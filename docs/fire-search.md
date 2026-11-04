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

## Performance and compatibility

Install the backend requirements, including Shapely. Polygon interiors use prepared
geometry; points near boundaries and invalid polygons retain the original ray
casting rules. Circle searches intersect a conservative spherical bounding box
with the caller's box before the authoritative haversine check. Combined polygon
and circle searches now require both to match (an approved correction of the old
circle-only behavior).

Exact counts are cached for 120 seconds in a bounded process-local cache keyed by
snapshot file identity and a normalized request hash. A first request at any offset
still computes a full count. File replacement or modification invalidates it.
Count caching never substitutes page length or an estimate for the full count.

The page query sorts narrow row IDs before reading payloads. Broad boxes can walk
the event-order index; older snapshots can use their end-time index. EXPLAIN plans
and repeatable benchmarks are in `outputs/search-performance/`.

Default footprints are unchanged. `simplify_footprints=true` opts into topologically
preserving simplification with tolerance `min(0.05, max(0.0005, max(width,height)/4000))`
degrees. This changes only returned footprint detail, never membership, count, or
ordering. Footprints are fetched in batches. Gzip (level 5, minimum 1000 bytes) is
negotiated for `/fires/search` only; the live NASA routes are untouched.

SQLite opens read-only with query-only mode, a 256 MiB mmap ceiling, and an 8 MiB
page cache per connection. Exclusive leases bound concurrent connections to eight.
On POSIX idle connections can be reused. On Windows reuse is off by default because
open SQLite handles block atomic snapshot replacement. Set
`FLAMESEEK_REUSE_SNAPSHOTS=1` only when publication is coordinated with stopping the
API or explicitly draining its pool. `FLAMESEEK_IMMUTABLE_SNAPSHOTS=1` is a separate
opt-in for guaranteed immutable files; it is ignored if WAL/journal sidecars exist.
Never enable immutable mode for in-place-updated databases.

Search logs identify R-Tree/fallback and ordering strategy, count-cache hits, exact
predicate calls, and stage timings. Missing R-Trees emit a warning once per snapshot
identity per hour. Rebuilding is an explicit pipeline operation: the API never adds
indexes to published snapshots. Ensure the local pipeline inputs/dependencies exist,
then run `python -m pipeline.snapshot` from the project root. Stop a Windows server
first if persistent reuse was explicitly enabled.

## Frontend requests

The map retains its 5000-event page limit and full-place search by default. A 250 ms
debounce coalesces rapidly changing queries. AbortController cancels superseded
searches and event-detail requests, and stale responses cannot update the page.
Results are cached by normalized query, window and exported snapshot data version
for 30 seconds (12 entries, conservative 24 MiB serialized-size budget).
Below zoom 8, centroid clusters represent all returned events; zooming in draws
the individual footprints. Clustering does not sample or discard events.

`Search current map view` is opt-in. It intersects the visible bounds with the
selected place's candidate box, retaining the exact polygon/radius constraints.
Counts then describe that intersection, as labeled in the UI. Moving the map
without enabling this option never changes whole-place search results.

Date filters, keyset pagination, antimeridian support, and footprint-intersection
search are follow-up work. Nominatim's existing cache and request throttling are
unchanged. This change does not alter the separate live NASA hotspot search.
