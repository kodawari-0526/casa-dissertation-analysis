# CASA dissertation analysis

This repository contains the code, source links and results for my CASA MSc dissertation on pedestrian-supportive street infrastructure in Hackney, Southwark and Richmond upon Thames.

The analysis combines a cleaned OpenStreetMap street network, Google Street View observations, council street-light inventories and open demographic and transport data. Street-view images were sampled at roughly 50 m intervals and the results were aggregated to 6,228 street segments.

## Reproducing the analysis

Create a Python environment, install `requirements.txt`, download the public inputs listed in `DATA_SOURCES.md`, and place them at the paths in `config/covariates.yml`. Council street-light files and Street View images must remain in the ignored `data/restricted/` directory.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run_pipeline.py --dry-run
python run_pipeline.py
```

The stages can also be run separately or resumed from a chosen stage:

```bash
python run_pipeline.py --from-stage 05_scoring --to-stage 08_figures_tables
```

The ordered source tree is:

1. `src/01_network/` — OSM query, cleaning and segment construction.
2. `src/02_sampling/` — 50 m sampling, tangent headings and four views.
3. `src/03_streetview/` — panorama metadata and key-free request manifests.
4. `src/04_vlm_audit/` — Gemini 2.5 Flash prompt, schema, parsing, NA and retries.
5. `src/05_scoring/` — image-to-point-to-segment aggregation and score formulas.
6. `src/06_covariates/` — street lights and neighbourhood, transport and built-environment joins.
7. `src/07_analysis/` — summaries, equity typology, Local Moran's I, OLS, LSOA, SAR/SEM and sensitivity checks.
8. `src/08_figures_tables/` — manuscript figures and tables from saved outputs.

`config/pipeline.yml` holds paths, expected production counts and analysis settings. The expected counts are recorded as QA checks because a live OSM query can change after the dissertation's production run.

## Repository notes

- [Data sources](DATA_SOURCES.md)
- [Third-party licences and acknowledgements](THIRD_PARTY_NOTICES.md)
- [What is and is not included](PUBLICATION_BOUNDARY.md)

The MIT licence applies to my original code and documentation. Third-party data remains subject to the terms of its original provider.

See [REPRODUCIBILITY.md](REPRODUCIBILITY.md) for input contracts and stage outputs.
