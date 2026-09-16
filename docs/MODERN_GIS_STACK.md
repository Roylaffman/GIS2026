# Modern Open-Source GIS Stack — Roadmap & Plan

> A practical plan for layering **Cesium, Deck.gl, Kepler.gl, and H3 ("hexagon")**
> on top of the classics (**GDAL, GeoPandas, DuckDB**) inside this DSHtest
> workspace. Every tool listed is free/open-source. It uses the running
> Mount Mitchell demo (DEM + 20 POIs) as the testbed.

---

## 1. TL;DR

| Layer | Tools | Job |
|-------|-------|-----|
| **Data / ETL** (Python) | GDAL / rasterio, GeoPandas, Shapely, pyproj | fetch, reproject, clean, transform |
| **Analytics** (Python/SQL) | DuckDB + spatial, H3 (`h3-py`) | SQL queries, aggregation, hex-binning |
| **Tiles & serving** | GDAL (COG), PMTiles, plain static server | make data web-friendly |
| **Web viz** (JS) | Deck.gl, Kepler.gl, CesiumJS, MapLibre GL | interactive/3D rendering in the browser |

The big idea: **Python does the heavy lifting; the browser does the display.**
You keep a fast, auditable, reusable data pipeline and pick the *best renderer*
per task instead of one monolithic GIS.

---

## 2. The two halves of the stack

### (a) Classics — Python data & analytics
- **GDAL / rasterio / fiona** — raster + vector I/O, reprojection, warping,
  Cloud-Optimized GeoTIFF (COG). *Already used here* (`rasterio` in `fetch_dem.py`).
- **GeoPandas** — vector dataframes, spatial joins, dissolves, overlays.
  (Thin, friendly wrapper over Shapely + Fiona + pyproj.)
- **Shapely** — the geometry engine underneath (predicates, buffers, etc.).
- **pyproj** — CRS transforms (EPSG ↔ EPSG).
- **DuckDB + spatial** — fast SQL analytics, reads GeoJSON/Parquet/GeoTIFF.
  *Already used here* (`build_db.py`).
- **h3-py** — H3 hexagonal grid indexing/aggregation (see §4).

### (b) Modern — JavaScript visualization
- **Deck.gl** — WebGL layers for big data (scatter, hexagon, terrain, trips,
  3D tiles…). Renders on top of a MapLibre GL basemap.
- **Kepler.gl** — a no-code dashboard built *on* Deck.gl. Drag-drop data,
  hexbins, heatmaps, trips. Good for exploration/prototyping and for handing
  non-coders a map.
- **CesiumJS** — a full 3D *globe* with terrain, time-dynamic data, and
  3D Tiles (OGC). Best when you need a globe, real terrain, or temporal scenes.
- **MapLibre GL** — the open-source Mapbox GL fork. Basemaps + 3D terrain +
  vector/raster tiles. (Also a natural replacement for the Leaflet page we
  already built.)
- **Turf.js / PMTiles** — client-side geometry ops; single-file tile archives.

---

## 3. The "hexagon" — H3, not Hexagon AB

Two different things share the name; pick the one you meant:

| Name | What it is | License | Open source? |
|------|-----------|---------|--------------|
| **H3** (Uber) | hierarchical hexagonal grid index (`h3-py`, JS) | Apache-2.0 | ✅ yes |
| **Hexagon AB** | vendor (ERDAS, Luciad, GeoMedia, M.App) | proprietary | ❌ no |

Given the "as much open source as possible" goal, this plan uses **H3** — and
it pairs beautifully with Deck.gl (`H3HexagonLayer`) and Kepler.gl (hexbin).
If you also need Hexagon AB's commercial products, that's a separate track.

---

## 4. Which renderer, when (decision guide)

| You want to… | Use |
|--------------|-----|
| Explore/drag-drop a dataset quickly, no code | **Kepler.gl** |
| A rich custom app: hexbins, trips, heatmaps, big data | **Deck.gl** |
| A full 3D globe with terrain + temporal/3D-tiles scenes | **CesiumJS** |
| A crisp 2D/2.5D basemap with labels + terrain | **MapLibre GL** |
| Aggregate millions of points to a grid | **H3** (+ Deck.gl hexagon layer) |
| SQL analytics before any viz | **DuckDB + spatial** |
| Raster/vector transforms, tiles, COGs | **GDAL / GeoPandas** |

