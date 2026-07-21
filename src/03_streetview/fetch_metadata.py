#!/usr/bin/env python3
"""Resolve Street View metadata and prepare a key-free request manifest."""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline_common import ensure_parent, load_config, project_path, require_columns, write_json


METADATA_ENDPOINT = "https://maps.googleapis.com/maps/api/streetview/metadata"
RETRYABLE_STATUSES = {"UNKNOWN_ERROR", "OVER_QUERY_LIMIT"}


def request_with_retry(session: requests.Session, params: dict[str, Any], retries: int) -> tuple[dict[str, Any], int]:
    last: dict[str, Any] = {}
    for attempt in range(1, retries + 1):
        try:
            response = session.get(METADATA_ENDPOINT, params=params, timeout=30)
            response.raise_for_status()
            last = response.json()
            if last.get("status") not in RETRYABLE_STATUSES:
                return last, attempt
        except (requests.RequestException, ValueError) as exc:
            last = {"status": "REQUEST_ERROR", "error_type": type(exc).__name__}
        if attempt < retries:
            time.sleep(min(30.0, 2 ** (attempt - 1)) + random.random())
    return last, retries


def metadata_row(view: pd.Series, payload: dict[str, Any], attempts: int) -> dict[str, Any]:
    location = payload.get("location") or {}
    return {
        **view.to_dict(),
        "status": payload.get("status", "UNKNOWN"),
        "pano_id": payload.get("pano_id", ""),
        "pano_date": payload.get("date", ""),
        "pano_latitude": location.get("lat"),
        "pano_longitude": location.get("lng"),
        "copyright": payload.get("copyright", ""),
        "attempts": attempts,
        "error_type": payload.get("error_type", ""),
    }


def request_manifest(metadata: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    street_cfg = cfg["streetview"]
    manifest = metadata.loc[metadata["status"].eq("OK")].copy()
    manifest["request_parameters"] = manifest.apply(
        lambda row: json.dumps(
            {
                "pano": row["pano_id"],
                "size": street_cfg["size"],
                "heading": float(row["heading"]),
                "fov": int(street_cfg["fov"]),
                "pitch": int(street_cfg["pitch"]),
                "source": street_cfg["source"],
            },
            separators=(",", ":"),
        ),
        axis=1,
    )
    return manifest[["view_id", "point_id", "segment_id", "borough", "pano_id", "pano_date", "request_parameters"]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/pipeline.yml")
    parser.add_argument("--views")
    parser.add_argument("--output")
    parser.add_argument("--request-output")
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)
    street_cfg = cfg["streetview"]
    key_name = street_cfg["api_key_env"]
    api_key = os.environ.get(key_name)
    if not api_key:
        raise RuntimeError(f"Set {key_name} in the environment before resolving metadata")
    views = pd.read_csv(project_path(args.views or cfg["paths"]["view_manifest"]))
    require_columns(views, ["view_id", "point_id", "segment_id", "borough", "heading", "latitude", "longitude"], "view manifest")
    output = ensure_parent(args.output or cfg["paths"]["streetview_metadata"])
    request_output = ensure_parent(args.request_output or cfg["paths"]["streetview_requests"])
    completed = pd.read_csv(output) if args.resume and output.exists() else pd.DataFrame()
    done = set(completed.get("view_id", pd.Series(dtype=str)).astype(str))
    rows = completed.to_dict("records")
    session = requests.Session()
    pending = views.loc[~views["view_id"].astype(str).isin(done)]
    for _, point_views in pending.groupby("point_id", sort=False):
        view = point_views.iloc[0]
        payload, attempts = request_with_retry(
            session,
            {
                "location": f"{view.latitude:.8f},{view.longitude:.8f}",
                "radius": int(street_cfg["radius_m"]),
                "source": street_cfg["source"],
                "key": api_key,
            },
            int(street_cfg["retries"]),
        )
        rows.extend(metadata_row(point_view, payload, attempts) for _, point_view in point_views.iterrows())
        if len(rows) % 250 == 0:
            pd.DataFrame(rows).to_csv(output, index=False)
    metadata = pd.DataFrame(rows).sort_values("view_id")
    metadata.to_csv(output, index=False)
    requests_frame = request_manifest(metadata, cfg)
    requests_frame.to_csv(request_output, index=False)
    write_json(
        {
            "rows": int(len(metadata)),
            "status_counts": metadata["status"].value_counts(dropna=False).astype(int).to_dict(),
            "unique_panoramas": int(metadata.loc[metadata.status.eq("OK"), "pano_id"].nunique()),
            "keys_or_signed_urls_written": False,
        },
        output.with_suffix(".qa.json"),
    )
    print(f"Wrote {len(metadata):,} metadata rows; no API key or signed URL was saved")


if __name__ == "__main__":
    main()
