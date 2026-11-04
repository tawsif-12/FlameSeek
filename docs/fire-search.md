# Fire event search

The Fire Events page sends `POST /fires/search?window=current_2026&limit=2000&offset=0&geometry=true`.
The JSON body contains `bbox: [west, south, east, north]`, optionally a GeoJSON
Polygon or MultiPolygon in `geometry`, and optionally `center: [lon, lat]` together
with `radius_km`. If both shape constraints are supplied, both must match.
The box is the candidate search extent; callers must enclose the entire desired
area in it. The current API rejects antimeridian-crossing boxes.

Search means event **centroid containment**, not intersection of an event footprint.
The backend applies the bounding box, then exact polygon/radius containment before
counting or pagination. Polygon holes are excluded. Results are ordered by
`end_time DESC, fire_id ASC`. `count` is the full matching count and `has_more`
indicates another page. The frontend displays a page strongest first and reports
the full matching count; at most 5000 events are requested for its map.

New snapshots contain `event_spatial_index`, an SQLite R-Tree keyed by event rowid,
and an index for deterministic event ordering. The R-Tree filters candidate points;
double-precision coordinates are rechecked to avoid float32 rounding errors.
Snapshots are immutable after publication, so the index is built before atomic
replacement rather than synchronized using update triggers.

Existing snapshots remain readable using a coordinate-filter fallback. Rebuild
them using the existing `python -m pipeline.snapshot` pipeline command from the
project root to gain the R-Tree. This requires the window's local pipeline artifacts
and pipeline dependencies. No existing snapshot data is modified by this change.

Date filters, keyset pagination, antimeridian support, and footprint-intersection
search are follow-up work. Nominatim's existing cache and request throttling are
unchanged. This change does not alter the separate live NASA hotspot search.
