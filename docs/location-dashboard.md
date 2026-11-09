# Explore and location dashboards

Explore (`/search`) is a search-only page. A fresh visit clears the previous area
and analysis results. Public Nominatim search is explicit (Search or Enter), not
per-keystroke autocomplete, in accordance with
https://operations.osmfoundation.org/policies/nominatim/. Existing server-side
cache and per-host request limiting remain in use. Results include provider names,
English/Bangla names when supplied, place type, parent context and OSM identity.
Exact name matches precede other provider-ranked results. Point-only results do
not silently become administrative bounding boxes; the user must draw an area.

Selecting a polygon or confirming a custom rectangle, polygon or circle opens
`/location/intelligence`. The desktop sidebar persists while React Router changes
the section (`intelligence`, `now`, `memory`, `dna`, `calendar`, `events`). The
existing feature components and APIs supply the content. Legacy standalone feature
routes remain available. History/DNA request analysis on first dashboard use if
no shared result exists, with the existing progress, coverage and failure states.

`location_id` is an OSM object identifier, or a deterministic boundary fingerprint
for custom areas. The exact AOI is serialized in the URL. Small areas use the
`area` query parameter. Large boundaries use `#area=...` so country polygons do
not overflow HTTP request-header limits. Both forms are self-contained for direct
links, refresh, and browser Back/Forward; no geocoder re-resolution or local-only
boundary lookup is required. Fire Now event links retain all location parameters
and the fragment. Internal feature links stay within the location dashboard.

The route hydrates the shared AOI before mounting a feature. A location-scoped
context keeps that boundary fixed, disables embedded location editors, and stops
an unmounted location's async results from updating shared analysis state. Changing
location clears memory and returns to Explore. Old server jobs may complete, but
their late responses cannot replace the new place's results. A boundary change
remounts location-owned view state. Missing coverage remains distinct from an
observed zero count; no coverage or calibrated result is manufactured by routing.

Desktop collapse preference is saved independently of the location. Collapsed
icons retain accessible names and native tooltips. Below 900px the sidebar becomes
a drawer with a backdrop, Escape dismissal, focus return, focus trapping and
active-section highlighting. The global header stays separate from the sidebar.

## Verification

From `frontend`:

```powershell
npm run test:location
node --test tests/searchRequests.test.mjs
npm run build
```

The DOM suite tests empty Explore, Noakhali across all six sections, refresh on
Fire Events, Back/Forward, changing to Bangladesh, late-response isolation,
collapsed sidebar accessibility, mobile drawer navigation, explicit-search
errors/retry and point-only fallback. Heavy feature renderers are mocked in shell
tests so no NASA jobs or GPU context are needed. A separate test uses the real
Leaflet drawing-event handlers for rectangles, polygons and circles. Real Noakhali
District and Bangladesh provider boundaries were retrieved and checked through
the URL serializer during development. Optional local fixtures are not required
to run the core suite. Backend regression:

```powershell
cd backend
python -m pytest tests/test_location_geocode.py tests/test_saved_area.py tests/test_search_performance.py tests/test_snapshot_api.py
```

The connected browser host was unavailable during this implementation, so these
automated DOM/drawing checks do not substitute for a visual desktop/mobile review.
