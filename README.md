# Mount Mitchell GIS demo (DSHtest)

End-to-end GIS pipeline test on the DeepSeek Harness:
**OpenTopography DEM -> SerpAPI points -> DuckDB (spatial) -> Leaflet map.**

Study area: Mount Mitchell, NC — summit 35.7649, -82.2651 (highest point east
of the Mississippi, 2,037 m). AOI is a ~0.08° box around the summit
(SRTMGL1 tile, 1-arc-sec ≈ 30 m resolution).

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

API keys live in `.env` (git-ignored). Required keys are documented in
`.env.example`.

## Documentation

All project docs live in **[`docs/`](docs/)** — see [`docs/README.md`](docs/README.md) for the index.

| Doc | What it covers |
|-----|----------------|
| [`docs/WORKPLAN.md`](docs/WORKPLAN.md) | **Start here** — project state, done/todo, environment, harness snags, command cheat sheet |
| [`docs/MODERN_GIS_STACK.md`](docs/MODERN_GIS_STACK.md) | Architecture & roadmap (GDAL/GeoPandas/DuckDB/H3 + Deck.gl/Kepler.gl/Cesium) |
| [`docs/TOPIC_WEBMAP_PLAN.md`](docs/TOPIC_WEBMAP_PLAN.md) | "Topic → webmap" system; **Mapbox GL JS primary renderer**; Quarto embedding |
| [`docs/DSH_WorkingGuide.md`](docs/DSH_WorkingGuide.md) | DeepSeek Harness itself — commands, rebuild rules, workspace setup |


## Pipeline steps

| Step | Script | Output |
|------|--------|--------|
| 1. Fetch DEM tile | `.\.venv\Scripts\python.exe fetch_dem.py [--demtype SRTMGL1\|SRTMGL3\|COP30]` | `data/dem_mount_mitchell.tif`, `data/dem_summary.json` |
| 2. Fetch POIs (SerpAPI Google Maps) | `.\.venv\Scripts\python.exe fetch_pois.py --query "hiking trails near Mount Mitchell NC"` | `data/pois.geojson` (dedupe/merge several queries with a small script or by hand) |
| 3. DuckDB spatial DB | `.\.venv\Scripts\python.exe build_db.py` | `data/gis.duckdb`, `web/pois.geojson`, `web/dem_bounds.geojson`, `data/query_report.txt` |
| 4. Web assets | `.\.venv\Scripts\python.exe make_web.py` | `web/index.html`, `web/dem_hillshade.png` (vendors Leaflet into `web/lib/`) |
| 5. View map | `.\.venv\Scripts\python.exe serve_map.py [port]` then open **http://127.0.0.1:8090** | |

## Notes / gotchas discovered

- **Sandbox TLS:** Windows `curl.exe`/`Invoke-WebRequest` fail inside this
  harness sandbox with `SEC_E_NO_CREDENTIALS` (schannel). Python's OpenSSL
  stack works — all network I/O here goes through `urllib` (see
  `gis_common.http_get`).
- **DuckDB extensions** want `%USERPROFILE%\.duckdb`; the sandbox denies that,
  so `build_db.py` sets `extension_directory` to `data/duckdb_ext/`.
- **SerpAPI key length:** the original key pasted into `.env` was truncated
  (46 hex chars, rejected with 401 "Invalid API key"). A valid SerpAPI key is
  64 hex chars. Fixed in `.env`.
- SerpAPI returns either `local_results` (list) or `place_results`
  (single dict/featured place); `fetch_pois.py` handles both.
- DuckDB spatial `ST_Read('file.geojson')` flattens GeoJSON properties into
  columns (geometry column named `geom`); `build_db.py` renames dynamically.

## More than the Mount Mitchell demo

This repo has grown well past the original demo. Current capabilities:

- **`quickmap.py`** — one command turns a place into a full map set (DEM +
  terrain + POIs + H3 + dashboard) under `web/runs/<slug>/`; hub at `/runs.html`.
- **`build_topic.py`** — turns a *topic* JSON into an embeddable webmap with a
  **Source Quality Legend** + references (see `docs/TOPIC_WEBMAP_PLAN.md`).
- **`inspect_data.py`** — QA any vector dataset (fields, CRS, bounds, nulls).
- **`analyze_dem.py`** — DEM **and bathymetry** analysis (stats, hypsometry,
  volume, slope/aspect/hillshade).
- **`make_terrain.py` / `make_bathymetry.py`** — terrain-RGB tiles and
  colorized depth tiles for 3D terrain / bathymetry overlays.
- **Map pages:** `/` (Leaflet), `/deck.html` (Deck.gl 3D), `/kepler.html`,
  `/dashboard.html`, `/topic.html` — all parameterized by `?run=` / `?topic=`.

## DEM → browser

3D terrain works: `make_terrain.py` writes terrain-RGB XYZ tiles and the
Deck.gl/dashboard pages render them via a `raster-dem` source + `setTerrain`
with hillshade. Bathymetry is colorized into tiles by `make_bathymetry.py`.
Per the renderer decision in `docs/TOPIC_WEBMAP_PLAN.md` §0, **Mapbox GL JS is
the primary engine for the main/topic maps** (3D terrain + coded-in GeoJSON).

## Querying the DB directly

```powershell
.\.venv\Scripts\python.exe -c "import duckdb; c=duckdb.connect('data/gis.duckdb'); print(c.sql('select name, rating from pois order by rating desc limit 5').fetchall())"
```
