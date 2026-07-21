#!/usr/bin/env python3
"""Aggregate image audits to points and segments and calculate score variants."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline_common import ensure_parent, load_config, project_path, require_columns, write_json
from scoring_core import add_streetlight_scores, aggregate_images_to_points, aggregate_points_to_segments, flatten_audit


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/pipeline.yml")
    parser.add_argument("--audits")
    parser.add_argument("--views")
    parser.add_argument("--streetlights")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)
    audit_path = project_path(args.audits or cfg["paths"]["audit_jsonl"])
    views = pd.read_csv(project_path(args.views or cfg["paths"]["view_manifest"]))
    require_columns(views, ["view_id", "point_id", "segment_id", "borough"], "view manifest")
    records = [record for record in read_jsonl(audit_path) if record.get("status") == "success"]
    image_scores = pd.DataFrame([flatten_audit(record, cfg["scoring"]["visual_weights"]) for record in records]).merge(
        views[["view_id", "point_id", "segment_id", "borough"]], on="view_id", how="left", validate="one_to_one"
    )
    if image_scores[["point_id", "segment_id", "borough"]].isna().any().any():
        raise RuntimeError("Some successful audits do not match the view manifest")
    point_scores = aggregate_images_to_points(image_scores)
    segment_scores = aggregate_points_to_segments(point_scores)
    streetlights_path = project_path(args.streetlights or cfg["paths"]["streetlight_metrics"])
    if streetlights_path.exists():
        segment_scores = add_streetlight_scores(segment_scores, pd.read_csv(streetlights_path))
    outputs = {
        "images": ensure_parent(cfg["paths"]["image_scores"]),
        "points": ensure_parent(cfg["paths"]["point_scores"]),
        "segments": ensure_parent(cfg["paths"]["segment_scores"]),
    }
    image_scores.to_csv(outputs["images"], index=False)
    point_scores.to_csv(outputs["points"], index=False)
    segment_scores.to_csv(outputs["segments"], index=False)
    write_json(
        {
            "audit_rows": len(records),
            "valid_image_scores": int(image_scores["EVIS_i"].notna().sum()),
            "point_rows": len(point_scores),
            "segment_rows": len(segment_scores),
            "segments_with_evis": int(segment_scores["EVIS_s"].notna().sum()),
            "streetlight_scores_added": "SL_s" in segment_scores.columns,
            "visual_weights": cfg["scoring"]["visual_weights"],
        },
        outputs["segments"].with_suffix(".qa.json"),
    )
    print(f"Wrote scores for {len(image_scores):,} images, {len(point_scores):,} points and {len(segment_scores):,} segments")


if __name__ == "__main__":
    main()
