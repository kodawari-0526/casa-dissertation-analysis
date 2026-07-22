# CASA dissertation analysis

This is the code companion to my CASA MSc dissertation on pedestrian-supportive street infrastructure in Hackney, Southwark and Richmond upon Thames.

The dissertation combines a cleaned OpenStreetMap network, Google Street View audits, council street-light inventories and neighbourhood open data. My final working dataset contained 6,228 street segments, 22,565 sample points and 90,260 directional image records.

I have kept this repository fairly small. It contains the processing and analysis code, the audit prompt and schema, and links to the original data providers. It does not contain Street View images, raw council lamp locations or copies of datasets that can be downloaded from their owners. The boundary is explained in [PUBLICATION_BOUNDARY.md](PUBLICATION_BOUNDARY.md).

## Repository layout

The numbered folders follow the order in which I did the work:

1. `src/01_network/` — download and clean the OSM street network;
2. `src/02_sampling/` — place roughly 50 m sample points and calculate four view headings;
3. `src/03_streetview/` — collect panorama metadata and prepare image request parameters;
4. `src/04_vlm_audit/` — run the structured visual audit;
5. `src/05_scoring/` — aggregate image results to points and segments;
6. `src/06_covariates/` — join street lights and the other spatial covariates;
7. `src/07_analysis/` — produce borough summaries, equity screens and statistical models;
8. `src/08_figures_tables/` — rebuild the result tables and maps.

The default paths and the main production settings are in `config/pipeline.yml`. Source links are recorded in [DATA_SOURCES.md](DATA_SOURCES.md).

## Running the code

The scripts are provided so that the method can be inspected and adapted. A complete rerun requires the original public downloads, separately obtained council files and valid access to the two APIs. It is not necessary to repeat the paid image collection simply to read or assess the dissertation.

For a fresh environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run_pipeline.py --dry-run
```

`--dry-run` prints the eight commands without contacting a data provider. Individual stages can be run directly, or a later part of the workflow can be selected, for example:

```bash
python run_pipeline.py --from-stage 05_scoring --to-stage 08_figures_tables
```

The live OSM network and several open-data portals change over time, so a new download may not reproduce the historical feature count exactly. The scripts record the expected dissertation counts in their QA output rather than silently treating a changed count as the same dataset. More detail is in [REPRODUCIBILITY.md](REPRODUCIBILITY.md).

## Licence

The MIT licence covers my code and documentation. Every external dataset keeps its original licence; attribution and reuse notes are collected in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
