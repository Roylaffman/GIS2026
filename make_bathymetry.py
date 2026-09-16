"""make_bathymetry.py — colorize a depth/bathymetry raster into XYZ tiles.

MapLibre renders a plain `raster` source as-is, so we pre-colorize depth
values into a blue ramp (land transparent) and write Web-Mercator XYZ tiles:

    <out>/bathy_tiles/{z}/{x}/{y}.png   (RGBA: sea = blue ramp, land = transparent)
    <out>/bathymetry.json               (bounds, depth range, colormap, tiles url)

The dashboard reads bathymetry.json (via a `type: "raster"` entry in
layers.json) and draws the depth colorbar from the colormap stops.

Usage:
  .venv\\Scripts\\python.exe make_bathymetry.py data/greece/aegean_cyclades_bathymetry.tif web/runs/aegean-cyclades
"""
from __future__ import annotations

import argparse
import json
import math
import warnings
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import Affine
from rasterio.warp import Resampling, reproject

from gis_common import fix_proj

try:
    import rasterio.errors
    warnings.filterwarnings("ignore", category=rasterio.errors.NotGeoreferencedWarning)
except Exception:
    pass

# depth -> RGB ramp (shallow light blue -> deep navy). Land (>= 0) = transparent.
COLORMAP = [
    (0.0, (126, 200, 227)),     # #7ec8e3 shallow
    (-10.0, (86, 180, 233)),    # #56b4e9
    (-50.0, (30, 136, 229)),    # #1e88e5
    (-200.0, (21, 101, 192)),   # #1565c0
    (-500.0, (13, 71, 161)),    # #0d47a1
    (-1000.0, (0, 33, 113)),    # #002171
    (-2000.0, (0, 8, 40)),      # deep trench
]


def _tile_bounds_lnglat(x, y, z):
    n = 2 ** z
    west = x / n * 360.0 - 180.0
    east = (x + 1) / n * 360.0 - 180.0
    north = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    south = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return west, south, east, north


def _lnglat_to_merc(lng, lat):
    x = lng * 20037508.342789244 / 180.0
    y = math.log(math.tan((90.0 + lat) * math.pi / 360.0)) / (math.pi / 180.0)
    return x, y * 20037508.342789244 / 180.0


def _apply_colormap(vals: np.ndarray, nodata: float) -> np.ndarray:
    """Return RGBA uint8 (H,W,4). Land/nodata -> alpha 0."""
    depths = np.array([s[0] for s in COLORMAP])
    colors = np.array([s[1] for s in COLORMAP], dtype=float)
    h, w = vals.shape
    out = np.zeros((h, w, 4), dtype=np.uint8)
    sea = vals < 0.0
    sea &= vals != nodata
    if not sea.any():
        return out
    v = vals[sea]  # negative depths
    # interpolate color for each sea cell
    idx = np.searchsorted(depths, v, side="right") - 1  # depths ascending, v<=0
    idx = np.clip(idx, 0, len(depths) - 2)
    t = (v - depths[idx]) / (depths[idx + 1] - depths[idx] + 1e-9)
    t = np.clip(t, 0, 1)[:, None]
    rgb = colors[idx] * (1 - t) + colors[idx + 1] * t
    out[sea, :3] = rgb.astype(np.uint8)
    out[sea, 3] = 255
    return out


def make_bathymetry(dem_path: Path, out_dir: Path, min_zoom: int = 8, max_zoom: int = 12) -> dict:
    dem_path = Path(dem_path)
    out_dir = Path(out_dir)
    tiles_dir = out_dir / "bathy_tiles"
    tiles_dir.mkdir(parents=True, exist_ok=True)

    with rasterio.open(dem_path) as src:
        nodata = src.nodata if src.nodata is not None else np.nan
        west, south, east, north = src.bounds
        band = src.read(1).astype("float32")
        src_transform = src.transform
        src_crs = src.crs

    def x_of(lng, n):
        return int((lng + 180.0) / 360.0 * n)

    def y_of(lat, n):
        return int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)

    count = 0
    for z in range(min_zoom, max_zoom + 1):
        n = 2 ** z
        for tx in range(x_of(west, n), x_of(east, n) + 1):
            for ty in range(y_of(north, n), y_of(south, n) + 1):
                w, s, e, nn = _tile_bounds_lnglat(tx, ty, z)
                mx0, my1 = _lnglat_to_merc(w, nn)
                mx1, my0 = _lnglat_to_merc(e, s)
                pw = (mx1 - mx0) / 256.0
                ph = (my1 - my0) / 256.0
                dst = np.full((256, 256), nodata, dtype="float32")
                reproject(
                    source=band, destination=dst,
                    src_transform=src_transform, src_crs=src_crs,
                    dst_transform=Affine(pw, 0.0, mx0, 0.0, -ph, my1),
                    dst_crs="EPSG:3857", resampling=Resampling.bilinear,
                    src_nodata=nodata, dst_nodata=nodata,
                )
                rgba = _apply_colormap(dst, nodata)
                png = tiles_dir / str(z) / str(tx) / f"{ty}.png"
                png.parent.mkdir(parents=True, exist_ok=True)
                with rasterio.open(png, "w", driver="PNG", width=256, height=256,
                                   count=4, dtype="uint8") as d:
                    d.write(rgba.transpose(2, 0, 1))
                count += 1

    finite = band[np.isfinite(band)]
    meta = {
        "encoding": "colorized",
        "tiles": f"{tiles_dir.name}/{{z}}/{{x}}/{{y}}.png",
        "tileSize": 256,
        "bounds": [west, south, east, north],
        "minzoom": min_zoom,
        "maxzoom": max_zoom,
        "depth_min": round(float(finite.min()), 1),
        "depth_max": round(float(finite.max()), 1),
        "colormap": [{"value": v, "color": "#%02x%02x%02x" % tuple(c)} for v, c in COLORMAP],
    }
    (out_dir / "bathymetry.json").write_text(json.dumps(meta, indent=2))
    print(f"bathymetry tiles -> {out_dir} ({count} tiles, z{min_zoom}-{max_zoom}, "
          f"depth {meta['depth_min']}..{meta['depth_max']} m)")
    return meta


if __name__ == "__main__":
    fix_proj()
    p = argparse.ArgumentParser()
    p.add_argument("dem", help="bathymetry/depth GeoTIFF")
    p.add_argument("out", help="output run dir")
    p.add_argument("--minzoom", type=int, default=8)
    p.add_argument("--maxzoom", type=int, default=12)
    args = p.parse_args()
    make_bathymetry(Path(args.dem), Path(args.out), args.minzoom, args.maxzoom)
