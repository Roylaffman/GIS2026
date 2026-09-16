# WORKPLAN — DSHarnessGIS

> Single source of truth for this project: **what's done, what's next, what's
> installed, and every harness snag we hit** (so tomorrow starts fast).
> Companion to `MODERN_GIS_STACK.md` (the *architecture* plan) and `README.md`
> (the *how-to-run*).

**Project:** Mount Mitchell, NC GIS pipeline — OpenTopography DEM → SerpAPI
POIs → DuckDB (spatial) → H3 → Leaflet / Deck.gl / Kepler.gl web maps.

---

## 0. How to "save work" in this harness (the workflow)

1. **Git commits are the primary save.** The repo lives on local disk at
   `C:\Users\royla\Documents\DSHtest\.git` — it survives session restarts.
   Commit early/often: `git add -A && git commit -m "..."`.
2. **This WORKPLAN.md is the memory.** After every working session, update
   the ✅/⬜ checklists below. This is what lets you resume without me.
3. **Push to GitHub = off-machine backup.** Blocked only on credentials
   (see §8). Once a token is available: `git push -u origin main`.
4. **`.env` holds secrets** and is git-ignored — never commit it.
   `.env.example` documents the required keys with placeholder values.

**To resume tomorrow:** `cd C:\Users\royla\Documents\DSHtest`, read this file,
then run `.\.venv\Scripts\python.exe serve_map.py 8090` to bring the maps back
(root demo `/`, runs hub `/runs.html`, new runs via `quickmap.py`).

---

## 1. Environment — what's installed

### Python 3.11.9 (`.venv`)
| Package | Version | Used by |
|---|---|---|
| duckdb | 1.5.5 | `build_db.py` (spatial SQL) |
| rasterio | 1.4.4 | DEM read, hillshade, COG |
| numpy | 2.4.6 | array math |
| geopandas | 1.1.4 | vector ETL |
| h3 | 4.5.0 | hex binning |
| pyarrow | 25.0.1 | (Geo)Parquet |
| shapely / pyproj / pyogrio | (deps) | geometry / CRS |

### Node v24.20.0 + npm 10.7.0 (`frontend/node_modules`)
| Package | Version | Purpose |
|---|---|---|
| deck.gl | 9.4.0 | WebGL viz (UMD vendored) |
| kepler.gl | 3.2.6 | explorer UI (UMD vendored) |
| react / react-dom | 18.3.1 | kepler.gl runtime |
| redux / react-redux | 4.2.1 / 8.1.3 | kepler.gl store (v4/v8 = UMD builds) |
| styled-components | 6.1.8 | kepler.gl runtime (exact pin) |
| maplibre-gl | 5.24.0 | basemap for deck.gl |
| jsdom | 30.0.1 | headless smoke tests |
| vite | 6.4.3 | **installed but unusable** (esbuild blocked, §2) |

### Services / keys (`.env`)
- `OPENTOPO_API_KEY` ✅ working (DEM fetch)
- `SERPAPI_KEY` ✅ working (POI fetch)
- `MAPBOX_TOKEN` ✅ working (kepler.gl basemap), served via `/config.js`
- `GCS_BUCKET` ⬜ configured but unused so far

---

## 2. Harness snags & workarounds (the knowledge base)

These bit us and will bite again — **do not rediscover them**:

