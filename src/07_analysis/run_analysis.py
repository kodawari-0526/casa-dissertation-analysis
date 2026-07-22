#!/usr/bin/env python3
"""Run descriptive, equity, spatial and multivariable analyses."""

from __future__ import annotations

import argparse
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import statsmodels.api as sm
from esda.moran import Moran, Moran_Local
from libpysal.weights import KNN
import spreg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline_common import load_config, project_path, require_columns, write_json


@dataclass
class ModelRun:
    model_id: str
    outcome: str
    predictors: list[str]
    sample: pd.DataFrame
    design: pd.DataFrame
    response: pd.Series
    result: Any
    covariance: str


def clean_number(value: Any) -> float:
    try:
        number = float(value)
        return number if np.isfinite(number) else np.nan
    except (TypeError, ValueError):
        return np.nan


def make_design(frame: pd.DataFrame, outcome: str, predictors: list[str]) -> tuple[pd.Series, pd.DataFrame, pd.DataFrame]:
    predictors = [name for name in dict.fromkeys(predictors) if name in frame.columns]
    needed = [outcome, *predictors, "borough"]
    if "lsoa21cd" in frame.columns:
        needed.append("lsoa21cd")
    sample = frame[needed].copy()
    sample[outcome] = pd.to_numeric(sample[outcome], errors="coerce")
    numeric: dict[str, pd.Series] = {}
    for name in predictors:
        values = pd.to_numeric(sample[name], errors="coerce")
        if values.dropna().nunique() <= 2:
            numeric[name] = values.astype(float)
        else:
            deviation = values.std(ddof=0)
            numeric[name] = (values - values.mean()) / deviation if deviation and np.isfinite(deviation) else values * 0.0
    design = pd.DataFrame(numeric, index=sample.index)
    borough = pd.get_dummies(sample["borough"].astype(str), prefix="borough", drop_first=True, dtype=float)
    design = pd.concat([design, borough], axis=1)
    complete = sample[outcome].notna() & design.notna().all(axis=1)
    sample = sample.loc[complete]
    response = sample[outcome].astype(float)
    design = sm.add_constant(design.loc[complete].astype(float), has_constant="add")
    return response, design, sample


def fit_model(frame: pd.DataFrame, model_id: str, outcome: str, predictors: list[str], weights: pd.Series | None = None) -> ModelRun:
    response, design, sample = make_design(frame, outcome, predictors)
    if weights is None:
        model = sm.OLS(response, design)
    else:
        model = sm.WLS(response, design, weights=weights.loc[sample.index].astype(float))
    try:
        if weights is None and "lsoa21cd" in sample and sample["lsoa21cd"].nunique() > 1:
            result = model.fit(cov_type="cluster", cov_kwds={"groups": sample["lsoa21cd"].astype(str)})
            covariance = "cluster_lsoa"
        else:
            result = model.fit(cov_type="HC3")
            covariance = "HC3"
    except Exception:
        result = model.fit(cov_type="HC3")
        covariance = "HC3"
    return ModelRun(model_id, outcome, predictors, sample, design, response, result, covariance)


def coefficient_table(run: ModelRun) -> pd.DataFrame:
    confidence = np.asarray(run.result.conf_int())
    rows = []
    for index, term in enumerate(run.design.columns):
        rows.append(
            {
                "model_id": run.model_id,
                "outcome": run.outcome,
                "term": term,
                "coefficient": clean_number(run.result.params.iloc[index]),
                "std_error": clean_number(run.result.bse.iloc[index]),
                "p_value": clean_number(run.result.pvalues.iloc[index]),
                "ci_low": clean_number(confidence[index, 0]),
                "ci_high": clean_number(confidence[index, 1]),
                "covariance": run.covariance,
                "n": int(run.result.nobs),
            }
        )
    return pd.DataFrame(rows)


