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

API keys live in `.env` (already populated; `.env` is git-ignored).

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

## DEM → browser note

This demo shows the DEM as a **hillshade raster overlay** in Leaflet
(GDAL/numpy-rendered PNG). For true 3D terrain (MapLibre GL / Mapbox GL
`raster-dem` decoding of terrain-RGB tiles) say the word and the next step is
a terrain-RGB tile pyramid served to a MapLibre page.

## Querying the DB directly

```powershell
.\.venv\Scripts\python.exe -c "import duckdb; c=duckdb.connect('data/gis.duckdb'); print(c.sql('select name, rating from pois order by rating desc limit 5').fetchall())"
```
