#!/usr/bin/env python3
"""Download, clean and identify the three-borough OSM street network."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Any

import geopandas as gpd
import osmnx as ox
import pandas as pd
from shapely.geometry import LineString

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline_common import check_count, ensure_parent, load_config, project_path, require_columns, write_json


ALLOWED_HIGHWAYS = {
    "primary",
    "secondary",
    "tertiary",
    "residential",
    "unclassified",
    "living_street",
    "pedestrian",
    "service",
}
REJECTED_ACCESS = {"private", "no", "customers", "permit"}
REJECTED_SERVICE = {"driveway", "parking_aisle", "drive-through", "emergency_access"}
REJECTED_LIFECYCLE = {"construction", "proposed", "abandoned", "razed"}


def scalar_tags(value: Any) -> set[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return set()
    if isinstance(value, (list, tuple, set)):
        return {str(item).lower() for item in value}
    return {part.strip().lower() for part in str(value).replace("[", "").replace("]", "").replace("'", "").split(",")}


def is_junction_link(row: pd.Series) -> bool:
    """Identify OSM connector links rather than ordinary street frontage."""
    return any(highway.endswith("_link") for highway in scalar_tags(row.get("highway")))


def edge_rejection_reason(row: pd.Series) -> str | None:
    highways = scalar_tags(row.get("highway"))
    if is_junction_link(row):
        return "junction_link"
    if highways.intersection(REJECTED_LIFECYCLE):
        return "lifecycle"
    if not highways.intersection(ALLOWED_HIGHWAYS):
        return "highway_type"
    if scalar_tags(row.get("access")).intersection(REJECTED_ACCESS):
        return "restricted_access"
    if "service" in highways and scalar_tags(row.get("service")).intersection(REJECTED_SERVICE):
        return "internal_service"
    return None


def keep_edge(row: pd.Series) -> bool:
    return edge_rejection_reason(row) is None


def canonical_line_key(line: LineString, precision: int = 2) -> tuple[tuple[float, float], ...]:
    coords = tuple((round(x, precision), round(y, precision)) for x, y, *_ in line.coords)
    reverse = tuple(reversed(coords))
    return min(coords, reverse)


def geometry_fingerprint(borough: str, line: LineString) -> str:
    digest = hashlib.blake2b(repr(canonical_line_key(line)).encode(), digest_size=6).hexdigest().upper()
    prefix = borough.replace(" ", "_").upper()
    return f"{prefix}_G{digest}"


def to_undirected(graph):
    if hasattr(ox, "convert") and hasattr(ox.convert, "to_undirected"):
        return ox.convert.to_undirected(graph)
    return ox.utils_graph.get_undirected(graph)


def graph_edges(graph) -> gpd.GeoDataFrame:
    return ox.graph_to_gdfs(graph, nodes=False, fill_edge_geometry=True).reset_index()


def remove_linear_overlaps(edges: gpd.GeoDataFrame, threshold_m: float) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    """Keep one deterministic representative where lines overlap beyond the threshold.

    Exact crossings have zero linear intersection length and are retained. For a
    duplicated or partly duplicated pair, the longer line is kept; ties are
    resolved by the canonical geometry key.
    """
    if edges.empty:
        return edges.copy(), {"removed": 0, "maximum_overlap_m": 0.0}
    work = edges.reset_index(drop=True).copy()
    work["_geometry_key"] = work.geometry.map(canonical_line_key)
    priority = sorted(
        work.index,
        key=lambda index: (-float(work.at[index, "segment_length_m"]), work.at[index, "_geometry_key"]),
    )
    rank = {index: position for position, index in enumerate(priority)}
    removed: set[int] = set()
    maximum_overlap = 0.0
    spatial_index = work.sindex
    for index in priority:
        if index in removed:
            continue
        geometry = work.at[index, "geometry"]
        for candidate in spatial_index.query(geometry, predicate="intersects"):
            candidate = int(candidate)
            if candidate == index or candidate in removed or rank[candidate] <= rank[index]:
                continue
            overlap_length = float(geometry.intersection(work.at[candidate, "geometry"]).length)
            if overlap_length > threshold_m:
                removed.add(candidate)
                maximum_overlap = max(maximum_overlap, overlap_length)
    output = work.drop(index=list(removed)).drop(columns="_geometry_key").reset_index(drop=True)
    return output, {"removed": len(removed), "maximum_overlap_m": maximum_overlap}


def build_for_borough(boundary, borough: str, cfg: dict[str, Any]) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    crs = cfg["project"]["crs"]
    network_cfg = cfg["network"]
    query_polygon = gpd.GeoSeries([boundary], crs=crs).buffer(network_cfg["query_buffer_m"]).to_crs(4326).iloc[0]
    graph = ox.graph_from_polygon(query_polygon, network_type="all", simplify=True, retain_all=True)
    graph = to_undirected(graph)
    degree = dict(graph.degree())
    edges = graph_edges(graph).to_crs(crs)
    edges["is_dead_end"] = edges.apply(lambda row: degree.get(row["u"], 0) == 1 or degree.get(row["v"], 0) == 1, axis=1)
    rejection_reasons = edges.apply(edge_rejection_reason, axis=1)
    rejection_counts = rejection_reasons.dropna().value_counts().astype(int).to_dict()
    edges = edges[rejection_reasons.isna()].copy()
    edges = gpd.clip(edges, gpd.GeoSeries([boundary], crs=crs)).explode(index_parts=False, ignore_index=True)
    edges = edges[edges.geometry.geom_type.eq("LineString") & ~edges.geometry.is_empty].copy()
    edges["segment_length_m"] = edges.geometry.length
    minimum = float(network_cfg["minimum_length_m"])
    short_limit = float(network_cfg["short_segment_threshold_m"])
    # Most very short lines are clipping or junction slivers. Named streets,
    # pedestrian streets and genuine dead ends are kept down to the 5 m floor.
    short_real_street = (
        edges["highway"].map(lambda value: bool(scalar_tags(value).intersection({"pedestrian", "living_street"})))
        | edges["is_dead_end"].fillna(False)
        | edges.get("name", pd.Series(index=edges.index, dtype=object)).notna()
    )
    keep_length = (edges["segment_length_m"] >= short_limit) | ((edges["segment_length_m"] >= minimum) & short_real_street)
    micro_fragments_removed = int((~keep_length).sum())
    boundary_slivers_removed = int(((~keep_length) & edges.geometry.distance(boundary.boundary).le(1e-7)).sum())
    edges = edges[keep_length].copy()
    edges["_geometry_key"] = edges.geometry.map(canonical_line_key)
    before_exact_duplicates = len(edges)
    edges = edges.sort_values("_geometry_key").drop_duplicates("_geometry_key").reset_index(drop=True).copy()
    exact_duplicates_removed = before_exact_duplicates - len(edges)
    edges, overlap_qa = remove_linear_overlaps(edges, float(network_cfg["overlap_threshold_m"]))
    edges["borough"] = borough
    prefix = borough.replace(" ", "_").upper()
    edges["segment_id"] = [f"{prefix}_SEG{index:05d}" for index in range(len(edges))]
    edges["geometry_id"] = edges.geometry.map(lambda geometry: geometry_fingerprint(borough, geometry))
    columns = [
        "segment_id",
        "geometry_id",
        "borough",
        "segment_length_m",
        "highway",
        "name",
        "access",
        "service",
        "is_dead_end",
        "geometry",
    ]
    for column in columns:
        if column not in edges:
            edges[column] = None
    qa = {
        "filter_rejections": rejection_counts,
        "junction_links_removed": int(rejection_counts.get("junction_link", 0)),
        "micro_fragments_removed": micro_fragments_removed,
        "boundary_slivers_removed": boundary_slivers_removed,
        "exact_duplicate_geometries_removed": exact_duplicates_removed,
        "overlap_threshold_m": float(network_cfg["overlap_threshold_m"]),
        "overlap_geometries_removed": int(overlap_qa["removed"]),
        "maximum_removed_overlap_m": float(overlap_qa["maximum_overlap_m"]),
    }
    return edges[columns], qa


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/pipeline.yml")
    parser.add_argument("--boundaries")
    parser.add_argument("--output")
    parser.add_argument("--strict-count", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)
    boundary_path = project_path(args.boundaries or cfg["paths"]["borough_boundaries"])
    output = ensure_parent(args.output or cfg["paths"]["segments"])
    boundaries = gpd.read_file(boundary_path).to_crs(cfg["project"]["crs"])
    borough_field = cfg["project"]["borough_field"]
    require_columns(boundaries, [borough_field, "geometry"], "borough boundaries")
    boundaries[borough_field] = boundaries[borough_field].astype(str).str.upper().str.replace(" ", "_", regex=False)
    frames = []
    cleaning_qa = {}
    for borough in cfg["project"]["boroughs"]:
        selected = boundaries.loc[boundaries[borough_field].eq(borough), "geometry"]
        if selected.empty:
            raise ValueError(f"No boundary found for {borough}")
        boundary = selected.union_all() if hasattr(selected, "union_all") else selected.unary_union
        borough_segments, borough_cleaning_qa = build_for_borough(boundary, borough, cfg)
        frames.append(borough_segments)
        cleaning_qa[borough] = borough_cleaning_qa
    segments = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=cfg["project"]["crs"])
    if segments["segment_id"].duplicated().any():
        raise RuntimeError("Duplicate segment IDs remain after network cleaning")
    segments.to_file(output, layer="segments", driver="GPKG")
    strict = args.strict_count or cfg["network"].get("strict_count", False)
    count_qa = check_count(
        "cleaned segments",
        len(segments),
        cfg["network"]["expected_segments"],
        strict,
    )
    borough_counts = segments.groupby("borough").size().astype(int).to_dict()
    borough_qa = {
        borough: check_count(f"{borough} segments", borough_counts.get(borough, 0), expected, strict)
        for borough, expected in cfg["network"].get("expected_by_borough", {}).items()
    }
    write_json(
        {
            "count": count_qa,
            "by_borough": borough_counts,
            "by_borough_checks": borough_qa,
            "cleaning_by_borough": cleaning_qa,
            "minimum_length_m": float(segments.segment_length_m.min()),
            "maximum_length_m": float(segments.segment_length_m.max()),
            "crs": str(segments.crs),
        },
        output.with_suffix(".qa.json"),
    )
    print(f"Wrote {len(segments):,} segments to {output}")


if __name__ == "__main__":
    main()
