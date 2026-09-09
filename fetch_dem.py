"""Fetch a DEM (digital elevation model) tile for the Mount Mitchell, NC area
from the OpenTopography API using OPENTOPO_API_KEY from .env.

Output: data/dem_mount_mitchell.tif  (GeoTIFF, WGS84)
Also prints a compact summary of the DEM tile.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from gis_common import AOI, DATA_DIR, load_env, http_get

DEM_OUT = DATA_DIR / "dem_mount_mitchell.tif"

# OpenTopography global DEM API: any of SRTMGL1 (30m), SRTMGL3 (90m), COP30...
API = "https://portal.opentopography.org/API/globaldem"


def fetch_dem(demtype: str = "SRTMGL1", aoi: dict | None = None) -> Path:
    env = load_env()
    key = env.get("OPENTOPO_API_KEY")
    if not key:
        sys.exit("OPENTOPO_API_KEY missing from .env")
    box = aoi or AOI
    url = (
        f"{API}?demtype={demtype}"
        f"&south={box['south']}&north={box['north']}"
        f"&west={box['west']}&east={box['east']}"
        f"&outputFormat=GTiff&API_Key={key}"
    )
    print(f"Requesting {demtype} DEM for box: {box}")
    http_get(url, DEM_OUT)
    if DEM_OUT.stat().st_size < 1000:
        sys.exit(f"DEM download suspiciously small: {DEM_OUT.stat().st_size} bytes")
    print(f"Saved {DEM_OUT} ({DEM_OUT.stat().st_size} bytes)")
    return DEM_OUT


def summarize(dem_path: Path) -> None:
    """Print raster metadata; requires rasterio (installed in .venv)."""
    import rasterio

    with rasterio.open(dem_path) as ds:
        arr = ds.read(1)
        import numpy as np

        nodata = ds.nodata
        m = arr != nodata if nodata is not None else np.ones_like(arr, dtype=bool)
        stats = {
            "driver": ds.driver,
            "crs": str(ds.crs),
            "size_px": [ds.width, ds.height],
            "resolution_deg": [ds.transform.a, -ds.transform.e],
            "bounds": list(ds.bounds),
            "min_elev_m": float(arr[m].min()),
            "max_elev_m": float(arr[m].max()),
            "mean_elev_m": float(arr[m].mean()),
            "nodata": nodata,
        }
        print(json.dumps(stats, indent=2))
        # stash machine-readable summary next to the DEM
        (DATA_DIR / "dem_summary.json").write_text(json.dumps(stats, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--demtype", default="SRTMGL1",
                   help="SRTMGL1 (30m, default) | SRTMGL3 (90m) | COP30 | ...")
    args = p.parse_args()
    out = fetch_dem(args.demtype)
    summarize(out)
