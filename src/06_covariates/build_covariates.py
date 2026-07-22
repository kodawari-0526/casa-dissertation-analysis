#!/usr/bin/env python3
"""Join street lights, neighbourhood statistics and open spatial covariates."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "05_scoring"))
from pipeline_common import ensure_parent, load_config, project_path, require_columns, write_json
from scoring_core import add_streetlight_scores


VECTOR_SUFFIXES = {".gpkg", ".geojson", ".json", ".shp", ".parquet", ".feather"}
TABLE_SUFFIXES = {".csv", ".xlsx", ".xls"}


def first_data_file(path: Path) -> Path | None:
    if path.is_file():
        return path
    if path.is_dir():
        candidates = sorted(item for item in path.rglob("*") if item.suffix.lower() in VECTOR_SUFFIXES | TABLE_SUFFIXES)
        return candidates[0] if candidates else None
    return None


def read_any(path: Path) -> pd.DataFrame | gpd.GeoDataFrame:
    source = first_data_file(path)
    if source is None:
        raise FileNotFoundError(path)
    if source.suffix.lower() == ".parquet":
        return gpd.read_parquet(source)
    if source.suffix.lower() == ".feather":
        return gpd.read_feather(source)
    if source.suffix.lower() in VECTOR_SUFFIXES:
        return gpd.read_file(source)
    if source.suffix.lower() == ".csv":
        return pd.read_csv(source, low_memory=False)
    return pd.read_excel(source)


def coordinate_columns(frame: pd.DataFrame) -> tuple[str, str, str]:
    # The three council spreadsheets use different coordinate headings, and
    # some provide longitude/latitude while others use British National Grid.
    lookup = {str(column).strip().lower().replace(" ", "_"): column for column in frame.columns}
    pairs = [
        (("longitude", "lon", "lng", "long"), ("latitude", "lat"), "EPSG:4326"),
        (("easting", "eastings", "x", "x_coord"), ("northing", "northings", "y", "y_coord"), "EPSG:27700"),
    ]
    for xs, ys, crs in pairs:
        x = next((lookup[key] for key in xs if key in lookup), None)
        y = next((lookup[key] for key in ys if key in lookup), None)
        if x is not None and y is not None:
            return x, y, crs
    raise ValueError("Could not identify coordinate columns")


def as_points(frame: pd.DataFrame | gpd.GeoDataFrame, target_crs: str) -> gpd.GeoDataFrame:
    if isinstance(frame, gpd.GeoDataFrame) and frame.geometry.notna().any():
        if frame.crs is None:
            raise ValueError("Spatial input has no CRS")
        points = frame.copy()
    else:
        x, y, crs = coordinate_columns(frame)
        points = gpd.GeoDataFrame(
            frame.copy(),
            geometry=gpd.points_from_xy(pd.to_numeric(frame[x], errors="coerce"), pd.to_numeric(frame[y], errors="coerce")),
            crs=crs,
        )
    points = points.loc[points.geometry.notna() & ~points.geometry.is_empty].copy()
    return points.to_crs(target_crs)


def load_streetlights(specs: dict[str, str], crs: str) -> tuple[gpd.GeoDataFrame, dict[str, int]]:
    frames, counts = [], {}
    for borough, configured in specs.items():
        source = project_path(configured)
        if not source.exists():
            counts[borough] = 0
            continue
        points = as_points(read_any(source), crs)
        points["borough"] = borough
        points["lamp_source_row"] = np.arange(len(points), dtype=int)
        frames.append(points[["borough", "lamp_source_row", "geometry"]])
        counts[borough] = len(points)
    if not frames:
        return gpd.GeoDataFrame(columns=["borough", "lamp_source_row", "geometry"], geometry="geometry", crs=crs), counts
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=crs), counts


def streetlight_metrics(segments: gpd.GeoDataFrame, lamps: gpd.GeoDataFrame, maximum_distance: float) -> tuple[pd.DataFrame, dict[str, Any]]:
    assignments = []
    # Restrict nearest matches to the same borough so that points close to an
    # administrative boundary cannot jump into a different council inventory.
    for borough, borough_segments in segments.groupby("borough"):
        borough_lamps = lamps.loc[lamps["borough"].eq(borough)]
        if borough_lamps.empty:
            continue
        joined = gpd.sjoin_nearest(
            borough_lamps,
            borough_segments[["segment_id", "geometry"]],
            how="left",
            max_distance=maximum_distance,
            distance_col="match_distance_m",
        )
        joined = joined.sort_values("match_distance_m").drop_duplicates(["borough", "lamp_source_row"])
        assignments.append(joined)
    matched = gpd.GeoDataFrame(pd.concat(assignments, ignore_index=True), crs=segments.crs) if assignments else gpd.GeoDataFrame()
    line_lookup = segments.set_index("segment_id").geometry
    positions: dict[str, list[float]] = {}
    if not matched.empty:
        matched = matched.loc[matched["segment_id"].notna()].copy()
        for row in matched.itertuples(index=False):
            line = line_lookup.loc[row.segment_id]
            positions.setdefault(row.segment_id, []).append(float(line.project(row.geometry)))
    rows = []
    for row in segments[["segment_id", "borough", "segment_length_m"]].itertuples(index=False):
        values = sorted(positions.get(row.segment_id, []))
        # Segment ends are included because an unlit end section is still part
        # of the largest spacing gap experienced along the segment.
        breaks = [0.0, *values, float(row.segment_length_m)]
        maximum_gap = max(np.diff(breaks)) if len(breaks) > 1 else float(row.segment_length_m)
        count = len(values)
        rows.append(
            {
                "segment_id": row.segment_id,
                "borough": row.borough,
                "lamp_count": count,
                "lamp_density_per_100m": count / float(row.segment_length_m) * 100.0 if row.segment_length_m else np.nan,
                "max_gap_m": float(maximum_gap),
            }
        )
    metrics = pd.DataFrame(rows)
    qa = {
        "lamp_input_rows": int(len(lamps)),
        "assigned_lamp_count": int(sum(len(value) for value in positions.values())),
        "unmatched_lamp_count": int(len(lamps) - sum(len(value) for value in positions.values())),
        "maximum_match_distance_m": maximum_distance,
    }
    return metrics, qa


def dominant_polygon_join(lines: gpd.GeoDataFrame, polygons: gpd.GeoDataFrame, code: str) -> pd.DataFrame:
    polygons = polygons.to_crs(lines.crs).reset_index(drop=True)
    require_columns(polygons, [code, "geometry"], "polygon layer")
    pairs = gpd.sjoin(lines[["segment_id", "geometry"]], polygons[[code, "geometry"]], predicate="intersects", how="left")
    polygon_geometry = polygons.geometry
    pairs["overlap_length_m"] = pairs.apply(
        lambda row: row.geometry.intersection(polygon_geometry.iloc[int(row.index_right)]).length if pd.notna(row.index_right) else 0.0,
        axis=1,
    )
    dominant = pairs.sort_values("overlap_length_m", ascending=False).drop_duplicates("segment_id")
    output = dominant[["segment_id", code, "overlap_length_m"]].copy()
    output["join_method"] = np.where(output[code].notna(), "dominant_line_overlap", "")
    missing_ids = output.loc[output[code].isna(), "segment_id"]
    if len(missing_ids):
        nearest = gpd.sjoin_nearest(
            lines.loc[lines.segment_id.isin(missing_ids), ["segment_id", "geometry"]],
            polygons[[code, "geometry"]],
            how="left",
            distance_col="nearest_distance_m",
        ).sort_values("nearest_distance_m").drop_duplicates("segment_id")
        replacement = nearest.set_index("segment_id")
        mask = output["segment_id"].isin(replacement.index)
        output.loc[mask, code] = output.loc[mask, "segment_id"].map(replacement[code])
        output.loc[mask, "join_method"] = "nearest_polygon_fallback"
    return output


def nearest_numeric(lines: gpd.GeoDataFrame, layer: gpd.GeoDataFrame, prefix: str, numeric_hint: str | None = None) -> pd.DataFrame:
    layer = layer.to_crs(lines.crs)
    numeric = [column for column in layer.columns if column != "geometry" and pd.api.types.is_numeric_dtype(layer[column])]
    value = next((column for column in numeric if numeric_hint and numeric_hint.lower() in column.lower()), numeric[0] if numeric else None)
    columns = ["geometry"] + ([value] if value else [])
    joined = gpd.sjoin_nearest(lines[["segment_id", "geometry"]], layer[columns], how="left", distance_col=f"distance_to_{prefix}")
    joined = joined.sort_values(f"distance_to_{prefix}").drop_duplicates("segment_id")
    output = joined[["segment_id", f"distance_to_{prefix}"]].copy()
    if value:
        output[f"{prefix}_nearest_score"] = joined[value].to_numpy()
    return output


def point_proximity(lines: gpd.GeoDataFrame, points: gpd.GeoDataFrame, prefix: str, radius: float) -> pd.DataFrame:
    points = points.to_crs(lines.crs)
    nearest = gpd.sjoin_nearest(lines[["segment_id", "geometry"]], points[["geometry"]], how="left", distance_col=f"distance_to_nearest_{prefix}")
    nearest = nearest.sort_values(f"distance_to_nearest_{prefix}").drop_duplicates("segment_id")
    buffers = lines[["segment_id", "geometry"]].copy()
    buffers["geometry"] = buffers.geometry.buffer(radius)
    counts = gpd.sjoin(points[["geometry"]], buffers, predicate="within", how="inner").groupby("segment_id").size()
    output = nearest[["segment_id", f"distance_to_nearest_{prefix}"]].copy()
    output[f"{prefix}_count_{int(radius)}m"] = output["segment_id"].map(counts).fillna(0).astype(int)
    return output


def polygon_context(lines: gpd.GeoDataFrame, polygons: gpd.GeoDataFrame, prefix: str, radii: tuple[int, ...]) -> pd.DataFrame:
    polygons = polygons.to_crs(lines.crs).reset_index(drop=True)
    output = nearest_numeric(lines, polygons, prefix)[["segment_id", f"distance_to_{prefix}"]]
    centroids = lines[["segment_id", "geometry"]].copy()
    centroids["geometry"] = centroids.geometry.centroid
    inside = gpd.sjoin(centroids, polygons[["geometry"]], predicate="within", how="left").groupby("segment_id")["index_right"].apply(lambda value: value.notna().any())
    output[f"inside_{prefix}"] = output["segment_id"].map(inside).fillna(False).astype(int)
    for radius in radii:
        buffers = lines[["segment_id", "geometry"]].copy()
        buffers["geometry"] = buffers.geometry.buffer(radius)
        area = buffers.set_index("segment_id").geometry.area
        pairs = gpd.sjoin(buffers, polygons[["geometry"]], predicate="intersects", how="left")
        pairs["covered"] = pairs.apply(
            lambda row: row.geometry.intersection(polygons.geometry.iloc[int(row.index_right)]).area if pd.notna(row.index_right) else 0.0,
            axis=1,
        )
        covered = pairs.groupby("segment_id")["covered"].sum()
        output[f"{prefix}_share_{radius}m"] = output["segment_id"].map(covered).fillna(0.0) / output["segment_id"].map(area)
    return output


def building_context(lines: gpd.GeoDataFrame, buildings: gpd.GeoDataFrame) -> pd.DataFrame:
    buildings = buildings.to_crs(lines.crs)
    buildings = buildings.loc[buildings.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    buildings["footprint_area"] = buildings.geometry.area
    result = pd.DataFrame({"segment_id": lines["segment_id"]})
    for radius in (50, 100):
        buffers = lines[["segment_id", "geometry"]].copy()
        buffers["geometry"] = buffers.geometry.buffer(radius)
        buffer_area = buffers.set_index("segment_id").geometry.area
        joined = gpd.sjoin(buildings[["footprint_area", "geometry"]], buffers, predicate="intersects", how="inner")
        grouped = joined.groupby("segment_id")["footprint_area"]
        count, total, mean = grouped.size(), grouped.sum(), grouped.mean()
        result[f"building_count_{radius}m"] = result.segment_id.map(count).fillna(0).astype(int)
        result[f"total_building_footprint_area_{radius}m"] = result.segment_id.map(total).fillna(0.0)
        result[f"mean_building_footprint_area_{radius}m"] = result.segment_id.map(mean)
        result[f"building_density_per_ha_{radius}m"] = result[f"building_count_{radius}m"] / result.segment_id.map(buffer_area) * 10000.0
        result[f"building_coverage_ratio_{radius}m"] = result[f"total_building_footprint_area_{radius}m"] / result.segment_id.map(buffer_area)
        large = joined.assign(large=joined.footprint_area.ge(500)).groupby("segment_id")["large"].mean()
        result[f"large_building_share_{radius}m"] = result.segment_id.map(large).fillna(0.0)
    return result


def road_context(lines: gpd.GeoDataFrame, roads: gpd.GeoDataFrame) -> pd.DataFrame:
    roads = roads.to_crs(lines.crs)
    roads = roads.loc[roads.geometry.geom_type.isin(["LineString", "MultiLineString"])].copy()
    buffers = lines[["segment_id", "geometry"]].copy()
    buffers["geometry"] = buffers.geometry.buffer(100)
    buffer_lookup = buffers.set_index("segment_id").geometry
    area = buffer_lookup.area
    joined = gpd.sjoin(roads[["geometry"]], buffers, predicate="intersects", how="inner")
    joined["clipped_length"] = joined.apply(lambda row: row.geometry.intersection(buffer_lookup.loc[row.segment_id]).length, axis=1)
    lengths = joined.groupby("segment_id")["clipped_length"].sum()
    output = pd.DataFrame({"segment_id": lines.segment_id})
    output["os_openroads_road_density_100m"] = output.segment_id.map(lengths).fillna(0.0) / output.segment_id.map(area)
    class_column = next((column for column in roads.columns if "class" in column.lower() or "road" in column.lower()), None)
    if class_column:
        classified = roads[[class_column, "geometry"]].copy()
        classified["_class"] = classified[class_column].astype(str).str.lower()
        buffer50 = lines[["segment_id", "geometry"]].copy()
        buffer50["geometry"] = buffer50.geometry.buffer(50)
        pairs = gpd.sjoin(classified, buffer50, predicate="intersects", how="inner")
        for label, pattern in (("major_road", "motorway|primary|a road|a-road"), ("b_road", "secondary|b road|b-road")):
            ids = set(pairs.loc[pairs["_class"].str.contains(pattern, regex=True), "segment_id"])
            output[f"os_openroads_{label}_exposure_50m"] = output.segment_id.isin(ids).astype(int)
    return output


def line_context(lines: gpd.GeoDataFrame, features: gpd.GeoDataFrame, prefix: str, radius: int) -> pd.DataFrame:
    features = features.to_crs(lines.crs)
    features = features.loc[features.geometry.geom_type.isin(["LineString", "MultiLineString"])].copy()
    buffers = lines[["segment_id", "geometry"]].copy()
    buffers["geometry"] = buffers.geometry.buffer(radius)
    lookup = buffers.set_index("segment_id").geometry
    joined = gpd.sjoin(features[["geometry"]], buffers, predicate="intersects", how="inner")
    joined["overlap_length"] = joined.apply(lambda row: row.geometry.intersection(lookup.loc[row.segment_id]).length, axis=1)
    count = joined.groupby("segment_id").size()
    length = joined.groupby("segment_id")["overlap_length"].sum()
    output = pd.DataFrame({"segment_id": lines.segment_id})
    output[f"{prefix}_count_{radius}m"] = output.segment_id.map(count).fillna(0).astype(int)
    output[f"{prefix}_overlap_length_{radius}m"] = output.segment_id.map(length).fillna(0.0)
    output[f"{prefix}_density_{radius}m"] = output[f"{prefix}_overlap_length_{radius}m"] / output.segment_id.map(lookup.area)
    return output


def functional_site_context(lines: gpd.GeoDataFrame, sites: gpd.GeoDataFrame) -> pd.DataFrame:
    sites = sites.to_crs(lines.crs).reset_index(drop=True)
    sites = sites.loc[sites.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    category = next(
        (column for column in sites.columns if column != "geometry" and any(token in column.lower() for token in ("function", "class", "type"))),
        None,
    )
    sites["_category"] = sites[category].fillna("other").astype(str).str.lower() if category else "other"
    output = pd.DataFrame({"segment_id": lines.segment_id})
    for radius in (50, 100, 200):
        buffers = lines[["segment_id", "geometry"]].copy()
        buffers["geometry"] = buffers.geometry.buffer(radius)
        lookup = buffers.set_index("segment_id").geometry
        joined = gpd.sjoin(sites[["_category", "geometry"]], buffers, predicate="intersects", how="inner")
        joined["covered_area"] = joined.apply(lambda row: row.geometry.intersection(lookup.loc[row.segment_id]).area, axis=1)
        totals = joined.groupby("segment_id")["covered_area"].sum()
        counts = joined.groupby("segment_id").size()
        output[f"functional_site_count_{radius}m"] = output.segment_id.map(counts).fillna(0).astype(int)
        output[f"functional_site_area_share_{radius}m"] = output.segment_id.map(totals).fillna(0.0) / output.segment_id.map(lookup.area)
        if radius == 100:
            grouped = joined.groupby(["segment_id", "_category"])["covered_area"].sum()
            proportions = grouped / grouped.groupby(level=0).sum()
            entropy = proportions.groupby(level=0).apply(lambda values: float(-(values * np.log(values.clip(lower=1e-12))).sum()))
            output["functional_site_entropy_100m"] = output.segment_id.map(entropy).fillna(0.0)
            for label in ("transport", "retail", "commercial", "community", "public", "sport", "recreation"):
                areas = joined.loc[joined["_category"].str.contains(label)].groupby("segment_id")["covered_area"].sum()
                output[f"{label}_site_share_100m"] = output.segment_id.map(areas).fillna(0.0) / output.segment_id.map(lookup.area)
    return output


def merge_one_to_one(base: gpd.GeoDataFrame, extra: pd.DataFrame) -> gpd.GeoDataFrame:
    duplicate = [column for column in extra.columns if column in base.columns and column != "segment_id"]
    return base.drop(columns=duplicate, errors="ignore").merge(extra, on="segment_id", how="left", validate="one_to_one")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/pipeline.yml")
    parser.add_argument("--segments")
    parser.add_argument("--scores")
    parser.add_argument("--specs")
    parser.add_argument("--output")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)
    specs = load_config(args.specs or cfg["paths"]["covariate_specs"])
    segments = gpd.read_file(project_path(args.segments or cfg["paths"]["segments"]), layer="segments").to_crs(cfg["project"]["crs"])
    require_columns(segments, ["segment_id", "borough", "segment_length_m", "geometry"], "segments")
    scores = pd.read_csv(project_path(args.scores or cfg["paths"]["segment_scores"]))
    data = merge_one_to_one(segments, scores)
    qa: dict[str, Any] = {"skipped_inputs": [], "joined_inputs": []}

    lamps, source_counts = load_streetlights(specs["inputs"]["streetlights"], str(data.crs))
    if not lamps.empty:
        metrics, lamp_qa = streetlight_metrics(data, lamps, float(specs["streetlights"]["maximum_match_distance_m"]))
        metrics_output = ensure_parent(cfg["paths"]["streetlight_metrics"])
        metrics.to_csv(metrics_output, index=False)
        score_table = add_streetlight_scores(pd.DataFrame(data.drop(columns="geometry")), metrics)
        data = gpd.GeoDataFrame(score_table.merge(data[["segment_id", "geometry"]], on="segment_id", how="left"), crs=data.crs)
        qa["streetlights"] = {**lamp_qa, "source_rows_by_borough": source_counts}
        qa["joined_inputs"].append("streetlights")
    else:
        qa["skipped_inputs"].append("streetlights")

    lsoa_path = project_path(specs["inputs"]["lsoa_boundaries"])
    if lsoa_path.exists():
        lsoa = gpd.read_file(first_data_file(lsoa_path))
        lsoa_code = specs["join_fields"]["lsoa_code"]
        data = merge_one_to_one(data, dominant_polygon_join(data, lsoa, lsoa_code))
        qa["joined_inputs"].append("lsoa_boundaries")
        for table_name in ("imd", "census"):
            table_path = project_path(specs["inputs"][table_name])
            if table_path.exists():
                table = pd.DataFrame(read_any(table_path))
                source_code = specs["join_fields"][f"{table_name}_code"]
                if source_code != lsoa_code:
                    table = table.rename(columns={source_code: lsoa_code})
                table = table.drop_duplicates(lsoa_code)
                data = data.merge(table, on=lsoa_code, how="left", suffixes=("", f"_{table_name}"), validate="many_to_one")
                qa["joined_inputs"].append(table_name)
            else:
                qa["skipped_inputs"].append(table_name)
    else:
        qa["skipped_inputs"].extend(["lsoa_boundaries", "imd", "census"])

    spatial_jobs = [
        ("ptal", lambda layer: nearest_numeric(data, layer, "ptal", "ptal")),
        (
            "bus_stops",
            lambda layer: point_proximity(data, as_points(layer, str(data.crs)), "bus_stop", 400).rename(
                columns={"distance_to_nearest_bus_stop": "distance_to_nearest_bus_stop_v2", "bus_stop_count_400m": "bus_stop_count_400m_v2"}
            ),
        ),
        ("bus_routes", lambda layer: line_context(data, layer, "bus_route", 50)),
        ("high_streets", lambda layer: polygon_context(data, layer, "high_street", (50,))),
        ("town_centres", lambda layer: polygon_context(data, layer, "town_centre", (50,))),
        ("buildings", lambda layer: building_context(data, layer)),
        ("roads", lambda layer: road_context(data, layer)),
        (
            "greenspace",
            lambda layer: polygon_context(data, layer, "green_space", (100, 200)).rename(
                columns={"distance_to_green_space": "distance_to_nearest_public_green_space"}
            ),
        ),
        ("greenspace_access", lambda layer: point_proximity(data, as_points(layer, str(data.crs)), "green_access_point", 400)),
        ("functional_sites", lambda layer: functional_site_context(data, layer)),
        ("dft_traffic", lambda layer: nearest_numeric(data, layer, "nearest_dft_count", "aadf")),
    ]
    for name, builder in spatial_jobs:
        if name not in specs["inputs"]:
            qa["skipped_inputs"].append(name)
            continue
        source = project_path(specs["inputs"][name])
        if not source.exists():
            qa["skipped_inputs"].append(name)
            continue
        layer = read_any(source)
        if not isinstance(layer, gpd.GeoDataFrame):
            layer = as_points(layer, str(data.crs))
        data = merge_one_to_one(data, builder(layer))
        qa["joined_inputs"].append(name)

    data["log_segment_length_m"] = np.log1p(data["segment_length_m"])
    data["evidence_mass_per_100m"] = data["total_evidence_mass"] / data["segment_length_m"] * 100.0
    data["log_evidence_mass_per_100m"] = np.log1p(data["evidence_mass_per_100m"])
    if "PSSI_s" in data:
        data["pssi_below_60"] = data["PSSI_s"].lt(60).astype(int)
    output = ensure_parent(args.output or cfg["paths"]["analysis_segments"])
    data.to_file(output, layer="segment_open_covariates", driver="GPKG")
    data.drop(columns="geometry").to_csv(output.with_suffix(".csv"), index=False)
    qa.update({"segment_rows": len(data), "columns": len(data.columns), "crs": str(data.crs)})
    write_json(qa, output.with_suffix(".qa.json"))
    print(f"Wrote {len(data):,} analysis segments with {len(data.columns):,} fields")


if __name__ == "__main__":
    main()
