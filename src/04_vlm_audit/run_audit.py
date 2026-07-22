#!/usr/bin/env python3
"""Audit private street-view images with Gemini 2.5 Flash and validated JSON output."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import random
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
from google import genai
from google.genai import types
from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline_common import ensure_parent, load_config, project_path, require_columns, write_json


HERE = Path(__file__).resolve().parent
SCHEMA = json.loads((HERE / "schema.json").read_text(encoding="utf-8"))
PROMPT = (HERE / "prompt.txt").read_text(encoding="utf-8")
VALIDATOR = Draft202012Validator(SCHEMA)


def normalize_na(payload: dict[str, Any], image_id: str) -> dict[str, Any]:
    payload["image_id"] = image_id
    for target in (
        "sidewalk_serviceability_coarse",
        "visible_drainage_feature_presence",
        "kerb_ramp_or_flush_transition_presence",
        "tactile_paving_presence",
    ):
        item = payload[target]
        if not item.get("applicable", False):
            item["score"] = None
            item["na_reason"] = item.get("na_reason") or "not auditable from this view"
        else:
            item["na_reason"] = None
        item["confidence"] = max(0.0, min(1.0, float(item.get("confidence", 0.0))))
    VALIDATOR.validate(payload)
    return payload


def audit_one(client: genai.Client, model: str, image_id: str, image_path: Path, retries: int) -> tuple[dict[str, Any], int]:
    mime_type = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"
    image_bytes = image_path.read_bytes()
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = client.models.generate_content(
                model=model,
                contents=[
                    types.Part.from_text(text=PROMPT.format(image_id=image_id)),
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_json_schema=SCHEMA,
                ),
            )
            return normalize_na(json.loads(response.text), image_id), attempt
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(min(60.0, 2 ** (attempt - 1)) + random.random())
    raise RuntimeError(f"Audit failed for {image_id} after {retries} attempts: {type(last_error).__name__}") from last_error


def load_completed(path: Path) -> tuple[list[dict[str, Any]], set[str]]:
    rows: list[dict[str, Any]] = []
    if path.exists():
        with path.open(encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream if line.strip()]
    return rows, {str(row["image_id"]) for row in rows if row.get("status") == "success"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/pipeline.yml")
    parser.add_argument("--manifest")
    parser.add_argument("--output")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)
    audit_cfg = cfg["vlm_audit"]
    key_name = audit_cfg["api_key_env"]
    api_key = os.environ.get(key_name)
    if not api_key:
        raise RuntimeError(f"Set {key_name} in the environment before running the audit")
    manifest = pd.read_csv(project_path(args.manifest or cfg["paths"]["private_image_manifest"]))
    require_columns(manifest, ["view_id", "image_path"], "private image manifest")
    output = ensure_parent(args.output or cfg["paths"]["audit_jsonl"])
    rows, completed = load_completed(output) if args.resume else ([], set())
    pending = manifest.loc[~manifest["view_id"].astype(str).isin(completed)]
    if args.limit is not None:
        pending = pending.head(args.limit)
    client = genai.Client(api_key=api_key)
    for row in pending.itertuples(index=False):
        image_id = str(row.view_id)
        try:
            payload, attempts = audit_one(
                client,
                str(audit_cfg["model"]),
                image_id,
                project_path(row.image_path),
                int(audit_cfg["retries"]),
            )
            record = {"image_id": image_id, "status": "success", "attempts": attempts, "audit": payload}
        except Exception as exc:
            record = {"image_id": image_id, "status": "failed", "attempts": int(audit_cfg["retries"]), "error_type": type(exc).__name__}
        rows.append(record)
        # Rewrite the checkpoint after every image. The production run was long
        # enough that losing the completed records would have been costly.
        with output.open("w", encoding="utf-8") as stream:
            for item in rows:
                stream.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
    write_json(
        {
            "model": str(audit_cfg["model"]),
            "rows": len(rows),
            "success": sum(row.get("status") == "success" for row in rows),
            "failed": sum(row.get("status") == "failed" for row in rows),
            "raw_images_written_to_output": False,
        },
        output.with_suffix(".qa.json"),
    )
    print(f"Wrote {len(rows):,} audit records using {audit_cfg['model']}")


if __name__ == "__main__":
    main()
