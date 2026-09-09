"""make_dashboard.py — prepare a run for the open-source "dashboard" view.

Mirrors the geoglypha flood-dashboard pattern (Mapbox layers + legend +
cross-section chart) but fully open-source and data-driven:

  layers.json   manifest of GeoJSON datasets to render, with style + visibility
  profile.json  REAL elevation cross-section sampled from the DEM (W->E transect)

The dashboard page (web/dashboard.html) reads these plus run.json and
terrain.json (from make_terrain.py) and renders everything with MapLibre GL +
Chart.js — no Mapbox token, no hand-authored data.

Usage:
  .venv\\Scripts\\python.exe make_dashboard.py <run_dir> [<run_dir> ...]
  .venv\\Scripts\\python.exe make_dashboard.py web            # root demo
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import rasterio


def sample_profile(dem: Path, num: int = 80) -> dict:
    """Sample elevation along a west->east transect through the DEM center."""
    with rasterio.open(dem) as ds:
        band = ds.read(1).astype("float64")
        nodata = ds.nodata
        left, bottom, right, top = ds.bounds
        lons = np.linspace(left, right, num)
        lat = (bottom + top) / 2.0
        # row/col for the center latitude
        cols = np.linspace(0, ds.width - 1, num)
        row = ds.index(left, lat)[0]
        elev = band[row, np.round(cols).astype(int)]
        if nodata is not None:
            elev = np.where(elev == nodata, np.nan, elev)
    # distances in km along the transect
    dist_km = np.linspace(0.0, (right - left) * 111.32 * np.cos(np.radians(lat)), num)
    return {
        "title": "Elevation cross-section (W\u2192E)",
        "xLabel": "distance (km)",
        "yLabel": "elevation (m)",
        "distances": [round(float(d), 3) for d in dist_km],
        "elevations": [round(float(e), 1) if not np.isnan(e) else None for e in elev],
        "min": round(float(np.nanmin(elev)), 1),
        "max": round(float(np.nanmax(elev)), 1),
    }


def build_layers(run_dir: Path) -> dict:
    """Build a layer manifest from whatever datasets exist in the run."""
    layers = []
    if (run_dir / "h3_hexagons.geojson").exists():
        layers.append({
            "id": "h3-density", "label": "POI density (H3)", "type": "fill",
            "file": "h3_hexagons.geojson", "color": "#1565c0", "opacity": 0.45,
            "outline": "#0d47a1", "visible": True,
        })
    if (run_dir / "pois.geojson").exists():
        layers.append({
            "id": "poi-points", "label": "Points of interest", "type": "circle",
            "file": "pois.geojson", "color": "#ff8f00", "radius": 5,
            "stroke": "#ffffff", "strokeWidth": 1, "visible": True,
        })
    if (run_dir / "dem_cog.tif").exists() or (run_dir / "dem.tif").exists():
        layers.append({
            "id": "dem-extent", "label": "DEM extent", "type": "line",
            "file": "dem_extent.geojson", "color": "#b71c1c", "width": 1.5,
            "dash": [2, 2], "visible": False,
        })
    return {"layers": layers}


def write_dem_extent(run_dir: Path, dem: Path) -> None:
    with rasterio.open(dem) as ds:
        l, b, r, t = ds.bounds
    fc = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature", "properties": {"name": "DEM extent"},
            "geometry": {"type": "Polygon", "coordinates": [[
                [l, b], [r, b], [r, t], [l, t], [l, b]]]},
        }],
    }
    (run_dir / "dem_extent.geojson").write_text(json.dumps(fc))


def make_dashboard(run_dir: Path) -> None:
    run_dir = Path(run_dir)
    dem = run_dir / "dem.tif"
    if not dem.exists():
        dem = run_dir / "dem_cog.tif"
    if not dem.exists():
        # root demo uses data/dem_mount_mitchell.tif
        alt = Path("data") / "dem_mount_mitchell.tif"
        dem = alt if alt.exists() else None
    if dem is None or not Path(dem).exists():
        print(f"  ({run_dir}: no DEM found - skipping profile)")
        dem = None
    else:
        profile = sample_profile(dem)
        (run_dir / "profile.json").write_text(json.dumps(profile, indent=2))
        print(f"  profile.json: {profile['min']}..{profile['max']} m over {profile['distances'][-1]:.2f} km")
        write_dem_extent(run_dir, dem)

    manifest = build_layers(run_dir)
    if manifest["layers"]:
        (run_dir / "layers.json").write_text(json.dumps(manifest, indent=2))
        print(f"  layers.json: {[l['id'] for l in manifest['layers']]}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("dirs", nargs="+", help="run dir(s) or web (root demo)")
    args = p.parse_args()
    for d in args.dirs:
        print(f"== dashboard: {d} ==")
        make_dashboard(Path(d))
