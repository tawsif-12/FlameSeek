# FlameSeek website — harmonized record inside the existing site

Date: 2026-11-02. Decisions: D75 (data and API), D76 (integration) and D77 (Search flow) in
`docs/decisions.md`. Run instructions: README, "Harmonized record pages — run locally".

## What changed in this revision

The first version replaced the existing site with a separate light-themed one. That has
been removed:

- `frontend/src/site/` deleted;
- `main.tsx`, `vite.config.ts` and `package.json` restored from git;
- Home is back at `/`.

The harmonized-record work is now built inside the existing FlameSeek frontend, using its
own theme and page structure. Existing pages (Home, FireNow, Search, Fire Memory,
Fire DNA, Sources) are unchanged apart from small additive edits:

| File | Addition |
|---|---|
| `main.tsx` | 3 routes, 3 nav links, language toggle |
| `HomePage.tsx` | one new section |
| `vite.config.ts` | proxy entries for the snapshot API |

## Pages and navigation (after D77)

Header: **FireNow** (your live 3D globe; the main map) · Search · **Methodology** · **About** · **বাংলা**/EN.

| Page | How you get there | Built with |
|---|---|---|
| Home — "Harmonized Record" section | `/` | `oc-section`, `oc-dashboard-panel`, `oc-hud-row`; first card links to FireNow |
| Fire Events for a place | Search → choose a place → card **04 Fire Events** | `space-page` layout, glass cards, react-leaflet + Esri imagery |
| Methodology & Validation | header | `space-page` layout, `method-card` steps, Plotly charts |
| About (placeholder) | header | `space-page` layout, `method-card` team cards |

## Screenshots

All are in `outputs/website_screenshots/`, captured from the running dev server (port 5173). The Fire Events
images come from a scripted browser run: Search → "Bangladesh" → Fire Events → click the strongest event.

| View | File |
|---|---|
| Home, Harmonized Record section | ![Home section](website_screenshots/01_home_record_section.png) |
| Search with a place chosen; card 04 is Fire Events | ![Search](website_screenshots/02b_search_destinations.png) |
| Fire Events for Bangladesh: place outline, events, named list | ![Fire Events](website_screenshots/02c_fire_events_place.png) |
| Clicking an event: zoom to its true outline + details | ![Event](website_screenshots/03_fire_events_panel.png) |
| Fire Events opened without a place: prompt to search | ![Prompt](website_screenshots/02a_fire_events_needs_place.png) |
| Methodology & Validation (full page) | ![Methodology](website_screenshots/04_methodology.png) |
| About | ![About](website_screenshots/05_about.png) |

## Content (all numbers from files on disk, each with label and status)

**Home section**
- 138,576 fire events in current_2026 (`/meta`); window 2026-10-29 → 2026-11-02; last
  observation 2026-11-02 07:48 UTC.
- 618,185 raw rows → 545,537 clean detections → 138,576 events
  (`outputs/phase1_report.md`). The older batch figure, 138,518, is superseded.
- Cards link to Fire Events, Methodology and About.
- Provenance chips show the window, data version and last observation.

**Fire Events (for a searched place)**
- Every event of the window inside the place (Bangladesh: 12 events), from the new `/fires` endpoint.
- **Map:** the place's dashed outline, and each event drawn as its true burned-ground outline. Zoomed out,
  a small outline gets a thick border in its intensity colour so it stays visible. There are no stand-in dots.
- **Named list, strongest first:** intensity word, time, satellites, peak FRP. Clicking a row zooms to that
  fire's outline and shows its details: platforms, sensors, last seen, confidence, trend, max FRP per sensor,
  area, honesty notes.
- The honesty notes stay on the map; a window selector is included.

**Methodology**
- Six pipeline steps with "show the math".
- Energy conservation: 5,259,083.28 MW before and after; 1.77e-16; pass.
- Aqua drift chart: 13:27 (2016) → 15:48 (2026).
- Calibration v1 vs v2 charts and table. A one-sentence explanation of why they differ is
  generated from the measured drift.
- Detection limits:

  | Detection limit | Value |
  |---|---|
  | MODIS F50 at nadir, 2016 | 17.3 MW |
  | Himawari F50, Bangladesh | 71.9 MW |
  | Himawari F50, near nadir | 13.4 MW |

