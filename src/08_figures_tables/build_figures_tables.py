#!/usr/bin/env python3
"""Regenerate manuscript maps, statistical figures and tables from analysis outputs."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
import numpy as np
import pandas as pd
import seaborn as sns

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline_common import load_config, project_path, write_json


BOROUGH_LABELS = {
    "HACKNEY": "Hackney",
    "SOUTHWARK": "Southwark",
    "RICHMOND_UPON_THAMES": "Richmond upon Thames",
}
TYPOLOGY_COLORS = {
    "High deprivation + low score": "#d73027",
    "High deprivation + high score": "#fc8d59",
    "Low deprivation + high score": "#1a9850",
    "Low deprivation + low score": "#91cf60",
    "Other": "#d9d9d9",
}
MORAN_COLORS = {
    "HH": "#b2182b",
    "LH": "#ef8a62",
    "LL": "#2166ac",
    "HL": "#67a9cf",
    "Not significant": "#d9d9d9",
}


def save_figure(figure: plt.Figure, directory: Path, stem: str) -> None:
    figure.savefig(directory / f"{stem}.png", dpi=300, bbox_inches="tight", facecolor="white")
    figure.savefig(directory / f"{stem}.pdf", bbox_inches="tight", facecolor="white")
    plt.close(figure)


def blank_axis(axis: plt.Axes) -> None:
    axis.set_axis_off()
    axis.set_aspect("equal")


def study_area_figure(frame: gpd.GeoDataFrame, directory: Path) -> None:
    figure, axis = plt.subplots(figsize=(8.2, 8.2))
    for borough, group in frame.groupby("borough"):
        group.plot(ax=axis, linewidth=0.35, label=BOROUGH_LABELS.get(borough, borough))
        centre = group.geometry.union_all().centroid
        axis.annotate(BOROUGH_LABELS.get(borough, borough), (centre.x, centre.y), xytext=(5, 5), textcoords="offset points", fontsize=9)
    axis.legend(frameon=False, loc="best")
    axis.set_title("Study street networks")
    blank_axis(axis)
    save_figure(figure, directory, "figure_1_study_area")


def workflow_figure(directory: Path) -> None:
    labels = [
        "OSM street network\n6,228 segments",
        "50 m sampling\n22,565 points × 4 views",
        "Visible-evidence audit\nstructured JSON + NA",
        "Image → point → segment\nEVIS and evidence mass",
        "Open-data joins\nSL and covariates",
        "PSSI, equity and\nspatial analysis",
    ]
    figure, axis = plt.subplots(figsize=(12, 3.1))
    axis.set_xlim(0, len(labels))
    axis.set_ylim(0, 1)
    axis.axis("off")
    for index, label in enumerate(labels):
        x = index + 0.08
        box = FancyBboxPatch((x, 0.31), 0.84, 0.38, boxstyle="round,pad=0.025", facecolor="#f2f5f7", edgecolor="#4c6272", linewidth=1.2)
        axis.add_patch(box)
        axis.text(x + 0.42, 0.50, label, ha="center", va="center", fontsize=8.5)
        if index < len(labels) - 1:
            axis.add_patch(FancyArrowPatch((x + 0.86, 0.50), (x + 1.06, 0.50), arrowstyle="-|>", mutation_scale=12, color="#4c6272"))
    axis.set_title("Research workflow", pad=12)
    save_figure(figure, directory, "figure_2_research_workflow")


def score_panels(frame: gpd.GeoDataFrame, score: str, directory: Path, stem: str, title: str) -> None:
    boroughs = list(BOROUGH_LABELS)
    figure, axes = plt.subplots(1, 3, figsize=(14, 5.1))
    normal = Normalize(0, 100)
    for axis, borough in zip(axes, boroughs):
        group = frame.loc[frame.borough.eq(borough)]
        group.plot(column=score, cmap="viridis", norm=normal, linewidth=0.75, ax=axis)
        axis.set_title(BOROUGH_LABELS[borough])
        blank_axis(axis)
    colourbar = figure.colorbar(plt.cm.ScalarMappable(norm=normal, cmap="viridis"), ax=axes, fraction=0.025, pad=0.015)
    colourbar.set_label(score)
    figure.suptitle(title, y=0.98)
    save_figure(figure, directory, stem)


def equity_figure(frame: gpd.GeoDataFrame, directory: Path) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(14, 6.2))
    for category, color in TYPOLOGY_COLORS.items():
        selected = frame.loc[frame.priority_typology.eq(category)]
        if not selected.empty:
            selected.plot(ax=axes[0], color=color, linewidth=0.7, label=category)
    axes[0].set_title("(a) Within-borough equity typology")
    blank_axis(axes[0])
    axes[0].legend(frameon=False, fontsize=7, loc="lower left")
    richmond = frame.loc[frame.borough.eq("RICHMOND_UPON_THAMES")]
    richmond.plot(ax=axes[1], color="#dedede", linewidth=0.45)
    concern = richmond.loc[richmond.priority_typology.eq("High deprivation + low score")]
    strict = richmond.loc[richmond.strict_priority.eq(1)]
    if not concern.empty:
        concern.plot(ax=axes[1], color="#d73027", linewidth=1.05, label="High deprivation + low score")
    if not strict.empty:
        strict.plot(ax=axes[1], color="#111111", linewidth=1.7, label="Also significant LL cluster")
    axes[1].set_title("(b) Richmond strict-priority overlap")
    blank_axis(axes[1])
    if axes[1].get_legend_handles_labels()[0]:
        axes[1].legend(frameon=False, fontsize=8, loc="lower left")
    figure.suptitle("Combined equity screening")
    save_figure(figure, directory, "figure_5_equity_screen")


def correlation_figure(table: pd.DataFrame, directory: Path, by_area: pd.DataFrame | None = None) -> None:
    if table.empty or len(table.columns) < 2:
        return
    matrix = table.set_index("score").apply(pd.to_numeric, errors="coerce")
    if by_area is not None and not by_area.empty:
        scopes = [scope for scope in ("Pooled", "HACKNEY", "SOUTHWARK", "RICHMOND_UPON_THAMES") if scope in set(by_area["scope"])]
        figure, axes = plt.subplots(2, 2, figsize=(max(11, 0.7 * matrix.shape[1]), 8.2), constrained_layout=True)
        for axis, scope in zip(axes.flat, scopes):
            scope_table = by_area.loc[by_area.scope.eq(scope)].pivot(index="score", columns="indicator", values="spearman_rho")
            sns.heatmap(scope_table, cmap="vlag", center=0, vmin=-0.5, vmax=0.5, annot=True, fmt=".2f", linewidths=0.3, ax=axis, cbar=scope == "Pooled")
            axis.set_title(BOROUGH_LABELS.get(scope, scope))
            axis.set_xlabel("")
            axis.set_ylabel("")
            axis.tick_params(axis="x", rotation=40)
    else:
        figure, axis = plt.subplots(figsize=(max(8, 0.65 * matrix.shape[1]), 4.2))
        sns.heatmap(matrix, cmap="vlag", center=0, vmin=-0.5, vmax=0.5, annot=True, fmt=".2f", linewidths=0.4, ax=axis, cbar_kws={"label": "Spearman rho"})
        axis.set_xlabel("")
        axis.set_ylabel("")
        axis.set_title("Score–deprivation correlations")
        axis.tick_params(axis="x", rotation=40)
    save_figure(figure, directory, "figure_a1_spearman_correlations")


def local_moran_figure(frame: gpd.GeoDataFrame, directory: Path) -> None:
    quadrants = ["HH", "LH", "LL", "HL"]
    figure, axes = plt.subplots(2, 2, figsize=(11, 10))
    for axis, quadrant in zip(axes.flat, quadrants):
        frame.plot(ax=axis, color="#e6e6e6", linewidth=0.35)
        selected = frame.loc[frame.local_moran_quadrant.eq(quadrant)]
        if not selected.empty:
            selected.plot(ax=axis, color=MORAN_COLORS[quadrant], linewidth=0.9)
        axis.set_title(quadrant)
        blank_axis(axis)
    figure.suptitle("Significant Local Moran clusters and outliers")
    save_figure(figure, directory, "figure_a2_local_moran")


def component_figure(frame: gpd.GeoDataFrame, directory: Path) -> None:
    boroughs = list(BOROUGH_LABELS)
    figure, axes = plt.subplots(2, 3, figsize=(14, 9.4))
    normal = Normalize(0, 100)
    for row, score in enumerate(("EVIS_s", "SL_s")):
        for axis, borough in zip(axes[row], boroughs):
            frame.loc[frame.borough.eq(borough)].plot(column=score, cmap="viridis", norm=normal, linewidth=0.65, ax=axis)
            axis.set_title(f"{BOROUGH_LABELS[borough]} — {score}")
            blank_axis(axis)
    colourbar = figure.colorbar(plt.cm.ScalarMappable(norm=normal, cmap="viridis"), ax=axes, fraction=0.02, pad=0.01)
    colourbar.set_label("Score")
    figure.suptitle("Visual and street-light score components")
    save_figure(figure, directory, "figure_a3_component_maps")


def coefficient_figure(table: pd.DataFrame, directory: Path) -> None:
    selected = table.loc[table.model_id.isin(["M7", "L4"]) & ~table.term.str.startswith(("const", "borough_"), na=False)].copy()
    if selected.empty:
        return
    selected["label"] = selected["model_id"] + ": " + selected["term"]
    selected = selected.sort_values("coefficient")
    figure, axis = plt.subplots(figsize=(8.5, max(4.5, len(selected) * 0.34)))
    positions = np.arange(len(selected))
    axis.errorbar(
        selected["coefficient"],
        positions,
        xerr=[selected["coefficient"] - selected["ci_low"], selected["ci_high"] - selected["coefficient"]],
        fmt="o",
        color="#2c3e50",
        ecolor="#7f8c8d",
        capsize=2,
    )
    axis.axvline(0, color="#999999", linewidth=0.8)
    axis.set_yticks(positions, selected["label"])
    axis.set_xlabel("Standardised coefficient (95% CI)")
    axis.set_title("Selected association models")
    sns.despine(ax=axis)
    save_figure(figure, directory, "model_coefficients")


def methods_tables(directory: Path) -> list[Path]:
    audit_targets = pd.DataFrame(
        [
            ["sidewalk_serviceability_coarse", "Main", "0 poor; 1 limited or mixed; 2 serviceable; NA", "Coarse visible footway serviceability"],
            ["visible_drainage_feature_presence", "Main", "0 not visible in auditable context; 1 visible; NA", "Visible feature presence only"],
            ["kerb_ramp_or_flush_transition_presence", "Secondary", "0 not visible in auditable context; 1 visible; NA", "Candidate pedestrian transition"],
            ["tactile_paving_presence", "Exploratory", "0 not visible in auditable context; 1 visible; NA", "Recognisable tactile surface"],
        ],
        columns=["indicator", "status", "coding", "permitted_claim"],
    )
    scoring = pd.DataFrame(
        [
            ["EVIS_s", "0.50 sidewalk + 0.25 drainage + 0.125 kerb + 0.125 tactile", "Valid-target and evidence-mass weighting"],
            ["RVSI_s", "0.70 sidewalk + 0.30 drainage", "Robustness output"],
            ["SL_s", "0.50 density percentile + 0.50 inverse-gap percentile", "Zero for no linked lamps"],
            ["PSSI_s", "0.80 EVIS_s + 0.20 SL_s", "Primary segment criterion"],
            ["PSSI_open", "0.70 EVIS_s + 0.30 SL_s", "Higher-lighting sensitivity"],
        ],
        columns=["measure", "formula", "role"],
    )
    prompt_structure = pd.DataFrame(
        [
            ["Task framing", "Audit one image using visible street evidence"],
            ["Output discipline", "One schema-valid JSON object"],
            ["Missingness", "NA is not auditable; zero is an auditable negative"],
            ["Confidence", "Uncertainty changes confidence, not the observed score"],
            ["Safeguards", "Exclude category errors such as driveways counted as pedestrian ramps"],
        ],
        columns=["component", "operational_rule"],
    )
    outputs = []
    for name, table in (("table_2_audit_targets.csv", audit_targets), ("table_3_scoring_framework.csv", scoring), ("table_a5_prompt_structure.csv", prompt_structure)):
        path = directory / name
        table.to_csv(path, index=False)
        outputs.append(path)
    return outputs


def copy_analysis_tables(source: Path, destination: Path) -> list[Path]:
    outputs = []
    for path in sorted(source.glob("*.csv")):
        target = destination / path.name
        shutil.copy2(path, target)
        outputs.append(target)
    return outputs


def excel_workbook(csv_files: list[Path], output: Path) -> None:
    used: set[str] = set()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for path in csv_files:
            base = path.stem[:31]
            sheet = base
            suffix = 1
            while sheet in used:
                suffix += 1
                sheet = f"{base[:27]}_{suffix}"
            used.add(sheet)
            pd.read_csv(path).to_excel(writer, sheet_name=sheet, index=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/pipeline.yml")
    parser.add_argument("--analysis-output")
    parser.add_argument("--output")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)
    source = project_path(args.analysis_output or cfg["paths"]["analysis_output"])
    output = project_path(args.output or cfg["paths"]["figures_output"])
    figures = output / "figures"
    tables = output / "tables"
    figures.mkdir(parents=True, exist_ok=True)
    tables.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="white", context="paper", font_scale=1.0)
    frame = gpd.read_file(source / "spatial/analysis_segments.gpkg", layer="analysis_segments")

    study_area_figure(frame, figures)
    workflow_figure(figures)
    score_panels(frame, "PSSI_s", figures, "figure_4_pssi_distribution", "Segment-level PSSI")
    equity_figure(frame, figures)
    local_moran_figure(frame, figures)
    component_figure(frame, figures)
    correlation_path = source / "tables/spearman_correlations.csv"
    if correlation_path.exists():
        by_area_path = source / "tables/spearman_correlations_by_area.csv"
        correlation_figure(pd.read_csv(correlation_path), figures, pd.read_csv(by_area_path) if by_area_path.exists() else None)

    csv_files = copy_analysis_tables(source / "tables", tables)
    csv_files.extend(methods_tables(tables))
    segment_coefficients = source / "tables/segment_ols_coefficients.csv"
    lsoa_coefficients = source / "tables/lsoa_wls_coefficients.csv"
    if segment_coefficients.exists():
        coefficients = pd.read_csv(segment_coefficients)
        if lsoa_coefficients.exists():
            coefficients = pd.concat([coefficients, pd.read_csv(lsoa_coefficients)], ignore_index=True)
        coefficient_figure(coefficients, figures)
    excel_workbook(csv_files, tables / "manuscript_tables.xlsx")
    write_json(
        {
            "figure_files": len(list(figures.glob("*"))),
            "csv_tables": len(csv_files),
            "streetview_validation_montage_generated": False,
            "validation_note": "The image-based disagreement montage is excluded because the underlying Street View images are not redistributable.",
        },
        output / "build_summary.json",
    )
    print(f"Wrote figures and tables to {output}")


if __name__ == "__main__":
    main()
