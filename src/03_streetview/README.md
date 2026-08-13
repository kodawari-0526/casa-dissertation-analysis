# Street View metadata

This stage resolves metadata and panorama IDs for the four requested headings, downloads the corresponding private images and writes `private_images.csv` for the visual-audit stage. Existing non-empty images are reused so an interrupted collection can continue safely. Pass `--metadata-only` to prepare requests without downloading images, or `--refresh-images` to replace an existing local collection. API keys and signed request URLs are never written to the outputs.

The image collection used in the dissertation was made in May 2026. Street View imagery and caches remain under `data/restricted/`, which is excluded from Git; panorama IDs and derived audit rows are handled under the publication boundary.
