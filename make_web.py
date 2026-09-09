"""Build the local web map assets for the Mount Mitchell DEM demo.

Reads data/dem_mount_mitchell.tif and produces, under web/:
  - lib/leaflet.js, leaflet.css, leaflet images (vendored, offline-capable)
  - dem_hillshade.png        512px hillshade of the tile (+ dem_bounds.geojson)
  - index.html               Leaflet page: hillshade overlay + POI markers
Then start:  python serve_map.py   ->  http://127.0.0.1:8090

Note on DEM handling in the browser: Leaflet shows the hillshade as a raster
overlay (built here with GDAL/numpy). If you later want true 3D terrain
(Mapbox GL / MapLibre GL terrain-RGB decoding), say so and I'll add a
terrain-RGB tile pyramid for MapLibre GL.
"""
from __future__ import annotations

import json
import math
import urllib.request
from pathlib import Path

import numpy as np
import rasterio

from gis_common import DATA_DIR, SUMMIT_LAT, SUMMIT_LON, SUMMIT_NAME, WEB_DIR

DEM = DATA_DIR / "dem_mount_mitchell.tif"
LIB = WEB_DIR / "lib"

# vendored Leaflet 1.9.4
LEAFLET_JS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
LEAFLET_CSS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
LEAFLET_MARKER = "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png"
LEAFLET_MARKER2X = "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png"
LEAFLET_SHADOW = "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png"


def vendor_leaflet() -> None:
    LIB.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        "https://unpkg.com/", headers={"User-Agent": "DSHtest-GIS/1.0"}
    )
    files = {
        LEAFLET_JS: LIB / "leaflet.js",
        LEAFLET_CSS: LIB / "leaflet.css",
        LEAFLET_MARKER: LIB / "marker-icon.png",
        LEAFLET_MARKER2X: LIB / "marker-icon-2x.png",
        LEAFLET_SHADOW: LIB / "marker-shadow.png",
    }
    for url, dest in files.items():
        if dest.exists() and dest.stat().st_size > 1000:
            continue
        with urllib.request.urlopen(req.full_url.replace(
                "https://unpkg.com/", url), timeout=60) as r:
            dest.write_bytes(r.read())
        print("vendored", dest.name, dest.stat().st_size, "bytes")


def make_hillshade(out: Path, size: int = 512) -> dict:
    """Azimuthal hillshade PNG of the DEM at `size` px on its long edge."""
    with rasterio.open(DEM) as ds:
        src = ds.read(1, masked=True).astype("float64")
        transform = ds.transform
        crs = ds.crs
        nodata = ds.nodata

    # keep aspect by resizing so the longer axis == size
    h, w = src.shape
    scale = size / max(h, w)
    new_h, new_w = max(1, round(h * scale)), max(1, round(w * scale))

    # fill nodata by nearest valid to avoid hillshade edge holes
    fill = float(np.ma.median(src)) if np.ma.count(src) else 0.0
    arr = np.ma.filled(src, fill)

    from rasterio.enums import Resampling
    import rasterio.warp as warp
    arr2 = np.empty((new_h, new_w), dtype="float64")
    warp.reproject(
        arr, arr2,
        src_transform=transform,
        src_crs=crs,
        dst_transform=transform * warp.Affine.scale(w / new_w, h / new_h),
        dst_crs=crs,
        resampling=Resampling.bilinear,
    )

    x, y = np.gradient(arr2)
    slope = np.pi / 2.0 - np.arctan(np.sqrt(x * x + y * y))
    aspect = np.arctan2(-x, y)
    az = math.radians(315.0)   # light from NW
    alt = math.radians(45.0)
    shaded = np.sin(alt) * np.sin(slope) + np.cos(alt) * np.cos(slope) * np.cos(az - aspect)
    hill = 255 * (shaded + 1) / 2
    hill = np.clip(hill, 0, 255).astype("uint8")

    # colorize: low=green -> high=white-ish? simpler: grayscale hillshade PNG
    with rasterio.open(
        out, "w", driver="PNG", height=new_h, width=new_w, count=1,
        dtype="uint8", crs=crs,
        transform=transform * warp.Affine.scale(w / new_w, h / new_h),
    ) as dst:
        dst.write(hill, 1)

    # bounds for the overlay in WGS84
    b = rasterio.transform.array_bounds(new_h, new_w,
        transform * warp.Affine.scale(w / new_w, h / new_h))
    return {"bounds": [b[1], b[0], b[3], b[2]]}  # [south, west, north, east]


def write_index(hill_info: dict) -> None:
    s, w, n, e = hill_info["bounds"]

    # Inline the POI GeoJSON so the page has zero runtime dependency on a
    # separate request (avoids caching / fetch failures entirely).
    pois_fc = None
    for cand in (WEB_DIR / "pois.geojson", DATA_DIR / "pois.geojson"):
        if cand.exists():
            pois_fc = json.loads(cand.read_text(encoding="utf-8"))
            break
    pois_js = json.dumps(pois_fc or {"type": "FeatureCollection", "features": []})

    html = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Mount Mitchell DEM + POIs (DSHtest)</title>
