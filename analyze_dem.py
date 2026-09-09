"""analyze_dem.py — load and analyze a DEM or bathymetry raster.

Auto-detects bathymetry (values <= 0) vs terrain and reports/derives:
  - metadata: size, resolution, CRS, nodata, bounds
  - statistics: min/max/mean/median/std, valid-cell coverage
  - hypsometry: elevation/depth histogram (bins -> cell count + area)
  - volume: total volume above/below a reference level (e.g. water volume for
    bathymetry, or earthwork volume for terrain above a base plane)
  - derivatives: slope, aspect, hillshade (written as GeoTIFF / PNG)
  - transect: W->E elevation/depth profile (JSON, same schema the dashboard uses)

Outputs (into --outdir, default data/):
  <stem>_slope.tif, <stem>_aspect.tif, <stem>_hillshade.png,
  <stem>_profile.json, <stem>_histogram.json, <stem>_report.json

Usage:
  .venv\\Scripts\\python.exe analyze_dem.py data/dem_mount_mitchell.tif
  .venv\\Scripts\\python.exe analyze_dem.py my_bathymetry.tif --reference 0 --outdir out/
"""
from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

import numpy as np

from gis_common import DATA_DIR, fix_proj

# PNG artifacts carry no georeferencing (XYZ/image use); suppress the warning
try:
    import rasterio.errors
    warnings.filterwarnings("ignore", category=rasterio.errors.NotGeoreferencedWarning)
except Exception:
    pass


def read_band(path: Path):
    import rasterio
    ds = rasterio.open(path)
    band = ds.read(1).astype("float64")
    nodata = ds.nodata
    mask = (band == nodata) if nodata is not None else np.zeros_like(band, dtype=bool)
    valid = np.where(~mask)
    return ds, band, valid


def hillshade(band, transform, az=315.0, alt=45.0):
    import rasterio.warp
    x, y = np.gradient(band)
    slope = np.pi / 2 - np.arctan(np.sqrt(x * x + y * y))
    aspect = np.arctan2(-x, y)
    azr = np.radians(az)
    altr = np.radians(alt)
    shaded = np.sin(altr) * np.sin(slope) + np.cos(altr) * np.cos(slope) * np.cos(azr - aspect)
    return np.clip(255 * (shaded + 1) / 2, 0, 255).astype("uint8")


def write_geotiff(path, arr, profile):
    import rasterio
    prof = profile.copy()
    prof.update(driver="GTiff", count=1, dtype=arr.dtype, compress="deflate")
    with rasterio.open(path, "w", **prof) as dst:
        dst.write(arr, 1)


def write_png(path, arr):
    import rasterio
    from rasterio.transform import from_origin
    # simple non-georeferenced PNG (XYZ/plain image); viewers don't need georef here
    with rasterio.open(path, "w", driver="PNG", width=arr.shape[1], height=arr.shape[0],
                       count=1, dtype="uint8") as dst:
        dst.write(arr, 1)


def sample_profile(ds, band, num=80):
    left, bottom, right, top = ds.bounds
    lat = (bottom + top) / 2.0
    cols = np.linspace(0, ds.width - 1, num).round().astype(int)
    row = ds.index(left, lat)[0]
    elev = band[row, cols]
    dist_km = np.linspace(0.0, (right - left) * 111.32 * np.cos(np.radians(lat)), num)
    return {
        "title": "Elevation/depth profile (W\u2192E)",
        "xLabel": "distance (km)",
        "yLabel": "value (m)",
        "distances": [round(float(d), 3) for d in dist_km],
        "values": [round(float(e), 1) if np.isfinite(e) else None for e in elev],
        "min": round(float(np.nanmin(elev)), 1),
        "max": round(float(np.nanmax(elev)), 1),
    }


