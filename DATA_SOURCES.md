# Data sources

The study covers Hackney, Southwark and Richmond upon Thames. It uses 6,228 cleaned street segments, 22,565 sample points and 90,260 directional image records. The links below point to the original providers so that the data can be obtained independently.

## Street network and image audit

### OpenStreetMap

The street network was downloaded from the live OpenStreetMap/Overpass service with OSMnx and then cleaned into undirected street segments. A later OSM query used for sensitivity variables is dated 3 July 2026 in the project manifest.

- [OpenStreetMap copyright and licence](https://www.openstreetmap.org/copyright)
- [Overpass API](https://overpass-api.de/)

OpenStreetMap data is available under ODbL. The segment data in this repository should be credited to **© OpenStreetMap contributors**.

### Google Street View

Street-view images were collected in May 2026 through the [Google Street View Static API](https://developers.google.com/maps/documentation/streetview/policies), using the latest imagery returned by the API at the time. Four views were requested at each sample point.

The images were kept in private cloud storage for processing and were sent directly to the vision-language model. Google Street View images, crops, thumbnails and caches are not included in this repository.

### Vision-language model

The image audit used the Gemini API through Google AI Studio. The model code was [`gemini-2.5-flash`](https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash). Image-level responses were aggregated to sample points and then to street segments.

The repository may include prompts, output fields and segment-level results, but it does not include the source images, private storage locations or API credentials.

## Street-light inventories

I obtained the three borough inventories through requests published on WhatDoTheyKnow. The councils supplied the files through the request pages, and I downloaded them in May 2026. The date shown below is the date of the council response containing the relevant data.

| Borough | Council response date | Public request page |
|---|---:|---|
| Hackney | 18 March 2021 | [Street light location data](https://www.whatdotheyknow.com/request/street_light_location_data_2) |
| Southwark | 25 November 2024 | [Street lighting locations](https://www.whatdotheyknow.com/request/street_lighting_locations_latest_291) |
| Richmond upon Thames | 18 December 2024 | [Street lighting locations](https://www.whatdotheyknow.com/request/street_lighting_locations_latest_252) |

The raw files and lamp coordinates are not reproduced here. Anyone rebuilding the street-light measure should obtain the files from the three request pages, follow the applicable reuse terms and join the lamp locations to the street segments.

## Census, population and deprivation

The following Census 2021 tables were downloaded from Nomis and joined at LSOA level:

| Table | Official download |
|---|---|
| TS007A: Age by five-year bands | [Nomis ZIP](https://www.nomisweb.co.uk/output/census/2021/census2021-ts007a.zip) |
| TS011: Households by deprivation dimensions | [Nomis ZIP](https://www.nomisweb.co.uk/output/census/2021/census2021-ts011.zip) |
| TS038: Disability | [Nomis ZIP](https://www.nomisweb.co.uk/output/census/2021/census2021-ts038.zip) |
| TS045: Car or van availability | [Nomis ZIP](https://www.nomisweb.co.uk/output/census/2021/census2021-ts045.zip) |
| TS052: Occupancy rating for bedrooms | [Nomis ZIP](https://www.nomisweb.co.uk/output/census/2021/census2021-ts052.zip) |
| TS054: Tenure | [Nomis ZIP](https://www.nomisweb.co.uk/output/census/2021/census2021-ts054.zip) |
| TS066: Economic activity status | [Nomis ZIP](https://www.nomisweb.co.uk/output/census/2021/census2021-ts066.zip) |
| TS067: Highest level of qualification | [Nomis ZIP](https://www.nomisweb.co.uk/output/census/2021/census2021-ts067.zip) |

Other statistical sources:

- [English Indices of Deprivation 2025](https://www.gov.uk/government/statistics/english-indices-of-deprivation-2025)
- [ONS LSOA population density](https://www.ons.gov.uk/peoplepopulationandcommunity/populationandmigration/populationestimates/datasets/lowersuperoutputareapopulationdensity)
- [ONS LSOA 2021 Boundaries EW BFC V10](https://geoportal.statistics.gov.uk/datasets/ons::lower-layer-super-output-areas-december-2021-boundaries-ew-bfc-v10-2/about)

ONS, Nomis and government statistical material is published under the Open Government Licence unless the source page states otherwise.

## Transport and accessibility

| Dataset | Official source |
|---|---|
| TfL PTAL 2023, 100 m grid | [ArcGIS item](https://www.arcgis.com/home/item.html?id=0646faf45243463aa04ca685e598f471) |
| TfL PTAL 2015 grid geometry | [London Datastore ZIP](https://data.london.gov.uk/download/24rz6/514d2847-94a8-4b9d-8a70-fdded01719a0/2015%20%20PTALs%20Grid%20Values.zip) |
| TfL Bus Routes | [FeatureServer](https://services1.arcgis.com/YswvgzOodUvqkoCN/arcgis/rest/services/Bus_Routes/FeatureServer) |
| TfL Bus Stops | [FeatureServer](https://services1.arcgis.com/YswvgzOodUvqkoCN/arcgis/rest/services/Bus_Stops/FeatureServer) |
| TfL Stations | [FeatureServer](https://services1.arcgis.com/YswvgzOodUvqkoCN/arcgis/rest/services/TfL_stations/FeatureServer) |
| DfT road-traffic count points and AADF | [Road traffic downloads](https://roadtraffic.dft.gov.uk/downloads) |

## Ordnance Survey OpenData

These products were used to construct built-form, road and green-space variables. The repository links to the official downloads rather than copying the original files.

| Product | Official source |
|---|---|
| OS OpenMap – Local | [Documentation](https://docs.os.uk/os-downloads/products/maps-and-imagery-portfolio/os-openmap-local) · [Downloads API](https://api.os.uk/downloads/v1/products/OpenMapLocal/downloads) |
| OS Open Roads | [Documentation](https://docs.os.uk/os-downloads/products/transport-network-portfolio/os-open-roads) · [Downloads API](https://api.os.uk/downloads/v1/products/OpenRoads/downloads) |
| OS Open Greenspace | [Documentation](https://docs.os.uk/os-downloads/products/land-and-terrain-portfolio/os-open-greenspace) · [Downloads API](https://api.os.uk/downloads/v1/products/OpenGreenspace/downloads) |

## Greater London Authority boundaries

- [GLA High Street Boundaries](https://data.london.gov.uk/dataset/gla-high-street-boundaries-2rq4w)
- [GLA Town Centre Boundaries](https://data.london.gov.uk/dataset/town-centre-boundaries-e55z7)

Both datasets are published through the London Datastore under the licence shown on their source pages.