<link rel="stylesheet" href="lib/leaflet.css"/>
<style>
  html,body,#map{height:100%;margin:0}
  #panel{position:absolute;z-index:1000;top:10px;right:10px;background:rgba(255,255,255,.92);
         padding:10px 14px;border-radius:8px;font:13px/1.5 Segoe UI,sans-serif;box-shadow:0 1px 6px rgba(0,0,0,.3);
         max-width:280px}
  #panel h1{font-size:15px;margin:0 0 4px}
  #panel code{background:#eee;padding:1px 4px;border-radius:3px}
  .lbl{font-weight:600}
  #poi-count{color:#1565c0;font-weight:600}
</style>
</head>
<body>
<div id="panel">
  <h1>&#9962; Mount Mitchell DEM demo</h1>
  <div><span class="lbl">DEM:</span> SRTMGL1 30&nbsp;m (OpenTopography)</div>
  <div><span class="lbl">Points:</span> Google Maps via SerpAPI</div>
  <div><span class="lbl">Stack:</span> OpenTopo &#8594; SerpAPI &#8594; DuckDB &#8594; Leaflet</div>
  <div style="margin-top:6px;color:#555">Hillshade overlay + POI markers.<br/>
  Click a marker for details.</div>
  <div style="margin-top:6px"><span class="lbl">POIs loaded:</span> <span id="poi-count">…</span></div>
  <div style="margin-top:8px;border-top:1px solid #ddd;padding-top:6px">
    <b>Other demos:</b><br/>
    <a href="deck.html">Deck.gl (hexagons + 3D)</a><br/>
    <a href="kepler.html">Kepler.gl (explore)</a><br/>
    <a href="runs.html">&#8594; All quick-map runs</a>
  </div>
</div>
<div id="map"></div>
<script src="lib/leaflet.js"></script>
<script>
const POIS = __POIS__;
const DEM_BOUNDS = [[__S__,__W__],[__N__,__E__]];
const SUMMIT = [__SLAT__,__SLON__];
const map = L.map('map').setView(SUMMIT, 13);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19, attribution: '&copy; OpenStreetMap'
}).addTo(map);
L.imageOverlay('dem_hillshade.png', DEM_BOUNDS, {opacity: 0.75}).addTo(map);
L.rectangle(DEM_BOUNDS, {color:'#b71c1c', weight:1.5, fill:false}).addTo(map)
 .bindPopup('<b>SRTMGL1 DEM tile</b><br/>'+JSON.stringify(DEM_BOUNDS.flat().map(b=>b.toFixed(5))));
const summitIcon = L.divIcon({html:'&#9878;', className:'', iconSize:[18,18],
  iconAnchor:[9,9], popupAnchor:[0,-12]});
L.marker(SUMMIT, {icon: summitIcon}).addTo(map)
 .bindPopup('<b>Mount Mitchell</b><br/>2,037&nbsp;m (6,684&nbsp;ft) - highest point east of the Mississippi');

const features = POIS.features || [];
const layer = L.geoJSON(features, {
  pointToLayer: (f,ll)=> L.circleMarker(ll, {radius:7, color:'#fff', weight:2, fillColor:'#1565c0', fillOpacity:.9}),
  onEachFeature: (f,l)=>{
    const p=f.properties||{};
    const rate=p.rating?` &#9733; ${p.rating}`:'';
    l.bindPopup(`<b>${p.name||'?'}</b>${rate}<br/>${p.address||''}<br/><span style="color:#888">${p.ptype||''}</span>`);
  }
}).addTo(map);
const n = layer.getLayers().length;
document.getElementById('poi-count').textContent = n;
if (n === 0) {
  const el=document.createElement('div');
  el.style.cssText='position:absolute;z-index:2000;bottom:10px;left:10px;background:#b71c1c;color:#fff;padding:6px 10px;border-radius:6px;font:12px sans-serif';
  el.textContent='Warning: 0 POIs found in page data (check data/pois.geojson)';
  document.body.appendChild(el);
}
</script>
</body>
</html>
"""
    html = (html.replace("__POIS__", pois_js)
                .replace("__S__", str(s)).replace("__W__", str(w))
                .replace("__N__", str(n)).replace("__E__", str(e))
                .replace("__SLAT__", str(SUMMIT_LAT)).replace("__SLON__", str(SUMMIT_LON)))
    (WEB_DIR / "index.html").write_text(html, encoding="utf-8")
    print("wrote", WEB_DIR / "index.html")


if __name__ == "__main__":
    WEB_DIR.mkdir(exist_ok=True)
    vendor_leaflet()
    info = make_hillshade(WEB_DIR / "dem_hillshade.png")
    print("hillshade bounds [s,w,n,e]:", info["bounds"])
    write_index(info)