def analyze(path: Path, outdir: Path, reference: float | None, num_bins: int) -> dict:
    import rasterio
    ds, band, valid = read_band(path)
    vals = band[valid]
    n_valid = int(vals.size)
    n_total = int(band.size)

    # resolution in native CRS units
    res_x = abs(ds.transform.a)
    res_y = abs(ds.transform.e)

    # cell area in real metres (approx) — handle degree-based CRS
    is_geographic = ds.crs and ds.crs.is_geographic
    if is_geographic:
        mid_lat = (ds.bounds[1] + ds.bounds[3]) / 2.0
        m_per_deg_lat = 111132.0
        m_per_deg_lon = 111320.0 * np.cos(np.radians(mid_lat))
        cell_area_m2 = res_x * m_per_deg_lon * res_y * m_per_deg_lat
        area_unit = "m2"
    else:
        cell_area_m2 = res_x * res_y
        area_unit = ds.crs.linear_units if ds.crs else "unit2"
    cell_area = cell_area_m2
    area_total = n_valid * cell_area

    mn, mx = float(vals.min()), float(vals.max())
    is_bathy = mx <= 0
    ref = reference if reference is not None else 0.0

    hist, edges = np.histogram(vals, bins=num_bins)
    histogram = {
        "bins": [round(float(e), 2) for e in edges],
        "counts": [int(h) for h in hist],
        "area_m2": [round(float(h * cell_area), 3) for h in hist],
    }

    # volume relative to reference
    if is_bathy:
        # water volume below reference (depths negative)
        depth = ref - vals  # positive below reference
        volume = float((depth * cell_area).sum())
        volume_label = "water_volume_m3"
    else:
        height = vals - ref
        volume = float((height * cell_area).sum())
        volume_label = "volume_m3_above_ref"

    # slope + aspect + hillshade (write artifacts)
    slope = np.degrees(np.arctan(np.hypot(*np.gradient(band)) * max(res_x, res_y) / 1.0))
    aspect = np.degrees(np.arctan2(*np.gradient(band)))
    hs = hillshade(band, ds.transform)

    stem = path.stem
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    write_geotiff(outdir / f"{stem}_slope.tif", slope, ds.profile)
    write_geotiff(outdir / f"{stem}_aspect.tif", aspect, ds.profile)
    write_png(outdir / f"{stem}_hillshade.png", hs)

    profile = sample_profile(ds, band)
    (outdir / f"{stem}_profile.json").write_text(json.dumps(profile, indent=2))
    (outdir / f"{stem}_histogram.json").write_text(json.dumps(histogram, indent=2))

    report = {
        "file": str(path),
        "kind": "bathymetry" if is_bathy else "terrain",
        "size_px": [ds.width, ds.height],
        "resolution": [round(res_x, 6), round(res_y, 6)],
        "crs": str(ds.crs),
        "nodata": ds.nodata,
        "valid_cells": n_valid,
        "total_cells": n_total,
        "coverage_pct": round(100.0 * n_valid / n_total, 2) if n_total else 0,
        "min": mn,
        "max": mx,
        "mean": round(float(vals.mean()), 2),
        "median": round(float(np.median(vals)), 2),
        "std": round(float(vals.std()), 2),
        "reference_level": ref,
        volume_label: round(volume, 3),
        "area_m2": round(float(area_total), 3),
        "bounds": [round(float(v), 6) for v in ds.bounds],
    }
    (outdir / f"{stem}_report.json").write_text(json.dumps(report, indent=2))
    return report


def _fmt(r: dict) -> str:
    lines = [
        f"File: {r['file']}",
        f"Kind: {r['kind'].upper()}",
        f"Size: {r['size_px'][0]}x{r['size_px'][1]}  res {r['resolution']}",
        f"CRS: {r['crs']}",
        f"Values: min={r['min']} max={r['max']} mean={r['mean']} median={r['median']} std={r['std']}",
        f"Coverage: {r['valid_cells']}/{r['total_cells']} ({r['coverage_pct']}%)",
    ]
    vol_key = "water_volume_m3" if "water_volume_m3" in r else "volume_m3_above_ref"
    lines.append(f"{vol_key} (rel {r['reference_level']} m): {r.get(vol_key)}  | area: {r['area_m2']} m2")
    return "\n".join(lines)


if __name__ == "__main__":
    fix_proj()
    p = argparse.ArgumentParser(description="Analyze a DEM or bathymetry raster")
    p.add_argument("path", help="GeoTIFF to analyze")
    p.add_argument("--outdir", default=str(DATA_DIR), help="output directory (default data/)")
    p.add_argument("--reference", type=float, default=None,
                   help="reference level for volume (default 0: sea level / datum)")
    p.add_argument("--bins", type=int, default=20, help="hypsometry histogram bins")
    args = p.parse_args()

    r = analyze(Path(args.path), Path(args.outdir), args.reference, args.bins)
    print(_fmt(r))
    print(f"\nartifacts -> {Path(args.outdir) / (Path(args.path).stem + '_*.tif/png/json')}")
