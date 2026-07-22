# Repository boundary

I am making the method and my own code open, but not every file that passed through the dissertation workflow. Some inputs belong to third-party providers, and some are unnecessary for understanding the analysis.

## Included

- Python code for data preparation, scoring, spatial analysis and figures.
- The visual-audit prompt, JSON schema and model identifier.
- Configuration examples, expected record counts and tests for the core formulas.
- Direct links to the public data sources.
- Documentation of the segment-level outputs that can be produced locally.

## Left out

- Google Street View images, crops, thumbnails and caches.
- API keys, signed URLs, private storage paths and service request logs.
- Raw borough lamp coordinates and council asset identifiers.
- Local copies of OSM, OS OpenData, TfL, GLA, ONS, Nomis and DfT downloads.
- Intermediate files, editable dissertation drafts and private working notes.

These omissions are deliberate. They keep the repository within the providers' terms and avoid turning a dissertation code repository into a duplicate data archive.

## If somebody wants to rebuild it

The public datasets can be downloaded from [DATA_SOURCES.md](DATA_SOURCES.md). The three street-light files must be obtained from their WhatDoTheyKnow request pages and kept locally. A new Street View collection must be made under the collector's own account and the applicable Google terms; the resulting images must not be added to this repository.

The cleaned segment framework may be released with proper OpenStreetMap attribution. Third-party inputs remain under their original licences, while the MIT licence applies only to my code and documentation.
