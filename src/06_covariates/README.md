# Covariate joins

This stage links each line segment to its dominant-overlap LSOA (with a nearest-polygon fallback), then adds IMD, Census, PTAL, transport, high-street, town-centre, building, road, greenspace and traffic measures where those downloaded inputs are available.

Council lamp points are assigned to the nearest analytical segment in the same borough within 15 m. The code derives lamp count, density per 100 m and the largest along-segment gap. The raw council files remain outside the repository; only segment-level derived fields can enter public outputs.
