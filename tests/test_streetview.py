from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd


SCRIPT = Path(__file__).resolve().parents[1] / "src/03_streetview/fetch_metadata.py"
SPEC = importlib.util.spec_from_file_location("fetch_metadata", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_download_images_writes_private_manifest(tmp_path, monkeypatch) -> None:
    requests = pd.DataFrame(
        [
            {
                "view_id": "SEG001_P001_FORWARD",
                "request_parameters": json.dumps({"pano": "example", "heading": 0, "size": "640x640"}),
            }
        ]
    )

    def fake_request(*args, **kwargs):
        return b"test-image", 1

    monkeypatch.setattr(MODULE, "request_image_with_retry", fake_request)
    output = tmp_path / "private_images.csv"
    images = tmp_path / "images"
    manifest, qa = MODULE.download_images(requests, images, output, "not-written", 1)

    assert output.exists()
    assert (images / "SEG001_P001_FORWARD.jpg").read_bytes() == b"test-image"
    assert manifest.loc[0, "view_id"] == "SEG001_P001_FORWARD"
    assert qa["downloaded"] == 1
    assert qa["api_key_written"] is False


def test_download_images_reuses_existing_file(tmp_path, monkeypatch) -> None:
    images = tmp_path / "images"
    images.mkdir()
    target = images / "SEG001_P001_FORWARD.jpg"
    target.write_bytes(b"existing")
    requests = pd.DataFrame(
        [{"view_id": "SEG001_P001_FORWARD", "request_parameters": json.dumps({"pano": "example"})}]
    )

    def unexpected_request(*args, **kwargs):
        raise AssertionError("existing image should be reused")

    monkeypatch.setattr(MODULE, "request_image_with_retry", unexpected_request)
    _, qa = MODULE.download_images(requests, images, tmp_path / "private_images.csv", "not-written", 1)
    assert qa["reused"] == 1
