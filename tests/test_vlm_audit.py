from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "src/04_vlm_audit/run_audit.py"
SPEC = importlib.util.spec_from_file_location("run_audit", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def audit_item(score: int) -> dict:
    return {
        "applicable": True,
        "score": score,
        "confidence": 0.9,
        "evidence": "visible",
        "na_reason": None,
    }


def test_audit_request_uses_fixed_temperature(tmp_path) -> None:
    payload = {
        "image_id": "view-1",
        "sidewalk_serviceability_coarse": audit_item(2),
        "visible_drainage_feature_presence": audit_item(1),
        "kerb_ramp_or_flush_transition_presence": audit_item(0),
        "tactile_paving_presence": audit_item(0),
    }

    class FakeModels:
        config = None

        def generate_content(self, **kwargs):
            self.config = kwargs["config"]
            return type("Response", (), {"text": json.dumps(payload)})()

    class FakeClient:
        models = FakeModels()

    image = tmp_path / "view.jpg"
    image.write_bytes(b"image")
    result, attempts = MODULE.audit_one(FakeClient(), "model", "view-1", image, 1, 0.0)

    assert attempts == 1
    assert result["image_id"] == "view-1"
    assert FakeClient.models.config.temperature == 0.0
