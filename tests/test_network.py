from __future__ import annotations

import importlib.util
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString


SCRIPT = Path(__file__).resolve().parents[1] / "src/01_network/build_network.py"
SPEC = importlib.util.spec_from_file_location("build_network", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_junction_link_has_explicit_rejection_reason() -> None:
    row = pd.Series({"highway": "primary_link", "access": None, "service": None})
    assert MODULE.is_junction_link(row)
    assert MODULE.edge_rejection_reason(row) == "junction_link"


def test_linear_overlap_removes_shorter_duplicate_but_keeps_crossing() -> None:
    frame = gpd.GeoDataFrame(
        {
            "segment_length_m": [10.0, 6.0, 10.0],
            "geometry": [
                LineString([(0, 0), (10, 0)]),
                LineString([(2, 0), (8, 0)]),
                LineString([(5, -5), (5, 5)]),
            ],
        },
        crs="EPSG:27700",
    )
    cleaned, qa = MODULE.remove_linear_overlaps(frame, 0.5)
    assert len(cleaned) == 2
    assert qa["removed"] == 1
    assert qa["maximum_overlap_m"] == 6.0
    assert any(line.equals(LineString([(5, -5), (5, 5)])) for line in cleaned.geometry)
