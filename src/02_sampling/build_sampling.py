#!/usr/bin/env python3
"""Create approximately 50 m sample points and four viewing directions."""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline_common import check_count, ensure_parent, load_config, project_path, require_columns, write_json


DIRECTIONS = (("forward", 0.0), ("backward", 180.0), ("left", -90.0), ("right", 90.0))


def sample_distances(length: float, spacing: float) -> np.ndarray:
    count = max(1, int(math.ceil(length / spacing)))
    return (np.arange(count, dtype=float) + 0.5) * length / count


def line_heading(line: LineString, distance: float) -> float:
    epsilon = min(2.0, max(line.length / 100.0, 0.05))
    before = line.interpolate(max(0.0, distance - epsilon))
    after = line.interpolate(min(line.length, distance + epsilon))
    dx, dy = after.x - before.x, after.y - before.y
    return float((math.degrees(math.atan2(dx, dy)) + 360.0) % 360.0)


def build_points(segments: gpd.GeoDataFrame, spacing: float) -> gpd.GeoDataFrame:
    records = []
    for row in segments.itertuples(index=False):
        line = row.geometry
        distances = sample_distances(float(line.length), spacing)
        for ordinal, distance in enumerate(distances, start=1):
            point_id = f"{row.segment_id}_P{ordinal:03d}"
            records.append(
                {
                    "point_id": point_id,
                    "segment_id": row.segment_id,
                    "borough": row.borough,
                    "point_order": ordinal,
                    "distance_along_m": float(distance),
                    "base_heading": line_heading(line, float(distance)),
                    "geometry": line.interpolate(float(distance)),
                }
            )
    return gpd.GeoDataFrame(records, crs=segments.crs)


def build_views(points: gpd.GeoDataFrame) -> pd.DataFrame:
    geographic = points.to_crs(4326)
    records = []
    for row in geographic.itertuples(index=False):
        for direction, offset in DIRECTIONS:
            records.append(
                {
                    "view_id": f"{row.point_id}_{direction.upper()}",
                    "point_id": row.point_id,
                    "segment_id": row.segment_id,
                    "borough": row.borough,
                    "direction": direction,
                    "heading": round((float(row.base_heading) + offset) % 360.0, 6),
                    "latitude": round(row.geometry.y, 8),
                    "longitude": round(row.geometry.x, 8),
                }
            )
    return pd.DataFrame.from_records(records)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/pipeline.yml")
    parser.add_argument("--segments")
    parser.add_argument("--points-output")
    parser.add_argument("--views-output")
    parser.add_argument("--strict-count", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)
    segments_path = project_path(args.segments or cfg["paths"]["segments"])
    points_output = ensure_parent(args.points_output or cfg["paths"]["sample_points"])
    views_output = ensure_parent(args.views_output or cfg["paths"]["view_manifest"])
    segments = gpd.read_file(segments_path, layer="segments")
    require_columns(segments, ["segment_id", "borough", "geometry"], "segments")
    spacing = float(cfg["sampling"]["spacing_m"])
    points = build_points(segments, spacing)
    views = build_views(points)
    if views["view_id"].duplicated().any() or points["point_id"].duplicated().any():
        raise RuntimeError("Sampling produced duplicate identifiers")
    if len(views) != 4 * len(points):
        raise RuntimeError("Each point must have exactly four view rows")
    points.to_file(points_output, layer="sample_points", driver="GPKG")
    views.to_csv(views_output, index=False)
    strict = args.strict_count or cfg["sampling"].get("strict_count", False)
    write_json(
        {
            "points": check_count("sample points", len(points), cfg["sampling"]["expected_points"], strict),
            "views": check_count("view rows", len(views), cfg["sampling"]["expected_views"], strict),
            "views_per_point": 4,
            "spacing_m": spacing,
        },
        points_output.with_suffix(".qa.json"),
    )
    print(f"Wrote {len(points):,} points and {len(views):,} views")


if __name__ == "__main__":
    main()