| # | Snag | Symptom | Workaround |
|---|---|---|---|
| 1 | PowerShell schannel TLS broken | `curl`/`Invoke-WebRequest` → `SEC_E_NO_CREDENTIALS` | Use **Python `urllib` or Node** (OpenSSL) for network |
| 2 | Headless Chrome can't launch | sandbox blocks its IPC/named pipes | Can't screenshot pages; verify via `node --check` + jsdom smoke tests; **user views in browser** |
| 3 | esbuild/vite can't spawn native binary | `spawn EPERM` | **No bundler.** Use prebuilt UMD bundles + `<script>` tags |
| 4 | npm postinstall scripts fail | `spawn EPERM` | `npm install --ignore-scripts` |
| 5 | npm cache dir outside sandbox | `EPERM` writing `%APPDATA%\npm-cache` | `$env:npm_config_cache = "...\.npm-cache"` |
| 6 | stray `package.json` at `C:\Users\royla\` | npm installs to wrong root | Always run npm from `frontend/` |
| 7 | DuckDB extension dir outside sandbox | `Access denied` on `~\.duckdb` | `SET extension_directory='data/duckdb_ext'` (done in `build_db.py`) |
| 8 | git credential manager can't run | `sh.exe` `CreateFileMapping` error | Push needs an inline token (§8) |
| 9 | Node 24 + `"type":"module"` | `.js` files treated as ESM | Name CommonJS scripts `.cjs` (e.g. smoke test) |
| 10 | kepler.gl UMD needs 5 browser globals | blank page / "KeplerGl undefined" | Load `React, ReactDOM, Redux, ReactRedux, styled-components` before keplergl (v4/v8 for UMD) |
| 11 | kepler.gl requires Redux `<Provider>` | **blank page** (our #1 bug) | Wrap component in `<Provider store>` + `keplerGlReducer` + `enhanceReduxMiddleware` |
| 12 | kepler.gl basemap is Mapbox | needs token | Token via `/config.js`; data layers work tokenless |
| 13 | `PROJ_LIB` env points at PostGIS old proj.db | `CRSError: proj_create_from_database ... LAYOUT.VERSION.MINOR` | Set `PROJ_LIB` to `.venv\Lib\site-packages\rasterio\proj_data` before rasterio warp/COG |
| 14 | PNG tile writes warn "NotGeoreferenced" | noisy but harmless | filter the warning; XYZ naming carries georef |

---

## 3. What works today ✅

- **DEM fetch** — `fetch_dem.py` → `data/dem_mount_mitchell.tif` (SRTMGL1, 288×288, 937–2029 m)
- **POI fetch** — `fetch_pois.py` → `data/pois.geojson` (20 POIs via SerpAPI Google Maps)
- **DuckDB spatial** — `build_db.py` → `data/gis.duckdb` (nearest-to-summit, AOI-in-count, categories)
- **H3 hexagons** — `build_h3.py` → `web/h3_hexagons.geojson` (17 cells @ res 8)
- **COG** — `make_cog.py` → `data/dem_cog.tif` (tiled + deflate + overviews [2,4,8])
- **Leaflet map** — `/` (hillshade + POI markers + "POIs loaded: 20")
- **Deck.gl map** — `/deck.html` (MapLibre basemap + H3 hexagons + scatterplot)
- **Kepler.gl** — `/kepler.html` (redux wiring + auto-load POIs; jsdom smoke test passes)
- **`/config.js`** — serves `MAPBOX_TOKEN` from `.env` (never baked into HTML)
- **Local server** — `serve_map.py` on `http://127.0.0.1:8090`
- **QUICK-MAPS SYSTEM** — `quickmap.py` turns a place name into a full run:
  - Nominatim (OSM) geocoding — open-source, no key
  - `web/runs/<slug>/` with `run.json`, `pois.geojson`, `h3_hexagons.geojson`, `dem.tif`, `dem_cog.tif`
  - One parameterized `deck.html`/`kepler.html` serves any run via `?run=<slug>`
  - Hub at `/runs.html` lists runs from `web/runs/index.json`
  - Proven runs: `grandfather-mountain` (20 POIs / 18 hex), `hanging-rock` (20 / 19)
- **3D TERRAIN + HILLSHADE on Deck.gl** — `make_terrain.py` generates Mapbox
  terrain-RGB XYZ tiles from any DEM (`tiles/{z}/{x}/{y}.png` + `terrain.json`).
  `deck.html` adds a `raster-dem` source + hillshade layer + `map.setTerrain()`,
  so the DEM now renders as real 3D relief (verified: root summit tile decodes
  0–2028 m, Grandfather 0–1658 m, Hanging Rock 928–1571 m). Wired into
  `quickmap.py` so every new run gets terrain automatically.
- **DASHBOARD view (open-source flood-dashboard equivalent)** — studied the
  geoglypha bat-cave flood dashboard (Mapbox GL JS + Mapbox-hosted terrain +
  hand-authored GeoJSON + Chart.js synthetic cross-section). Built the
  open-source, data-driven equivalent: `make_dashboard.py` writes a `layers.json`
  manifest (any GeoJSON → styled fill/line/circle layer + visibility) and a
  REAL `profile.json` elevation cross-section sampled from the DEM (Mount
  Mitchell 1108–2021 m, Grandfather 1143–1600 m, Hanging Rock 945–1553 m).
  `web/dashboard.html` renders MapLibre terrain + manifest layers + legend
  toggles + Chart.js cross-section. Wired into `quickmap.py`.
