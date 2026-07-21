"""Small shared helpers for command-line pipeline stages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]


def project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = project_path(path)
    with config_path.open(encoding="utf-8") as stream:
        config = yaml.safe_load(stream) or {}
    config["_config_path"] = str(config_path)
    return config


def ensure_parent(path: str | Path) -> Path:
    output = project_path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    return output


def write_json(payload: Any, path: str | Path) -> Path:
    output = ensure_parent(path)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output


def require_columns(frame: Any, columns: list[str], label: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{label} is missing required columns: {', '.join(missing)}")


def check_count(label: str, observed: int, expected: int, strict: bool) -> dict[str, Any]:
    result = {
        "label": label,
        "observed": int(observed),
        "expected": int(expected),
        "matches_expected": int(observed) == int(expected),
    }
    if strict and not result["matches_expected"]:
        raise RuntimeError(f"{label}: expected {expected:,}, observed {observed:,}")
    return result