def model_fit(run: ModelRun) -> dict[str, Any]:
    residual = np.asarray(run.result.resid, dtype=float)
    return {
        "model_id": run.model_id,
        "outcome": run.outcome,
        "n": int(run.result.nobs),
        "predictor_count": len(run.predictors),
        "r_squared": clean_number(getattr(run.result, "rsquared", np.nan)),
        "adjusted_r_squared": clean_number(getattr(run.result, "rsquared_adj", np.nan)),
        "aic": clean_number(getattr(run.result, "aic", np.nan)),
        "bic": clean_number(getattr(run.result, "bic", np.nan)),
        "rmse": clean_number(np.sqrt(np.mean(np.square(residual)))),
        "covariance": run.covariance,
    }


def spatial_weights(frame: gpd.GeoDataFrame, k: int) -> KNN:
    centroids = frame.geometry.centroid
    coordinates = np.column_stack([centroids.x.to_numpy(), centroids.y.to_numpy()])
    # Eight neighbours preserve the three borough components while giving each
    # segment a consistent local comparison set.
    weights = KNN.from_array(coordinates, k=min(k, len(frame) - 1))
    weights.transform = "R"
    return weights


def local_moran(frame: gpd.GeoDataFrame, outcome: str, k: int, permutations: int, seed: int) -> tuple[pd.DataFrame, dict[str, float]]:
    sample = frame.loc[frame[outcome].notna(), ["segment_id", outcome, "geometry"]].copy()
    weights = spatial_weights(sample, k)
    values = sample[outcome].to_numpy(dtype=float)
    global_stat = Moran(values, weights, permutations=permutations)
    local = Moran_Local(values, weights, permutations=permutations, seed=seed)
    labels = np.array(["HH", "LH", "LL", "HL"], dtype=object)[np.asarray(local.q, dtype=int) - 1]
    significant = np.asarray(local.p_sim) < 0.05
    labels = np.where(significant, labels, "Not significant")
    output = pd.DataFrame(
        {
            "segment_id": sample["segment_id"].to_numpy(),
            "local_moran_i": np.asarray(local.Is, dtype=float),
            "local_moran_p": np.asarray(local.p_sim, dtype=float),
            "local_moran_quadrant": labels,
            "local_moran_significant": significant.astype(int),
        }
    )
    summary = {"global_moran_i": float(global_stat.I), "global_moran_p": float(global_stat.p_sim)}
    return output, summary


def priority_typology(frame: pd.DataFrame, outcome: str, deprivation: str) -> pd.DataFrame:
    output = frame[["segment_id", "borough", outcome, deprivation]].copy().reset_index(drop=True)
    # Quintiles are borough-specific: the screen is intended to highlight local
    # contrasts rather than let cross-borough level differences set the cut-offs.
    output["deprivation_q20"] = output.groupby("borough")[deprivation].transform(lambda values: values.quantile(0.20))
    output["deprivation_q80"] = output.groupby("borough")[deprivation].transform(lambda values: values.quantile(0.80))
    output["score_q20"] = output.groupby("borough")[outcome].transform(lambda values: values.quantile(0.20))
    output["score_q80"] = output.groupby("borough")[outcome].transform(lambda values: values.quantile(0.80))
    high_dep = output[deprivation].ge(output["deprivation_q80"])
    low_dep = output[deprivation].le(output["deprivation_q20"])
    low_score = output[outcome].le(output["score_q20"])
    high_score = output[outcome].ge(output["score_q80"])
    output["priority_typology"] = np.select(
        [high_dep & low_score, high_dep & high_score, low_dep & high_score, low_dep & low_score],
        ["High deprivation + low score", "High deprivation + high score", "Low deprivation + high score", "Low deprivation + low score"],
        default="Other",
    )
    return output