- Geostationary assignment map.
- Northern Australia investigation, marked "method demonstration – not applied".
- Awaiting-data list and data sources.

## Design and accessibility

- **Theme.** Uses the project's theme tokens (`--oc-*`, `--sp-*`, mission font), glass
  cards and pill eyebrows. The new stylesheet `src/harmonized.css` only adds layout for the
  new pieces.
- **Colours** were validated for the dark surface with the dataviz palette validator:
  - intensity ordinal ramp `#8f3a14 → #d4561f → #ff8a4c → #ffc78a` (brighter = more power);
  - chart pair `#3987e5` / `#d95926`.
- **Labels.** Every colour has a text label. Each chart has a hover tooltip and a
  "Show as table" view.
- **Provenance.** Each new page shows `data_version` and `last_observation_time`.
  Existing live-FIRMS pages are not stamped with snapshot provenance, because they show
  different (live) data.

## Fire Intelligence now runs the FlameSeek pipeline (D80)

Searching a place and opening its Fire Intelligence page now processes that place's history
with the same pipeline as the study windows. Before, the history came only from the older
Fire Memory harmonization.

**What the page does**

1. Live hotspots and the 12-month quick look appear first (seconds).
2. The Fire Memory 5-year history follows (seconds when saved).
3. A fourth step, **FlameSeek pipeline**, then:
   - downloads the place's FIRMS archive (MODIS + Suomi-NPP), reusing the cached NASA files;
   - runs footprints → events → energy-conserving grid;
   - shows each stage's progress.
4. When it finishes, these answers switch to the pipeline and name it as their source:
   - history;
   - where hotspots repeat;
   - seasons;
   - change over time;
   - whether current activity is unusual;
   - future risk.

**Labels on every year**

The reliability answer labels each year's calibration from the measured Aqua orbit drift:

| Years (Sundarbans run) | Label |
|---|---|
| 2021–2023 | synchronized era, calibration v2 (validated on 2016) |
| 2024–2026 | drift-affected, calibration v1 (provisional) |

The latent fire rate (λ) is shown as *awaiting data*. It needs historical satellite orbits
(TLEs) for these years.

**One rule for "inside the place"**

Detections, events (by centroid) and hotspot cells all count only fires inside the place
outline. An earlier draft kept 0.1° grid cells whose centre was inside. The map then showed
edge cells with fire on up to 5 days, while the history counted 1 event. The map is now built
from the same inside detections.

**Sundarbans, 5 years (2021-11-02 → 2026-11-01)**

| | Forest outline (from search) | Rectangle around it |
|---|---|---|
| Fire events | 1 (27 Feb 2024) | 37 |
| Clean detections | 1 | 40 |
| Energy conserved on grid | pass | pass |
| Run time, first visit | ≈ 2.5–3 min | ≈ 110 s |

Most fire near the Sundarbans is on the farmland around the forest, not inside it. Future
risk stays withheld: it needs 5 complete years, and the 5-year choice gives 4. The page offers
10 years.

**Pipeline fixes found on the way** (each now has a test):

- **Two-detection days.** With pandas 3, two int64 hash ids of opposite sign made an
  overflowing, empty RangeIndex. `tests/test_place_run.py` forces such ids; it fails on the
  old code and passes on the fix.
- **Days with every detection outside the place.** The quality step returned tables instead
  of columns (`tests/test_quality_empty_day.py`).
- **Finalize.** Month partitions with mixed types are now written as text.

Screenshot: `website_screenshots/08_area_intelligence_pipeline.png`.

## Tests and checks

- 131 harmonization and 87 backend tests pass (including the place pipeline job and the end-to-end place run).
- TypeScript type-check: 0 errors.
- All routes return 200 on the dev server. The Search → Fire Events and Search → Fire Intelligence (with the pipeline step) flows were run end-to-end in a browser.

## Known limits

- **Production build.** `npm run build` still could not be verified on this machine
  because of low free memory. It is not caused by these changes, which add no
  dependencies.
- **Leftover dev server.** A dev server from my earlier attempt still runs on port 5180
  (process 24928), serving the removed version. Stopping it was blocked by a permission
  check; close it from Task Manager, or run `Stop-Process -Id 24928` in PowerShell.
- **Bangla.** Bangla covers the new section and pages: interface chrome and fire
  descriptions. Text exported from data files stays English. The Bangla interface
  strings need native review.
