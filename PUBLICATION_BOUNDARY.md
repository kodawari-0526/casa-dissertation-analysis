# What is and is not included

The repository is intended to make the analysis reproducible without republishing material that belongs to another provider.

## Included

- Analysis and data-processing code.
- Environment and package information needed to rerun the analysis.
- Source links and download instructions for public data.
- The street-segment framework and segment-level analysis data, with OpenStreetMap attribution.
- Prompts and output-field definitions used for the image audit.
- Aggregated results, tables and figures used in the dissertation.

The segment framework is based on a cleaned street network with sample points placed at roughly 50 m intervals. It does not contain the Google Street View image files.

## Not included

- Google Street View images, crops, thumbnails or caches.
- API keys, private cloud-storage details, request logs or signed URLs.
- Raw borough street-light files, individual lamp coordinates or council asset identifiers.
- Copies of raw third-party datasets that can be downloaded from their official source.
- Editable dissertation files, private working notes or local data packages.

## Reproducing the data preparation

1. Build the street network from OpenStreetMap with OSMnx and retain the required attribution.
2. Create sample points along the cleaned segments at roughly 50 m intervals.
3. Obtain street-view images directly from the provider under the provider's terms. Do not redistribute the images.
4. Run the documented image-audit prompt with `gemini-2.5-flash` and aggregate the responses to street segments.
5. Download each borough's street-light file from its public request page and join the lamp locations to the corresponding street segments.
6. Download the remaining demographic, transport and built-environment data from the links in [DATA_SOURCES.md](DATA_SOURCES.md).

Third-party datasets keep their original licences. The repository's MIT licence covers only the original code and documentation.
