# Reproducibility guide

## Production reference counts

The dissertation analysis used 6,228 cleaned street segments, 22,565 sample points and 90,260 directional image rows. Of those image rows, 89,756 contributed a valid visual score. The network is divided into 1,601 Hackney, 2,603 Southwark and 2,024 Richmond upon Thames segments.

The Street View collection was made in May 2026. The visual audit used `gemini-2.5-flash` through the Gemini API. Images are supplied to the model from private storage and are never written to public outputs.

## Local inputs

`config/pipeline.yml` defines the pipeline paths. `config/covariates.yml` defines the downloadable covariate inputs. Before a full run, provide:

- a three-borough boundary layer with a `borough` field;
- the public neighbourhood, deprivation, Census, transport, road, building and greenspace files listed in `DATA_SOURCES.md`;
- the three council street-light deliveries under `data/restricted/streetlights/`;
- a private image manifest with `view_id` and `image_path` after the licensed image collection has been completed.

The two credentials are read only from the `GOOGLE_MAPS_API_KEY` and `GEMINI_API_KEY` environment variables. Neither variable is written to disk by the pipeline. `.env`, credentials, raw street-light data and Street View imagery are ignored by Git.

## Stage contracts

| Stage | Main input | Main output |
|---|---|---|
| 01 | Borough boundaries | Cleaned segment GeoPackage and QA counts |
| 02 | Cleaned segments | Sample-point GeoPackage and four-view CSV |
| 03 | Four-view CSV | Panorama metadata and key-free parameters |
| 04 | Private image manifest | Schema-validated audit JSONL |
| 05 | Audit JSONL and view CSV | Image, point and segment visual scores |
| 06 | Segments, scores and downloaded covariates | Analysis-ready segment GeoPackage and CSV |
| 07 | Analysis-ready segments | Descriptive, spatial and model tables |
| 08 | Stage 07 outputs | Manuscript figures, CSV tables and workbook |

The runner stops on a failed stage. Network and sampling stages write QA JSON files and can enforce the production counts with `--strict-count` when a fixed input snapshot is available.

## Score definitions

`EVIS_s` combines sidewalk, drainage, kerb-transition and tactile-paving evidence using weights 0.50, 0.25, 0.125 and 0.125. Non-auditable targets are removed from the valid-target denominator; confidence contributes to evidence mass.

`SL_s` averages the within-borough percentile of lamp density and the inverse percentile of maximum along-segment gap. Segments with no linked lamps receive zero. It is an asset-provision and spacing-continuity proxy, not a measure of illuminance or operational condition.

The primary final score is:

```text
PSSI_s = 0.80 × EVIS_s + 0.20 × SL_s
```

Alternative visual and lighting weights are saved as sensitivity outputs. All statistical results are associations and screening evidence; they are not causal estimates.
