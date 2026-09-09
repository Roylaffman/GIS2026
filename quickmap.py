"""quickmap.py — turn a place name into a ready "quick map" set.

One command -> a run folder web/runs/<slug>/ containing:
  run.json            (title, center, zoom, metadata)
  pois.geojson        (points of interest around the place)
  h3_hexagons.geojson (H3 aggregation of the POIs)
  dem.tif / dem_cog.tif (SRTM DEM + Cloud-Optimized copy)

View it at:
  http://127.0.0.1:8090/deck.html?run=<slug>     (Deck.gl)
  http://127.0.0.1:8090/kepler.html?run=<slug>   (Kepler.gl)

Open-source stack used here: Nominatim (OSM geocoder, no key),
OpenTopography SRTM, H3, GDAL/rasterio COG. SerpAPI only for the POI list
(optional: pass --pois none to skip it).

Usage:
  .venv\\Scripts\\python.exe quickmap.py "Grandfather Mountain, NC"
  .venv\\Scripts\\python.exe quickmap.py "Mount Washington NH" --query "hiking trails overlooks" --radius 0.05
  .venv\\Scripts\\python.exe quickmap.py "35.765,-82.265" --query "trails"   # or raw lat,lon
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from gis_common import WEB_DIR, load_env, http_get

RUNS_DIR = WEB_DIR / "runs"
# keep run data out of the root demo namespace? no - it's fine under web/runs

DEMTYPES = {"SRTMGL1": 30.0, "SRTMGL3": 90.0}


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "place"


def geocode_nominatim(place: str) -> dict:
    """OpenStreetMap Nominatim geocoder — free, no API key."""
    q = urllib.parse.quote(place)
    url = f"https://nominatim.openstreetmap.org/search?q={q}&format=json&limit=1"
    try:
        raw = http_get(url, timeout=30)
        results = json.loads(raw)
    except Exception as e:
        sys.exit(f"Geocoding failed: {e}")
    if not results:
        sys.exit(f"Nominatim found nothing for {place!r}")
    r = results[0]
    return {
        "lat": float(r["lat"]),
        "lon": float(r["lon"]),
        "display": r.get("display_name", place),
    }


def parse_center(text: str) -> dict:
    m = re.match(r"^\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*$", text)
    if m:
        return {"lat": float(m.group(1)), "lon": float(m.group(2)), "display": text}
    return geocode_nominatim(text)


def fetch_dem(center: dict, radius_deg: float, demtype: str, out_dir: Path) -> Path:
    env = load_env()
    key = env.get("OPENTOPO_API_KEY")
    if not key:
        sys.exit("OPENTOPO_API_KEY missing from .env")
    west = center["lon"] - radius_deg
    east = center["lon"] + radius_deg
    south = center["lat"] - radius_deg
    north = center["lat"] + radius_deg
    url = (
        "https://portal.opentopography.org/API/globaldem"
        f"?demtype={demtype}&south={south}&north={north}&west={west}&east={east}"
        f"&outputFormat=GTiff&API_Key={key}"
    )
    dem = out_dir / "dem.tif"
    http_get(url, dem)
    print(f"  DEM {demtype} -> {dem} ({dem.stat().st_size} bytes)")
    return dem


def fetch_pois(query: str, center: dict, out_dir: Path) -> int:
    env = load_env()
    key = env.get("SERPAPI_KEY")
    if not key:
        sys.exit("SERPAPI_KEY missing from .env (or use --pois none)")
    ll = f"@{center['lat']},{center['lon']},13z"
    params = {
        "engine": "google_maps", "q": query, "ll": ll,
        "type": "search", "hl": "en", "api_key": key,
    }
    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
    payload = json.loads(http_get(url))
    if payload.get("error"):
        sys.exit(f"SerpAPI error: {payload['error']}")
    results = list(payload.get("local_results") or [])
    pr = payload.get("place_results")
    if isinstance(pr, dict):
        results.append(pr)

    feats = []
    for r in results:
        gc = r.get("gps_coordinates") or {}
        if gc.get("latitude") is None or gc.get("longitude") is None:
            continue
        props = {k: v for k, v in {
            "name": r.get("title") or r.get("name"),
            "address": r.get("address"),
            "rating": r.get("rating"),
            "reviews": r.get("reviews"),
            "ptype": r.get("type"),
            "place_id": r.get("place_id"),
        }.items() if v not in (None, "")}
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point",
                         "coordinates": [gc["longitude"], gc["latitude"]]},
            "properties": props,
        })
    fc = {"type": "FeatureCollection", "features": feats}
    (out_dir / "pois.geojson").write_text(json.dumps(fc, indent=1))
    print(f"  SerpAPI -> {len(feats)} POIs")
    return len(feats)


def build_h3(pois_file: Path, out_dir: Path, res: int) -> int:
    import h3 as h3lib
    import numpy as np

    fc = json.loads(pois_file.read_text())
    feats = fc.get("features", [])
    if not feats:
        return 0
    cells = {}
    for f in feats:
        lon, lat = f["geometry"]["coordinates"]
        cell = h3lib.latlng_to_cell(lat, lon, res)
        p = f.get("properties", {})
        rating = p.get("rating")
        cells.setdefault(cell, {"count": 0, "ratings": [], "ptypes": []})
        c = cells[cell]
        c["count"] += 1
        if rating is not None:
            try: c["ratings"].append(float(rating))
            except (TypeError, ValueError): pass
        if p.get("ptype"):
            c["ptypes"].append(str(p["ptype"]))

    out_feats = []
    for cell, c in cells.items():
        bnd = h3lib.cell_to_boundary(cell)
        ring = [(lng, lat) for lat, lng in bnd]
        out_feats.append({
            "type": "Feature",
            "properties": {
                "h3": cell,
                "count": c["count"],
                "mean_rating": round(np.mean(c["ratings"]), 2) if c["ratings"] else None,
                "category": max(set(c["ptypes"]), key=c["ptypes"].count) if c["ptypes"] else None,
            },
            "geometry": {"type": "Polygon", "coordinates": [ring + [ring[0]]]},
        })
    out = {"type": "FeatureCollection", "features": out_feats}
    (out_dir / "h3_hexagons.geojson").write_text(json.dumps(out))
    print(f"  H3 res {res} -> {len(out_feats)} hexagons")
    return len(out_feats)


def make_cog(dem: Path, out_dir: Path) -> Path:
    import rasterio
    from rasterio.enums import Resampling

    cog = out_dir / "dem_cog.tif"
    with rasterio.open(dem) as src:
        profile = src.profile.copy()
        profile.update(driver="COG", tiled=True, compress="deflate")
        with rasterio.open(cog, "w", **profile) as dst:
            dst.write(src.read(1), 1)
            try:
                dst.build_overviews([2, 4, 8], Resampling.average)
            except Exception:
                pass
    print(f"  COG -> {cog}")
    return cog


def write_run_meta(out_dir: Path, title: str, center: dict, query: str | None, zoom: int) -> None:
    meta = {
        "title": title,
        "center": [center["lon"], center["lat"]],
        "zoom": zoom,
        "query": query,
        "created": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "display_name": center.get("display"),
    }
    (out_dir / "run.json").write_text(json.dumps(meta, indent=2))


def update_manifest() -> list[dict]:
    """Rebuild web/runs/index.json from every run.json under web/runs/."""
    runs = []
    if RUNS_DIR.exists():
        for run_json in sorted(RUNS_DIR.glob("*/run.json")):
            slug = run_json.parent.name
            meta = json.loads(run_json.read_text())
            runs.append({"slug": slug, **meta})
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / "index.json").write_text(
        json.dumps({"count": len(runs), "runs": runs}, indent=2)
    )
    return runs


def build_run(place: str, query: str | None, demtype: str, radius_deg: float, res: int, pois: str) -> str:
    print(f"== quickmap: {place} ==")
    center = parse_center(place)
    print(f"  center: {center['lat']:.5f}, {center['lon']:.5f}  ({center['display'][:70]})")

    slug = slugify(center["display"].split(",")[0] if "display" in center else place)
    out_dir = RUNS_DIR / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    dem = fetch_dem(center, radius_deg, demtype, out_dir)
    try:
        make_cog(dem, out_dir)
    except Exception as e:
        print(f"  (cog skipped: {e})")
    # terrain-RGB tiles so deck.html shows 3D terrain + hillshade
    try:
        from make_terrain import make_terrain
        make_terrain(dem, out_dir)
    except Exception as e:
        print(f"  (terrain skipped: {e})")

    n_pois = 0
    if pois == "serpapi":
        q = query or f"points of interest near {place.split(',')[0]}"
        n_pois = fetch_pois(q, center, out_dir)
    elif query:
        print("  (pois skipped - pass --pois serpapi to query SerpAPI)")
    else:
        print("  (pois skipped)")

    n_hex = 0
    pois_file = out_dir / "pois.geojson"
    if pois_file.exists() and n_pois:
        n_hex = build_h3(pois_file, out_dir, res)
        if n_hex == 0:
            (out_dir / "pois.geojson").unlink()

    title = place.split(",")[0].strip()
    write_run_meta(out_dir, title, center, query, zoom=13 if radius_deg <= 0.02 else 12)
    runs = update_manifest()

    print(f"\nDONE -> web/runs/{slug}/  ({len(runs)} run(s) total)")
    print(f"  Deck.gl   : http://127.0.0.1:8090/deck.html?run={slug}")
    print(f"  Kepler.gl : http://127.0.0.1:8090/kepler.html?run={slug}")
    return str(out_dir)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Quick maps: place name -> Deck.gl/Kepler.gl run")
    p.add_argument("place", help='Place name ("Grandfather Mountain, NC") or "lat,lon"')
    p.add_argument("--query", default=None, help="SerpAPI query for POIs")
    p.add_argument("--demtype", default="SRTMGL1", choices=sorted(DEMTYPES))
    p.add_argument("--radius", type=float, default=0.03,
                   help="half-box degrees around center (0.03 ~ 3 km)")
    p.add_argument("--res", type=int, default=8, help="H3 resolution")
    p.add_argument("--pois", choices=["serpapi", "none"], default="none",
                   help="POI source (serpapi needs SERPAPI_KEY)")
    args = p.parse_args()
    build_run(args.place, args.query, args.demtype, args.radius, args.res, args.pois)
