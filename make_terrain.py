"""make_terrain.py — generate Mapbox-compatible terrain-RGB XYZ tiles from a DEM.

MapLibre GL (and Mapbox GL) render 3D terrain from a `raster-dem` source whose
tiles encode elevation in the R/G/B channels:
    height = -10000 + ((R*256*256 + G*256 + B) * 0.1)

This script reads a GeoTIFF (e.g. data/dem_mount_mitchell.tif or a run's
web/runs/<slug>/dem.tif) and writes:
    <out>/tiles/{z}/{x}/{y}.png   (256px terrain-RGB)
    <out>/terrain.json            (bounds + zoom range + encoding)

Then a MapLibre map adds:
    source { type: 'raster-dem', tiles: [<out>/tiles/{z}/{x}/{y}.png], encoding: 'mapbox' }
    layer  { type: 'hillshade', source: ... }
    map.setTerrain({ source: ..., exaggeration: 1.4 })

Usage:
    .venv\\Scripts\\python.exe make_terrain.py data/dem_mount_mitchell.tif web
    .venv\\Scripts\\python.exe make_terrain.py web/runs/<slug>/dem.tif web/runs/<slug>
"""
from __future__ import annotations

import argparse
import json
import math
import warnings
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject
from rasterio.transform import Affine

# PNG tiles intentionally carry no georeferencing (XYZ naming encodes it)
warnings.filterwarnings("ignore", category=rasterio.errors.NotGeoreferencedWarning)

# terrain-RGB encoding range: 0..8850 m (covers Mt Mitchell 2037 m etc.)
MAX_ELEV = 8850.0


def _tile_bounds_lnglat(x: int, y: int, z: int):
    n = 2 ** z
    west = x / n * 360.0 - 180.0
    east = (x + 1) / n * 360.0 - 180.0
    north = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    south = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return west, south, east, north


def _lnglat_to_merc(lng: float, lat: float):
    x = lng * 20037508.342789244 / 180.0
    y = math.log(math.tan((90.0 + lat) * math.pi / 360.0)) / (math.pi / 180.0)
    y = y * 20037508.342789244 / 180.0
    return x, y


def _encode_terrain_rgb(h: np.ndarray) -> np.ndarray:
    h = np.clip(h, 0.0, MAX_ELEV)
    v = ((h + 10000.0) * 10.0).astype(np.int64)
    r = (v >> 16) & 0xFF
    g = (v >> 8) & 0xFF
    b = v & 0xFF
    return np.stack([r, g, b], axis=2).astype(np.uint8)


def make_terrain(dem_path: Path, out_dir: Path, min_zoom: int = 9, max_zoom: int = 15) -> dict:
    dem_path = Path(dem_path)
    out_dir = Path(out_dir)
    tiles_dir = out_dir / "tiles"
    tiles_dir.mkdir(parents=True, exist_ok=True)

    with rasterio.open(dem_path) as src:
        nodata = src.nodata if src.nodata is not None else -32768.0
        # lon/lat bounds
        west, south, east, north = src.bounds
        band = src.read(1).astype("float32")
        src_transform = src.transform
        src_crs = src.crs

    tile_count = 0
    for z in range(min_zoom, max_zoom + 1):
        n = 2 ** z
        # tile index range covering the DEM bounds
        def x_of(lng):
            return int((lng + 180.0) / 360.0 * n)
        def y_of(lat):
            return int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
        x0, x1 = x_of(west), x_of(east)
        y0, y1 = y_of(north), y_of(south)
        for tx in range(x0, x1 + 1):
            for ty in range(y0, y1 + 1):
                w, s, e, n_ = _tile_bounds_lnglat(tx, ty, z)
                mx0, my1 = _lnglat_to_merc(w, n_)  # top-left (max Y)
                mx1, my0 = _lnglat_to_merc(e, s)   # bottom-right (min Y)
                pw = (mx1 - mx0) / 256.0
                ph = (my1 - my0) / 256.0
                dst = np.full((256, 256), nodata, dtype="float32")
                dst_transform = Affine(pw, 0.0, mx0, 0.0, -ph, my1)
                reproject(
                    source=band,
                    destination=dst,
                    src_transform=src_transform,
                    src_crs=src_crs,
                    dst_transform=dst_transform,
                    dst_crs="EPSG:3857",
                    resampling=Resampling.bilinear,
                    src_nodata=nodata,
                    dst_nodata=nodata,
                )
                # nodata -> sea level (0) so terrain edges are flat, not -10000 m
                dst[dst == nodata] = 0.0
                rgb = _encode_terrain_rgb(dst)
                out_png = tiles_dir / f"{z}" / f"{tx}" / f"{ty}.png"
                out_png.parent.mkdir(parents=True, exist_ok=True)
                with rasterio.open(out_png, "w", driver="PNG", width=256, height=256,
                                   count=3, dtype="uint8") as d:
                    d.write(rgb.transpose(2, 0, 1))
                tile_count += 1

    meta = {
        "encoding": "mapbox",
        "bounds": [west, south, east, north],
        "minzoom": min_zoom,
        "maxzoom": max_zoom,
        "tileSize": 256,
        "tiles": f"{tiles_dir.name}/{{z}}/{{x}}/{{y}}.png",
    }
    (out_dir / "terrain.json").write_text(json.dumps(meta, indent=2))
    print(f"terrain -> {out_dir} ({tile_count} tiles, z{min_zoom}-{max_zoom})")
    return meta


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Generate terrain-RGB XYZ tiles from a DEM")
    p.add_argument("dem", help="input GeoTIFF")
    p.add_argument("out", help="output dir (tiles/ + terrain.json)")
    p.add_argument("--minzoom", type=int, default=9)
    p.add_argument("--maxzoom", type=int, default=15)
    args = p.parse_args()
    make_terrain(Path(args.dem), Path(args.out), args.minzoom, args.maxzoom)
