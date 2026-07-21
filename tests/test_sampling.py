from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
from shapely.geometry import LineString


SCRIPT = Path(__file__).resolve().parents[1] / "src/02_sampling/build_sampling.py"
SPEC = importlib.util.spec_from_file_location("build_sampling", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_sample_distances_are_centred_and_no_more_than_spacing() -> None:
    distances = MODULE.sample_distances(120.0, 50.0)
    assert np.allclose(distances, [20.0, 60.0, 100.0])
    assert np.diff(np.r_[0.0, distances, 120.0]).max() <= 50.0


def test_heading_is_clockwise_from_north() -> None:
    north = LineString([(0, 0), (0, 100)])
    east = LineString([(0, 0), (100, 0)])
    assert MODULE.line_heading(north, 50.0) == 0.0
    assert MODULE.line_heading(east, 50.0) == 90.0
