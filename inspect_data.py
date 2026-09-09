"""inspect_data.py — load and check any vector dataset (GeoJSON/Shapefile/
GeoParquet/CSV) and produce a QA report.

Answers "what is actually in this file?" before you map it:
  - file/format/driver, row + geometry counts
  - CRS + bounds (native and WGS84)
  - geometry type breakdown
  - per-column: type, non-null count, null count, # unique (and min/max for numerics)
  - coordinate sanity (lat/lng ranges)
  - duplicate geometry detection

Outputs (all optional, printed to stdout by default):
  --out report.json   machine-readable summary
  --bounds out.geojson  a bounding-box polygon (for quick map overlay)

Usage:
  .venv\\Scripts\\python.exe inspect_data.py data/pois.geojson
  .venv\\Scripts\\python.exe inspect_data.py runs/<slug>/pois.geojson --out r.json --bounds r_bounds.geojson
  .venv\\Scripts\\python.exe inspect_data.py data.csv --x lon --y lat
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from gis_common import fix_proj


def _read_table(path: Path, xcol: str | None, ycol: str | None):
    import pandas as pd
    import geopandas as gpd

    suffix = path.suffix.lower()
    if suffix == ".csv":
        if not (xcol and ycol):
            sys.exit("CSV needs --x <loncol> --y <latcol> to build points")
        df = pd.read_csv(path)
        if xcol not in df.columns or ycol not in df.columns:
            sys.exit(f"columns {xcol}/{ycol} not in CSV (have {list(df.columns)[:12]})")
        gdf = gpd.GeoDataFrame(
            df, geometry=gpd.points_from_xy(df[xcol], df[ycol]), crs="EPSG:4326"
        )
        return gdf
    try:
        return gpd.read_file(path)
    except Exception as e:
        sys.exit(f"Could not read {path}: {e}")


def summarize(gdf, path: Path) -> dict:
    import numpy as np

    summary: dict = {
        "file": str(path),
        "rows": int(len(gdf)),
        "columns": [str(c) for c in gdf.columns],
        "geometry_type": {str(k): int(v) for k, v in gdf.geometry.geom_type.value_counts().items()},
    }
    crs = gdf.crs
    summary["crs"] = str(crs) if crs is not None else None
    summary["bounds_native"] = [float(v) for v in gdf.total_bounds]

    # WGS84 bounds (reproject if needed)
    try:
        g4326 = gdf.to_crs("EPSG:4326")
        summary["bounds_wgs84"] = [round(float(v), 6) for v in g4326.total_bounds]
    except Exception as e:
        summary["bounds_wgs84"] = None
        summary["bounds_wgs84_error"] = str(e)

    # coordinate sanity (on WGS84 if we have it, else native)
    b = summary.get("bounds_wgs84") or summary["bounds_native"]
    summary["coord_sanity"] = {
        "lon_in_range": -180 <= b[0] <= b[2] <= 180,
        "lat_in_range": -90 <= b[1] <= b[3] <= 90,
    }

    # per-column stats
    cols = []
    for c in gdf.columns:
        if c == gdf.geometry.name:
            continue
        s = gdf[c]
        info = {"name": str(c), "dtype": str(s.dtype), "nulls": int(s.isna().sum())}
        try:
            info["unique"] = int(s.nunique(dropna=True))
        except Exception:
            pass
        try:
            is_numeric = np.issubdtype(s.dtype, np.number)
        except TypeError:
            is_numeric = False
        if is_numeric:
            try:
                info["min"] = float(s.min())
                info["max"] = float(s.max())
            except Exception:
                pass
        else:
            # non-numeric: try a numeric coercion to catch "5.0" strings, but
            # don't fail on uncoercible columns
            try:
                num = pd.to_numeric(s, errors="coerce")
                if num.notna().any():
                    info["min"] = float(num.min())
                    info["max"] = float(num.max())
            except Exception:
                pass
        cols.append(info)
    summary["columns_detail"] = cols

    # duplicate geometry detection
    try:
        summary["duplicate_geometries"] = int(gdf.geometry.duplicated().sum())
    except Exception:
        summary["duplicate_geometries"] = None

    summary["feature_count"] = int(len(gdf))
    summary["empty_geometries"] = int(gdf.geometry.is_empty.sum()) if hasattr(gdf.geometry, "is_empty") else 0
    return summary


def _fmt(s: dict) -> str:
    lines = []
    lines.append(f"File: {s['file']}")
    lines.append(f"Rows/features: {s['rows']}")
    lines.append(f"CRS: {s['crs']}")
    lines.append(f"Geometry types: {s['geometry_type']}")
    nb = s.get("bounds_native")
    wb = s.get("bounds_wgs84")
    lines.append(f"Bounds (native): {[round(x,6) for x in nb] if nb else None}")
    lines.append(f"Bounds (WGS84):  {wb if wb else '(n/a)'}")
    cs = s.get("coord_sanity") or {}
    lines.append(f"Coordinate sanity: lon {cs.get('lon_in_range')}, lat {cs.get('lat_in_range')}")
    lines.append(f"Duplicate geometries: {s.get('duplicate_geometries')}, empty: {s.get('empty_geometries')}")
    lines.append("Columns:")
    for c in s.get("columns_detail", []):
        extra = f"  min={c['min']} max={c['max']}" if "min" in c else ""
        lines.append(f"  - {c['name']} ({c['dtype']}) nulls={c['nulls']} unique={c.get('unique','?')}{extra}")
    return "\n".join(lines)


def write_bounds_geojson(s: dict, out: Path) -> None:
    wb = s.get("bounds_wgs84")
    if not wb:
        print("(no WGS84 bounds; skipping --bounds)")
        return
    xmin, ymin, xmax, ymax = wb
    fc = {"type": "FeatureCollection", "features": [{
        "type": "Feature",
        "properties": {"name": Path(s["file"]).stem + " extent"},
        "geometry": {"type": "Polygon", "coordinates": [[
            [xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax], [xmin, ymin]]]},
    }]}
    out.write_text(json.dumps(fc))
    print(f"bounds -> {out}")


if __name__ == "__main__":
    fix_proj()
    p = argparse.ArgumentParser(description="Inspect a vector dataset")
    p.add_argument("path", help="path to GeoJSON/Shapefile/GeoParquet/CSV")
    p.add_argument("--x", default=None, help="CSV longitude column")
    p.add_argument("--y", default=None, help="CSV latitude column")
    p.add_argument("--out", default=None, help="write JSON summary here")
    p.add_argument("--bounds", default=None, help="write bbox GeoJSON here")
    args = p.parse_args()

    gdf = _read_table(Path(args.path), args.x, args.y)
    s = summarize(gdf, Path(args.path))
    print(_fmt(s))
    if args.out:
        Path(args.out).write_text(json.dumps(s, indent=2))
        print(f"\nsummary -> {args.out}")
    if args.bounds:
        write_bounds_geojson(s, Path(args.bounds))