They are *complementary*, not competing: a common production pattern is
**Kepler.gl for exploration → Deck.gl for the product → Cesium for the 3D globe**.

---

## 5. How they plug into THIS workspace (current state)

Existing files already form the "classics" half of the pipeline:

```
DSHtest/
├── .env                      # API keys (OpenTopo, SerpAPI, GCS)
├── gis_common.py             # env loader + shared constants
├── fetch_dem.py              # GDAL/rasterio: OpenTopo -> GeoTIFF
├── fetch_pois.py             # urllib: SerpAPI -> GeoJSON
├── build_db.py               # DuckDB + spatial: analytics, exports
├── make_web.py               # hillshade render + Leaflet page
├── serve_map.py              # local static server (port 8090)
├── data/
│   ├── dem_mount_mitchell.tif   # SRTMGL1 30m, 288x288, WGS84
│   ├── pois.geojson             # 20 POIs
│   └── gis.duckdb               # DuckDB spatial DB
└── web/                      # current Leaflet demo
```

Target architecture (adds the "modern" half):

```
        ┌─────────────────────────── Python (ETL/analytics) ───────────────────────────┐
        │  fetch_dem.py ──► GDAL/rasterio ──► COG (dem.tif)                             │
        │  fetch_pois.py ─► GeoJSON ──► GeoPandas ──► H3 hex-bin ──► h3.geojson        │
        │  build_db.py  ──► DuckDB spatial ──► Parquet / GeoJSON / query_report        │
        └──────────────┬────────────────────────────────────────────────────────────────┘
                       │ outputs (GeoJSON, Parquet, COG, PMTiles)
                       ▼
        ┌─────────────────────────── local static server (serve_map.py) ────────────────┐
        │   /index.html   /tiles/{z}/{x}/{y}.pbf   /data/*.geojson  /dem.pmtiles        │
        └──────────────┬────────────────────────────────────────────────────────────────┘
                       │ browser (user's machine)
                       ▼
        ┌─────────────────────────── JavaScript renderers ──────────────────────────────┐
        │  Kepler.gl (explore)  ·  Deck.gl (product)  ·  CesiumJS (3D globe)            │
        └────────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Constraints we already discovered in this harness

These change *how* we build here (they're baked into the plan below):

1. **schannel TLS fails in PowerShell** — `curl.exe` / `Invoke-WebRequest`
   error with `SEC_E_NO_CREDENTIALS`. **Python (`urllib`) and Node work**
   because they use OpenSSL. → Do all network I/O in Python/Node.
2. **Headless Chrome cannot launch** (sandbox blocks its IPC/named pipes).
   → We can *serve* web apps and verify them via HTTP + `node --check`, but
   only **you** can see the rendered map in your browser. This matters for
   Deck.gl/Kepler.gl/Cesium: they must be viewed by you, not screenshotted by me.
3. **DuckDB wants `%USERPROFILE%\.duckdb`** for extensions; sandbox denies it.
   → Set `SET extension_directory='data/duckdb_ext'` (already done in `build_db.py`).
4. **Workspace-write sandbox** — writes stay under
   `C:\Users\royla\Documents\DSHtest`. Fine for all of the above.
5. **Python 3.11 + Node v24** are both available; a `.venv` already exists
   with `duckdb`, `rasterio`, `numpy`.

---

## 7. Phased implementation plan

### Phase 0 — Foundations (mostly done ✅)
- [x] `.venv`, `duckdb`, `rasterio`, `numpy`
- [x] DEM fetch (OpenTopo) + POI fetch (SerpAPI)
- [x] DuckDB spatial DB + Leaflet proof-of-concept map

### Phase 1 — Add the Python classics (GeoPandas + H3)
- [x] Install: `pip install geopandas h3 pyarrow` (geopandas 1.1.4, h3 4.5.0, pyarrow 25.0.1)
- [x] New script `build_h3.py`:
  - load `data/pois.geojson` → GeoDataFrame (CRS EPSG:4326)
  - `latlng_to_cell(lat, lng, res)` for each POI (`res=8`, ~0.7 km cells)
  - aggregate: `POI count per hex`, `mean rating per hex`, dominant category
  - export `web/h3_hexagons.geojson` (H3 cells as polygons, with counts)
- [x] Ran it: 17 hexagons covering 20 POIs → `web/h3_hexagons.geojson`

**Result:** a hex-grid aggregation ready to render — the H3 "classic→modern"
bridge is in place.

### Phase 2 — Web-friendly data (COG + PMTiles)
- [ ] COG-ify the DEM:
  `gdal_translate -of COG data/dem_mount_mitchell.tif data/dem_cog.tif`
  (or via `rasterio` with overviews/tiling for HTTP range reads)
- [ ] Convert POIs to vector tiles with **tippecanoe** (needs install) *or*
  keep as GeoJSON for now (20 points is trivial — PMTiles is for scale).
- [ ] Keep serving via `serve_map.py` (or swap to `npx serve` later).

### Phase 3 — Deck.gl app (the "product" renderer)
- [x] `frontend/package.json` + `npm install deck.gl` (v9.4.0) — UMD bundles
      vendored into `web/lib/` (no bundler needed; sandbox blocks esbuild/vite).
- [x] `web/deck.html` — Deck.gl + MapLibre GL:
  - MapLibre basemap (OSM raster)
  - `GeoJsonLayer` for `web/h3_hexagons.geojson` (extruded by POI count)
  - `ScatterplotLayer` for the 20 raw POIs (tooltip = name + rating)
- [ ] Add a `TerrainLayer` from the COG DEM (needs Phase 2 COG first).

**Result:** the Mount Mitchell scene becomes a Deck.gl dashboard — hex bins
of POI density + raw points, all from our existing data.

### Phase 4 — CesiumJS 3D globe
- [ ] `web/cesium.html` — CesiumJS (Apache-2.0) from CDN:
  - base globe; POIs as `Entity` billboards/labels at their lon/lat/alt
  - optional real terrain: either Cesium World Terrain (needs a free ion
    token) or self-hosted quantized-mesh via `ctb-quantized-mesh`/`pg_tileserv`.
- [ ] Add a summit camera fly-to (Mount Mitchell 2,037 m).

**Result:** the same POIs on a spin-able globe with elevation — the "wow" view.

### Phase 5 — Kepler.gl exploratory dashboard
- [x] `npm install kepler.gl` (v3.2.6) — UMD bundle vendored into `web/lib/`
      with its 5 required globals (React, ReactDOM, Redux, ReactRedux, styled-components).
- [x] `web/kepler.html` — embeds Kepler.gl (UMD build, no bundler):
  - loads POIs via the UI "Add Data" (drag-drop `pois.geojson`)
  - ⚠ basemap uses Mapbox GL and needs a `MAPBOX_TOKEN` (proprietary);
    data layers render without it.
- [ ] Wire kepler.gl reducers into redux to pre-load `pois.geojson` automatically
      (nicer than the manual "Add Data" button).

**Result:** zero-code exploration of the same data.

### Phase 6 — Consolidate & scale
- [ ] One entry page (`web/index.html`) linking Deck/Cesium/Kepler demos.
- [ ] Move heavy data to **Parquet** (GeoParquet) so DuckDB/GeoPandas share
      one format; add **PMTiles** once data grows past a few hundred MB.
- [ ] (Optional) Docker + `docker compose` so the whole stack is reproducible
      on any machine — *only if the harness sandbox allows Docker* (verify
      later; not required for local dev).

---

## 8. Licensing quick-reference (all open source)

| Tool | License |
|------|---------|
| GDAL, Fiona, Shapely, GeoPandas, MapLibre GL, PMTiles | BSD-3-Clause / X/MIT-style |
| Deck.gl, Kepler.gl, Turf.js, pyproj, DuckDB | MIT |
| CesiumJS, H3, xarray, rioxarray | Apache-2.0 |

⚠️ CesiumJS is open source, but **Cesium ion** (hosted terrain/assets/token)
is a commercial service. For a fully self-hosted stack, use local/self-hosted
terrain or MapLibre terrain instead of ion.

---

## 9. Suggested order of attack (what I'd do first)

1. **Phase 1** — `pip install geopandas h3 pyarrow` and write `build_h3.py`
   (quick, pure Python, immediately gives you a "hexagon" artifact).
2. **Phase 3** — a single `deck.html` with H3 hexagon layer + scatterplot,
   reusing the data we already have. This is the highest-value visual payoff.
3. **Phase 2** — COG the DEM so terrain layers can stream it.
4. **Phase 4/5** — Cesium globe and Kepler.gl, as time allows.

Want me to start **Phase 1 (install GeoPandas + H3 and build `build_h3.py`)** now?
