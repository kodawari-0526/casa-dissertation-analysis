# Reproducing the workflow

This file records the inputs and stage boundaries I used for the dissertation. It is intended to make the method understandable and reusable; it is not a promise that a new live-data run will recreate the exact 2026 dataset.

## Reference run

The completed analysis used:

- 6,228 cleaned street segments: 1,601 in Hackney, 2,603 in Southwark and 2,024 in Richmond upon Thames;
- 22,565 sample points and four requested directions per point;
- 90,260 directional image records, of which 89,756 contributed a valid visual score;
- Street View imagery collected in May 2026;
- `gemini-2.5-flash` through the Gemini API for the visual audit.

The Street View collection and audit involved paid services. I have therefore documented the requests, prompt, schema, retry logic and aggregation code without republishing the images or suggesting that a reader must pay to repeat the collection.

## Inputs kept outside Git

Before a complete rerun, the paths in `config/pipeline.yml` and `config/covariates.yml` need to point to locally downloaded data. The main local-only inputs are the borough boundary layer, the three council street-light deliveries and a private manifest containing `view_id` and `image_path`.

The Street View and Gemini credentials are read from `GOOGLE_MAPS_API_KEY` and `GEMINI_API_KEY`. They are not written to an output file. Raw lamp records, image files, `.env` files and credentials are ignored by Git.

## What each stage leaves behind

| Stage | Output used by the next stage |
|---|---|
| 01 | cleaned segment GeoPackage and network QA counts |
| 02 | sample-point GeoPackage and four-view CSV |
| 03 | panorama metadata and a request manifest without an API key |
| 04 | schema-checked audit JSONL |
| 05 | image, point and segment visual scores |
| 06 | analysis-ready segment GeoPackage and CSV |
| 07 | descriptive, spatial and model tables |
| 08 | manuscript maps, CSV tables and a workbook |

The network and sampling scripts have an optional `--strict-count` flag. I used the reference counts as a check, but left strict mode off by default because OSM is a live source.

## Main score definitions

`EVIS_s` combines sidewalk, drainage, kerb-transition and tactile-paving evidence with weights 0.50, 0.25, 0.125 and 0.125. A target marked NA is removed from that image's denominator; confidence is carried separately as evidence mass.

`SL_s` is the mean of the within-borough lamp-density percentile and inverse maximum-gap percentile. A segment with no linked lamp receives zero. This is an asset and spacing proxy, not a measurement of illumination or whether a lamp was working.

The dissertation's primary score is `PSSI_s = 0.80 × EVIS_s + 0.20 × SL_s`. The other score variants are sensitivity checks, not alternative headline results.