- **DATA INSPECTION tool** — `inspect_data.py` loads any vector dataset
  (GeoJSON/Shapefile/GeoParquet/CSV) and reports rows, CRS, bounds (native +
  WGS84), geometry-type breakdown, per-column nulls/uniques/min/max, coordinate
  sanity, and duplicate/empty geometry counts; optional `--out` JSON + `--bounds`
  bbox GeoJSON. (Verified on 20 Grandfather POIs.)
- **DEM / BATHYMETRY ANALYSIS tool** — `analyze_dem.py` auto-detects terrain vs
  bathymetry (values ≤ 0) and reports size/resolution/CRS, min/max/mean/median/std,
  coverage, hypsometry histogram, and real-unit volume (water volume for bathy,
  earthwork volume for terrain). Writes slope/aspect GeoTIFFs, hillshade PNG,
  profile JSON, histogram JSON, report JSON. Verified: Mount Mitchell 64.2 km² /
  95.5 Gm³; synthetic 120 m-deep lake → 125 Mm³ water (paraboloid-correct).
- **GREECE dataset** — `fetch_greece.py` pulls SRTMGL1 DEMs around 8 ancient
  sites (Acropolis, Delphi, Olympia, Knossos, Delos, Akrotiri, Mycenae,
  Epidaurus) via Nominatim geocoding + OpenTopo, each as a full quickmap run
  (terrain + dashboard). Plus **Aegean bathymetry** from EMODnet WCS (no key,
  Cyclades 24.5–26.5°E × 36–38°N, 1600×1600, −1921..1025 m, 93% sea) — overlaps
  the island sites. All 10 runs live in the hub.
- **BATHYMETRY RASTER OVERLAY + COLORBAR** — `make_bathymetry.py` colorizes a
  depth raster into RGBA XYZ tiles (sea = blue ramp, land transparent) + a
  `bathymetry.json` (depth range + colormap stops). `dashboard.html` now
  supports `type: "raster"` layers and draws a depth colorbar. The dedicated
  `aegean-cyclades` run shows the colorized Aegean bathymetry with Delos +
  Santorini extent outlines (1001 tiles, z8–12). Wired into `fetch_greece.py`.
- **Remote push** — pushed to `github.com/Roylaffman/GIS2026` (done by user, verified in sync)

---

## 4. Tasks — DONE ✅

- [x] `.env` with all keys; `.gitignore` excludes secrets
- [x] OpenTopo DEM + SerpAPI POIs (corrected 64-char SerpAPI key)
- [x] DuckDB spatial DB + analysis report
- [x] Leaflet map with hillshade + POIs (fixed `DEM_BOUNDS.map`→`.flat()` runtime bug)
- [x] GeoPandas + H3 installed; `build_h3.py` exports hexagons
- [x] deck.gl + kepler.gl installed (npm) + UMD-vendored into `web/lib/`
- [x] Kepler.gl redux wiring + auto-load (fixed blank-page bug)
- [x] Mapbox token in `.env` + `/config.js` runtime endpoint
- [x] Phase 2 COG (`make_cog.py`)
- [x] git init + commits on `main`, remote = GIS2026
- [x] **Quick-maps system** — `quickmap.py`, parameterized deck/kepler pages,
      runs hub `/runs.html`, manifest `web/runs/index.json`
- [x] **3D terrain + hillshade** — `make_terrain.py` terrain-RGB tiles + deck.html
      raster-dem/hillshade/setTerrain; wired into quickmap.py
- [x] **Dashboard view** — `make_dashboard.py` (layers.json + real profile.json)
      + `web/dashboard.html` (MapLibre terrain + layers + legend toggles + Chart.js)
- [x] **inspect_data.py** — vector data QA (fields/CRS/bounds/nulls/duplicates)
- [x] **analyze_dem.py** — DEM + bathymetry analysis (stats, hypsometry, volume,
      slope/aspect/hillshade, profile)
- [x] Pushed to GitHub (user pushed; verified `origin/main` in sync)

---

## 5. Tasks — TODO ⬜ (prioritized)

**Blocked / needs user**
- [ ] **Push to GitHub** — needs a Personal Access Token (§8), or user pushes manually
- [ ] **GCS upload** — push DEM/GeoJSON/COG to `gs://www.geoglypha1.org`

