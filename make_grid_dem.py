"""make_grid_dem.py — fetch a wide DEM region around a center + a grid overlay.

Fills in the region AROUND a central point so a topic map shows surrounding
terrain (mirrors the "wider area" feel of the geoglypha reference maps).

Two modes:
  1. single   (default, fast) — one OpenTopography request for the whole
              n*cell_deg wide box, then derive an n x n grid overlay outline.
  2. mosaic   (literal tiles) — fetch each n*n cell separately and mosaic.
              Slower (n*n requests) but matches "grid of DEMs" exactly.

Always writes:
  <out>/grid_dem.tif    the DEM
  <out>/grid.geojson    n x n cell outlines (for an on-map overlay)

Usage:
  .venv\\Scripts\\python.exe make_grid_dem.py 35.7649 -82.2651 --n 4 --cell 0.08 --out data/mm_grid
  .venv\\Scripts\\python.exe make_grid_dem.py 35.7649 -82.2651 --n 9 --cell 0.08 --mode mosaic
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import rasterio
from rasterio.merge import merge as rio_merge

from gis_common import fix_proj, load_env, http_get


def _cell_bounds(center_lat, center_lon, i, j, n, cell_deg):
    dy = (i - (n - 1) / 2) * cell_deg
    dx = (j - (n - 1) / 2) * cell_deg
    south = center_lat + dy - cell_deg / 2
    north = center_lat + dy + cell_deg / 2
    west = center_lon + dx - cell_deg / 2
    east = center_lon + dx + cell_deg / 2
    return west, south, east, north


def write_grid_geojson(center_lat, center_lon, n, cell_deg, out_dir: Path):
    cells = []
    for i in range(n):
        for j in range(n):
            w, s, e, nn = _cell_bounds(center_lat, center_lon, i, j, n, cell_deg)
            cells.append({"type": "Feature",
                          "properties": {"cell": f"{i},{j}"},
                          "geometry": {"type": "Polygon", "coordinates": [[
                              [w, s], [e, s], [e, nn], [w, nn], [w, s]]]}})
    (out_dir / "grid.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "features": cells}))


def _fetch_one(west, south, east, north, demtype, key, dest: Path):
    url = (
        "https://portal.opentopography.org/API/globaldem"
        f"?demtype={demtype}&south={south}&north={north}&west={west}&east={east}"
        f"&outputFormat=GTiff&API_Key={key}"
    )
    http_get(url, dest)
    return dest


def fetch_grid_dem(center_lat: float, center_lon: float, n: int, cell_deg: float,
                   demtype: str, out_dir: Path, mode: str = "single") -> Path:
    fix_proj()
    env = load_env()
    key = env.get("OPENTOPO_API_KEY")
    if not key:
        raise SystemExit("OPENTOPO_API_KEY missing from .env")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    half = n * cell_deg / 2
    west = center_lon - half
    east = center_lon + half
    south = center_lat - half
    north = center_lat + half

    if mode == "single":
        out_dem = out_dir / "grid_dem.tif"
        _fetch_one(west, south, east, north, demtype, key, out_dem)
    else:  # mosaic of literal tiles
        tmp = out_dir / "_grid_tmp"
        tmp.mkdir(parents=True, exist_ok=True)
        paths = []
        for i in range(n):
            for j in range(n):
                w, s, e, nn = _cell_bounds(center_lat, center_lon, i, j, n, cell_deg)
                p = tmp / f"cell_{i}_{j}.tif"
                _fetch_one(w, s, e, nn, demtype, key, p)
                paths.append(p)
        datasets = [rasterio.open(p) for p in paths]
        mosaic, transform = rio_merge(datasets)
        prof = datasets[0].profile.copy()
        prof.update(height=mosaic.shape[1], width=mosaic.shape[2], transform=transform,
                    driver="GTiff", compress="deflate")
        out_dem = out_dir / "grid_dem.tif"
        with rasterio.open(out_dem, "w", **prof) as dst:
            dst.write(mosaic)
        for ds in datasets:
            ds.close()
        shutil.rmtree(tmp, ignore_errors=True)

    write_grid_geojson(center_lat, center_lon, n, cell_deg, out_dir)

    with rasterio.open(out_dem) as ds:
        b = ds.bounds
        arr = ds.read(1).astype("float64")
        print(f"grid_dem.tif: {ds.width}x{ds.height}px  bounds "
              f"[{b.left:.3f},{b.bottom:.3f},{b.right:.3f},{b.top:.3f}]  "
              f"elev {np.nanmin(arr):.0f}..{np.nanmax(arr):.0f} m  ({n}x{n} grid)")
    return out_dem


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Fetch a wide DEM region + grid overlay")
    p.add_argument("lat", type=float)
    p.add_argument("lon", type=float)
    p.add_argument("--n", type=int, default=4, help="grid is n x n (default 4)")
    p.add_argument("--cell", type=float, default=0.08, help="cell size in degrees (default 0.08)")
    p.add_argument("--demtype", default="SRTMGL1")
    p.add_argument("--mode", choices=["single", "mosaic"], default="single")
    p.add_argument("--out", required=True, help="output dir")
    args = p.parse_args()
    fetch_grid_dem(args.lat, args.lon, args.n, args.cell, args.demtype,
                   Path(args.out), args.mode)
