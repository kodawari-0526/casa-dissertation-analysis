#!/usr/bin/env python3
"""Run the dissertation workflow in a fixed, inspectable order."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
STAGES = [
    ("01_network", ROOT / "src/01_network/build_network.py"),
    ("02_sampling", ROOT / "src/02_sampling/build_sampling.py"),
    ("03_streetview", ROOT / "src/03_streetview/fetch_metadata.py"),
    ("04_vlm_audit", ROOT / "src/04_vlm_audit/run_audit.py"),
    ("05_scoring", ROOT / "src/05_scoring/build_scores.py"),
    ("06_covariates", ROOT / "src/06_covariates/build_covariates.py"),
    ("07_analysis", ROOT / "src/07_analysis/run_analysis.py"),
    ("08_figures_tables", ROOT / "src/08_figures_tables/build_figures_tables.py"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/pipeline.yml")
    parser.add_argument("--from-stage", choices=[name for name, _ in STAGES])
    parser.add_argument("--to-stage", choices=[name for name, _ in STAGES])
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def selected_stages(first: str | None, last: str | None):
    names = [name for name, _ in STAGES]
    start = names.index(first) if first else 0
    stop = names.index(last) + 1 if last else len(STAGES)
    if start >= stop:
        raise ValueError("--from-stage must not come after --to-stage")
    return STAGES[start:stop]


def main() -> None:
    args = parse_args()
    config = str((ROOT / args.config).resolve())
    for name, script in selected_stages(args.from_stage, args.to_stage):
        command = [sys.executable, str(script), "--config", config]
        print(f"[{name}] {' '.join(command)}", flush=True)
        if not args.dry_run:
            subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