**Next build steps (unblocked)**
- [ ] **Arbitrary raster overlays** in dashboard/deck (flood extents, SST, etc. as colorized GeoTIFF + legend/colorbar) — next step toward the flood/`climate` dashboards
- [ ] **CesiumJS globe** (per run; Apache-2.0; self-host terrain to stay tokenless)
- [ ] **PMTiles / vector tiles** for POIs (tippecanoe) once data grows
- [ ] **GeoParquet** export so DuckDB + GeoPandas share one format
- [ ] Kepler.gl auto-load polish: verify `addDataToMap` point layer renders as expected in browser
- [ ] quickmap: fetch POIs for a run into DuckDB too (currently POIs only live as GeoJSON + H3)

**Nice-to-have**
- [ ] One `web/index.html` landing page linking all demos (runs hub already exists at `/runs.html`)
- [ ] Docker compose (verify sandbox allows Docker first)
- [ ] Vendor script to rebuild `web/lib/` from npm (reproducibility)

---

## 6. File map

```
DSHtest/
├── .env                      # SECRETS (git-ignored)
├── .gitignore
├── WORKPLAN.md               # this file
├── MODERN_GIS_STACK.md       # architecture/roadmap
├── README.md                 # run instructions
├── requirements.txt          # Python deps
├── gis_common.py             # env loader + shared constants
├── quickmap.py               # **quick-maps system** (place -> run folder)
├── fetch_dem.py              # OpenTopo -> DEM
├── fetch_pois.py             # SerpAPI -> POIs
├── build_db.py               # DuckDB spatial
├── build_h3.py               # H3 hexagons
├── make_cog.py               # DEM -> COG
├── make_terrain.py           # DEM -> terrain-RGB XYZ tiles + terrain.json
├── make_dashboard.py         # run -> layers.json manifest + real DEM profile.json
├── make_web.py               # hillshade + Leaflet page
├── inspect_data.py           # vector data QA/inspection CLI
├── analyze_dem.py            # DEM + bathymetry analysis CLI
├── fetch_greece.py           # Greek sites DEMs + Aegean bathymetry
├── make_sample_bathy.py      # synthetic bathymetry test fixture
├── serve_map.py              # static server + /config.js (any depth)
├── data/                     # tif, geojson, duckdb, summaries
├── web/
│   ├── index.html            # Mount Mitchell Leaflet demo
│   ├── deck.html             # parameterized Deck.gl (?run=<slug>)
│   ├── kepler.html           # parameterized Kepler.gl (?run=<slug>)
│   ├── dashboard.html        # parameterized dashboard (terrain+layers+profile)
│   ├── runs.html             # hub listing all quick-map runs
│   ├── runs/                 # one folder per quick map + index.json
│   │   ├── index.json
│   │   └── <slug>/{run.json, pois.geojson, h3_hexagons.geojson, dem.tif, dem_cog.tif,
│   │               terrain.json, tiles/{z}/{x}/{y}.png}
│   ├── lib/                  # vendored UMD bundles (committed)
│   ├── tiles/ + terrain.json # root demo terrain
│   └── dem_hillshade.png, *.geojson   # root demo assets
└── frontend/                 # package.json, node_modules (git-ignored),
                              # smoke_kepler.cjs (jsdom test)
```

---

## 7. Command cheat sheet

```powershell
# server (maps)
.\.venv\Scripts\python.exe serve_map.py 8090

# pipeline
.\.venv\Scripts\python.exe quickmap.py "Place, State" --pois serpapi --query "attractions hiking"
.\.venv\Scripts\python.exe fetch_dem.py --demtype SRTMGL1
.\.venv\Scripts\python.exe fetch_pois.py --query "hiking trails near Mount Mitchell NC"
.\.venv\Scripts\python.exe build_db.py
.\.venv\Scripts\python.exe build_h3.py --res 8
.\.venv\Scripts\python.exe make_cog.py
.\.venv\Scripts\python.exe make_web.py

# headless kepler.gl smoke test
cd frontend; node smoke_kepler.cjs

# git
git status; git add -A; git commit -m "..."; git log --oneline
```

---

## 8. Git / push status

- Local: `main`, 2 commits (`dc51485`, `32d8731`), working tree clean.
- Remote: `origin = https://github.com/Roylaffman/GIS2026.git` (public, empty).
- **Push is blocked on authentication**: no credential stored in this sandbox,
  and git's credential-manager helper cannot run here (snag #8).

**To unblock (pick one):**
- **A** — create a GitHub **Personal Access Token** (repo write scope), then I
  run: `git push https://<TOKEN>@github.com/Roylaffman/GIS2026.git main`
  (token used inline, not committed).
- **B** — you push from your normal desktop shell (outside the harness):
  `cd C:\Users\royla\Documents\DSHtest; git push -u origin main`.