def borough_summary(frame: pd.DataFrame, low_threshold: float) -> pd.DataFrame:
    rows = []
    for borough, group in frame.groupby("borough"):
        row: dict[str, Any] = {"borough": borough, "segments": len(group)}
        for score in ("EVIS_s", "SL_s", "PSSI_s", "RVSI_s"):
            if score in group:
                row[f"mean_{score}"] = group[score].mean()
                row[f"sd_{score}"] = group[score].std()
                row[f"median_{score}"] = group[score].median()
        row[f"share_PSSI_below_{low_threshold:g}"] = group["PSSI_s"].lt(low_threshold).mean()
        rows.append(row)
    return pd.DataFrame(rows)


def aggregate_lsoa(frame: pd.DataFrame, predictors: list[str]) -> pd.DataFrame:
    require_columns(frame, ["lsoa21cd", "borough", "segment_id", "PSSI_s"], "analysis segments")
    aggregations: dict[str, str] = {
        "segment_id": "count",
        "borough": "first",
        "PSSI_s": "mean",
        "EVIS_s": "mean",
        "SL_s": "mean",
    }
    for predictor in predictors:
        if predictor in frame:
            aggregations[predictor] = "mean"
    if "pssi_below_60" in frame:
        aggregations["pssi_below_60"] = "mean"
    output = frame.groupby("lsoa21cd", as_index=False).agg(aggregations)
    return output.rename(
        columns={
            "segment_id": "n_segments",
            "PSSI_s": "mean_PSSI_s",
            "EVIS_s": "mean_EVIS_s",
            "SL_s": "mean_SL_s",
            "pssi_below_60": "share_PSSI_below_60",
        }
    )


