"""Scoring formulas shared by the scoring and covariate stages."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd


TARGETS = (
    "sidewalk_serviceability_coarse",
    "visible_drainage_feature_presence",
    "kerb_ramp_or_flush_transition_presence",
    "tactile_paving_presence",
)
SHORT = {
    "sidewalk_serviceability_coarse": "sw",
    "visible_drainage_feature_presence": "dr",
    "kerb_ramp_or_flush_transition_presence": "kr",
    "tactile_paving_presence": "tp",
}
MAX_SCORE = {
    "sidewalk_serviceability_coarse": 2.0,
    "visible_drainage_feature_presence": 1.0,
    "kerb_ramp_or_flush_transition_presence": 1.0,
    "tactile_paving_presence": 1.0,
}
DEFAULT_VISUAL_WEIGHTS = {
    "sidewalk_serviceability_coarse": 0.50,
    "visible_drainage_feature_presence": 0.25,
    "kerb_ramp_or_flush_transition_presence": 0.125,
    "tactile_paving_presence": 0.125,
}


def flatten_audit(record: Mapping[str, Any], weights: Mapping[str, float] | None = None) -> dict[str, Any]:
    weights = weights or DEFAULT_VISUAL_WEIGHTS
    image_id = str(record["image_id"])
    audit = record.get("audit", record)
    row: dict[str, Any] = {"view_id": image_id, "audit_status": record.get("status", "success")}
    visual_numerator = 0.0
    visual_denominator = 0.0
    primary_numerator = 0.0
    primary_denominator = 0.0
    for target in TARGETS:
        short = SHORT[target]
        item = audit[target]
        applicable = bool(item.get("applicable", False)) and item.get("score") is not None
        confidence = float(np.clip(item.get("confidence", 0.0), 0.0, 1.0))
        score = float(item["score"]) / MAX_SCORE[target] * 100.0 if applicable else np.nan
        mass = confidence if applicable else 0.0
        row[f"X_i_{short}"] = score
        row[f"A_i_{short}"] = int(applicable)
        row[f"C_i_{short}"] = confidence if applicable else np.nan
        row[f"M_i_{short}"] = mass
        row[f"evidence_{short}"] = item.get("evidence", "")
        row[f"na_reason_{short}"] = item.get("na_reason", "") if not applicable else ""
        if applicable:
            visual_numerator += float(weights[target]) * mass * score
            visual_denominator += float(weights[target]) * mass
            if short in {"sw", "dr"}:
                primary_weight = 0.70 if short == "sw" else 0.30
                primary_numerator += primary_weight * mass * score
                primary_denominator += primary_weight * mass
    row["evidence_mass"] = sum(float(row[f"M_i_{SHORT[target]}"]) for target in TARGETS)
    row["EVIS_i"] = visual_numerator / visual_denominator if visual_denominator else np.nan
    row["RVSI_i"] = primary_numerator / primary_denominator if primary_denominator else np.nan
    sw, dr = bool(row["A_i_sw"]), bool(row["A_i_dr"])
    secondary = bool(row["A_i_kr"] or row["A_i_tp"])
    row["evidence_tier"] = "A" if sw and dr else "B" if sw or dr else "C" if secondary else "NA"
    return row


def weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    valid = values.notna() & weights.notna() & weights.gt(0)
    if not valid.any():
        return np.nan
    return float(np.average(values[valid].astype(float), weights=weights[valid].astype(float)))


def aggregate_images_to_points(images: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for point_id, group in images.groupby("point_id", sort=False):
        row: dict[str, Any] = {
            "point_id": point_id,
            "segment_id": group["segment_id"].iloc[0],
            "borough": group["borough"].iloc[0],
            "image_count": int(len(group)),
            "valid_image_count": int(group["EVIS_i"].notna().sum()),
            "evidence_mass": float(group["evidence_mass"].sum()),
            "EVIS_p": weighted_mean(group["EVIS_i"], group["evidence_mass"]),
            "RVSI_p": weighted_mean(group["RVSI_i"], group["M_i_sw"] + group["M_i_dr"]),
        }
        for short in SHORT.values():
            row[f"X_p_{short}"] = weighted_mean(group[f"X_i_{short}"], group[f"M_i_{short}"])
            row[f"NA_p_{short}"] = float(1.0 - group[f"A_i_{short}"].mean())
            row[f"C_p_{short}"] = weighted_mean(group[f"C_i_{short}"], group[f"A_i_{short}"].astype(float))
            row[f"M_p_{short}"] = float(group[f"M_i_{short}"].sum())
        rows.append(row)
    return pd.DataFrame(rows)


def aggregate_points_to_segments(points: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for segment_id, group in points.groupby("segment_id", sort=False):
        row: dict[str, Any] = {
            "segment_id": segment_id,
            "borough": group["borough"].iloc[0],
            "n_sample_points_total": int(len(group)),
            "n_sample_points_valid": int(group["EVIS_p"].notna().sum()),
            "total_image_count": int(group["image_count"].sum()),
            "total_valid_image_count": int(group["valid_image_count"].sum()),
            "total_evidence_mass": float(group["evidence_mass"].sum()),
            "EVIS_s": weighted_mean(group["EVIS_p"], group["evidence_mass"]),
            "RVSI_s": weighted_mean(group["RVSI_p"], group["M_p_sw"] + group["M_p_dr"]),
        }
        for short in SHORT.values():
            mass = group[f"M_p_{short}"]
            row[f"X_s_{short}"] = weighted_mean(group[f"X_p_{short}"], mass)
            row[f"NA_s_{short}"] = float(group[f"NA_p_{short}"].mean())
            row[f"C_s_{short}"] = weighted_mean(group[f"C_p_{short}"], mass)
        rows.append(row)
    segments = pd.DataFrame(rows)
    segments["valid_image_rate"] = segments["total_valid_image_count"] / segments["total_image_count"].replace(0, np.nan)
    return segments


def add_streetlight_scores(segments: pd.DataFrame, metrics: pd.DataFrame) -> pd.DataFrame:
    needed = ["segment_id", "lamp_count", "lamp_density_per_100m", "max_gap_m"]
    missing = [column for column in needed if column not in metrics.columns]
    if missing:
        raise ValueError(f"street-light metrics missing: {', '.join(missing)}")
    duplicate = [column for column in metrics.columns if column in segments.columns and column != "segment_id"]
    output = segments.drop(columns=duplicate, errors="ignore").merge(metrics, on="segment_id", how="left", validate="one_to_one")
    for column in ["lamp_count", "lamp_density_per_100m", "max_gap_m"]:
        output[column] = pd.to_numeric(output[column], errors="coerce")
    # Lamp inventories differ sharply between councils, so the two component
    # ranks are calculated within each borough before they are combined.
    output["density_pr"] = output.groupby("borough")["lamp_density_per_100m"].rank(method="average", pct=True)
    output["gap_pr"] = output.groupby("borough")["max_gap_m"].rank(method="average", pct=True)
    output["inverse_gap_pr"] = 1.0 - output["gap_pr"]
    output["SL_s"] = 50.0 * (output["density_pr"] + output["inverse_gap_pr"])
    output.loc[output["lamp_count"].fillna(0).eq(0), "SL_s"] = 0.0
    # These fixed variants are the weights reported in the dissertation.
    output["PSSI_s"] = 0.80 * output["EVIS_s"] + 0.20 * output["SL_s"]
    output["PSSI_open"] = 0.70 * output["EVIS_s"] + 0.30 * output["SL_s"]
    components = ["X_s_sw", "X_s_dr", "X_s_kr", "X_s_tp"]
    complete = output[components].notna().all(axis=1)
    output["PSSI_eq"] = np.nan
    output.loc[complete, "PSSI_eq"] = 0.20 * output.loc[complete, components].sum(axis=1) + 0.20 * output.loc[complete, "SL_s"]
    output["PSSI_main"] = np.nan
    output.loc[complete, "PSSI_main"] = (
        0.40 * output.loc[complete, "X_s_sw"]
        + 0.20 * output.loc[complete, "X_s_dr"]
        + 0.10 * output.loc[complete, "X_s_kr"]
        + 0.10 * output.loc[complete, "X_s_tp"]
        + 0.20 * output.loc[complete, "SL_s"]
    )
    return output
