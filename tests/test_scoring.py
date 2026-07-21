from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/05_scoring"))
from scoring_core import add_streetlight_scores, flatten_audit


def audit_item(applicable: bool, score: int | None, confidence: float = 1.0) -> dict:
    return {"applicable": applicable, "score": score, "confidence": confidence, "evidence": "visible", "na_reason": None if applicable else "not visible"}


def test_visual_weights_and_na_reweighting() -> None:
    record = {
        "image_id": "view-1",
        "status": "success",
        "audit": {
            "sidewalk_serviceability_coarse": audit_item(True, 2),
            "visible_drainage_feature_presence": audit_item(True, 0),
            "kerb_ramp_or_flush_transition_presence": audit_item(False, None),
            "tactile_paving_presence": audit_item(False, None),
        },
    }
    row = flatten_audit(record)
    assert np.isclose(row["EVIS_i"], 100.0 * 0.50 / 0.75)
    assert np.isclose(row["RVSI_i"], 70.0)
    assert row["evidence_tier"] == "A"


def test_streetlight_and_final_score_formulas() -> None:
    segments = pd.DataFrame(
        {
            "segment_id": ["a", "b"],
            "borough": ["X", "X"],
            "EVIS_s": [80.0, 60.0],
            "X_s_sw": [100.0, 50.0],
            "X_s_dr": [100.0, 50.0],
            "X_s_kr": [100.0, 50.0],
            "X_s_tp": [100.0, 50.0],
        }
    )
    metrics = pd.DataFrame(
        {
            "segment_id": ["a", "b"],
            "borough": ["X", "X"],
            "lamp_count": [2, 0],
            "lamp_density_per_100m": [4.0, 0.0],
            "max_gap_m": [10.0, 30.0],
        }
    )
    output = add_streetlight_scores(segments, metrics).set_index("segment_id")
    assert np.isclose(output.loc["a", "SL_s"], 75.0)
    assert output.loc["b", "SL_s"] == 0.0
    assert np.isclose(output.loc["a", "PSSI_s"], 79.0)
    assert np.isclose(output.loc["a", "PSSI_main"], 95.0)
