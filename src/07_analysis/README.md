# Statistical and spatial analysis

The analysis writes borough summaries, within-borough equity quintiles, a strict priority flag, Local Moran's I, segment OLS models, segment-count-weighted LSOA models, SAR/SEM checks and alternative-score sensitivity models.

Spatial weights use eight nearest segment centroids, row standardisation and 999 permutations. The equity screen defines high deprivation and low PSSI from borough-specific top and bottom quintiles; the strict screen requires this category to overlap a significant low-low Local Moran cluster. These are screening outputs, not causal estimates.