def deprivation_correlations(frame: pd.DataFrame, scores: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    candidates = [
        name
        for name in frame.columns
        if any(token in name.lower() for token in ("imd", "income", "employment", "living_environment", "health_deprivation", "idaci", "idaopi"))
        and pd.api.types.is_numeric_dtype(frame[name])
    ]
    intensity = pd.DataFrame(index=frame.index)
    for name in candidates:
        values = pd.to_numeric(frame[name], errors="coerce")
        if "decile_1_most_deprived" in name.lower():
            intensity[f"{name}_reversed"] = 11.0 - values
        else:
            intensity[name] = values
    if intensity.empty:
        return pd.DataFrame(), pd.DataFrame()
    pooled = pd.concat([frame[scores], intensity], axis=1).corr(method="spearman").loc[scores, intensity.columns].reset_index(names="score")
    rows = []
    scopes = [("Pooled", frame.index), *[(str(borough), group.index) for borough, group in frame.groupby("borough")]]
    for scope, group_index in scopes:
        matrix = pd.concat([frame.loc[group_index, scores], intensity.loc[group_index]], axis=1).corr(method="spearman").loc[scores, intensity.columns]
        for score in scores:
            for variable in intensity.columns:
                rows.append({"scope": scope, "score": score, "indicator": variable, "spearman_rho": matrix.loc[score, variable]})
    return pooled, pd.DataFrame(rows)


def spatial_models(run: ModelRun, geometry: gpd.GeoDataFrame, k: int, permutations: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    subset = geometry.set_index("segment_id").loc[run.sample.index if run.sample.index.name == "segment_id" else geometry.loc[run.sample.index, "segment_id"]]
    weights = spatial_weights(subset, k)
    response = run.response.to_numpy(dtype=float).reshape((-1, 1))
    design = run.design.drop(columns="const", errors="ignore")
    rows, coefficients = [], []
    for model_id, model_type, model_class in (("SAR", "spatial_lag", spreg.ML_Lag), ("SEM", "spatial_error", spreg.ML_Error)):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                fitted = model_class(response, design.to_numpy(), w=weights, method="LU", name_y=run.outcome, name_x=list(design.columns))
            residual = np.asarray(fitted.u).ravel()
            residual_moran = Moran(residual, weights, permutations=permutations)
            rows.append(
                {
                    "model_id": model_id,
                    "model_type": model_type,
                    "status": "success",
                    "n": len(response),
                    "aic": clean_number(getattr(fitted, "aic", np.nan)),
                    "bic": clean_number(getattr(fitted, "schwarz", np.nan)),
                    "pseudo_r_squared": clean_number(getattr(fitted, "pr2", np.nan)),
                    "residual_moran_i": clean_number(residual_moran.I),
                    "residual_moran_p": clean_number(residual_moran.p_sim),
                }
            )
            names = list(getattr(fitted, "name_x", []))
            betas = np.asarray(fitted.betas).ravel()
            z_stats = list(getattr(fitted, "z_stat", []))
            for index, beta in enumerate(betas):
                z_value, p_value = z_stats[index] if index < len(z_stats) else (np.nan, np.nan)
                coefficients.append(
                    {
                        "model_id": model_id,
                        "term": names[index] if index < len(names) else f"beta_{index}",
                        "coefficient": clean_number(beta),
                        "z_stat": clean_number(z_value),
                        "p_value": clean_number(p_value),
                    }
                )
        except Exception as exc:
            rows.append({"model_id": model_id, "model_type": model_type, "status": "failed", "error_type": type(exc).__name__})
    return pd.DataFrame(rows), pd.DataFrame(coefficients)


def write_table(frame: pd.DataFrame, directory: Path, name: str) -> None:
    frame.to_csv(directory / name, index=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/pipeline.yml")
    parser.add_argument("--input")
    parser.add_argument("--output")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)
    analysis_cfg = cfg["analysis"]
    input_path = project_path(args.input or cfg["paths"]["analysis_segments"])
    output = project_path(args.output or cfg["paths"]["analysis_output"])
    tables = output / "tables"
    spatial_directory = output / "spatial"
    tables.mkdir(parents=True, exist_ok=True)
    spatial_directory.mkdir(parents=True, exist_ok=True)
    frame = gpd.read_file(input_path, layer="segment_open_covariates")
    require_columns(frame, ["segment_id", "borough", "PSSI_s", "EVIS_s", "SL_s", "geometry"], "analysis segments")
    frame["segment_id"] = frame["segment_id"].astype(str)
    frame = frame.set_index("segment_id", drop=False)
    outcome = analysis_cfg["outcome"]
    seed = int(analysis_cfg["random_seed"])
    np.random.seed(seed)

    summary = borough_summary(frame, float(analysis_cfg["low_score_threshold"]))
    write_table(summary, tables, "borough_summary.csv")

    local, global_moran = local_moran(
        frame,
        outcome,
        int(analysis_cfg["knn"]),
        int(analysis_cfg["permutations"]),
        seed,
    )
    write_table(local, spatial_directory, "local_moran.csv")
    if "income_score_rate" in frame.columns:
        priority = priority_typology(frame, outcome, "income_score_rate")
    else:
        priority = frame[["segment_id", "borough", outcome]].copy()
        priority["priority_typology"] = "Unavailable: income_score_rate missing"
    priority = priority.merge(local[["segment_id", "local_moran_quadrant", "local_moran_p"]], on="segment_id", how="left")
    priority["strict_priority"] = (
        priority["priority_typology"].eq("High deprivation + low score")
        & priority["local_moran_quadrant"].eq("LL")
    ).astype(int)
    write_table(priority, tables, "priority_typology.csv")

    controls = [name for name in ("log_segment_length_m", "log_evidence_mass_per_100m", "valid_image_rate") if name in frame]
    segment_predictors = [name for name in analysis_cfg["selected_segment_predictors"] if name in frame]
    m0 = fit_model(frame, "M0", outcome, controls)
    m7 = fit_model(frame, "M7", outcome, segment_predictors)
    segment_coefficients = pd.concat([coefficient_table(m0), coefficient_table(m7)], ignore_index=True)
    segment_fits = pd.DataFrame([model_fit(m0), model_fit(m7)])
    write_table(segment_coefficients, tables, "segment_ols_coefficients.csv")
    write_table(segment_fits, tables, "segment_model_comparison.csv")

    geometry_for_model = frame.loc[m7.sample.index]
    spatial_fit, spatial_coefficients = spatial_models(
        m7,
        geometry_for_model,
        int(analysis_cfg["knn"]),
        int(analysis_cfg["permutations"]),
    )
    write_table(spatial_fit, tables, "spatial_model_comparison.csv")
    write_table(spatial_coefficients, tables, "spatial_model_coefficients.csv")

    lsoa_predictors = [name for name in analysis_cfg["selected_lsoa_predictors"] if name in frame]
    if "lsoa21cd" in frame and frame["lsoa21cd"].notna().any():
        lsoa = aggregate_lsoa(frame, lsoa_predictors)
        write_table(lsoa, tables, "lsoa_aggregate.csv")
        l0 = fit_model(lsoa, "L0", "mean_PSSI_s", [name for name in controls if name in lsoa], weights=lsoa["n_segments"])
        l4 = fit_model(lsoa, "L4", "mean_PSSI_s", lsoa_predictors, weights=lsoa["n_segments"])
        write_table(pd.concat([coefficient_table(l0), coefficient_table(l4)], ignore_index=True), tables, "lsoa_wls_coefficients.csv")
        write_table(pd.DataFrame([model_fit(l0), model_fit(l4)]), tables, "lsoa_model_comparison.csv")
    else:
        lsoa = pd.DataFrame()

    robustness_rows, robustness_coefficients = [], []
    for alternative in ("PSSI_s", "PSSI_open", "RVSI_s", "EVIS_s", "PSSI_eq", "PSSI_main"):
        if alternative not in frame or frame[alternative].notna().sum() < 20:
            continue
        run = fit_model(frame, f"ROBUST_{alternative}", alternative, segment_predictors)
        robustness_rows.append(model_fit(run))
        robustness_coefficients.append(coefficient_table(run))
    write_table(pd.DataFrame(robustness_rows), tables, "sensitivity_model_comparison.csv")
    write_table(pd.concat(robustness_coefficients, ignore_index=True), tables, "sensitivity_coefficients.csv")

    scores = [name for name in ("PSSI_s", "EVIS_s", "SL_s", "RVSI_s") if name in frame]
    correlations, correlations_by_area = deprivation_correlations(frame, scores)
    write_table(correlations, tables, "spearman_correlations.csv")
    write_table(correlations_by_area, tables, "spearman_correlations_by_area.csv")

    osm_candidates = [name for name in frame.columns if name.startswith("osm_") and pd.api.types.is_numeric_dtype(frame[name])]
    osm_rows = []
    for candidate in osm_candidates:
        run = fit_model(frame, f"OSM_{candidate}", outcome, [*segment_predictors, candidate])
        fit = model_fit(run)
        osm_rows.append({"candidate": candidate, **fit})
    if osm_rows:
        write_table(pd.DataFrame(osm_rows).sort_values("bic"), tables, "osm_sensitivity.csv")

    mapped = frame.reset_index(drop=True).merge(
        priority[["segment_id", "priority_typology", "strict_priority", "local_moran_quadrant", "local_moran_p"]],
        on="segment_id",
        how="left",
    )
    gpd.GeoDataFrame(mapped, geometry="geometry", crs=frame.crs).to_file(spatial_directory / "analysis_segments.gpkg", layer="analysis_segments", driver="GPKG")
    metadata = {
        "segment_rows": len(frame),
        "lsoa_rows": len(lsoa),
        "outcome": outcome,
        "segment_predictors_used": segment_predictors,
        "lsoa_predictors_used": lsoa_predictors,
        "knn": int(analysis_cfg["knn"]),
        "permutations": int(analysis_cfg["permutations"]),
        **global_moran,
    }
    write_json(metadata, output / "run_metadata.json")
    print(f"Analysis complete: {len(frame):,} segments; outputs in {output}")


if __name__ == "__main__":
    main()
