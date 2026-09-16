"""fetch_grid_pois.py — query POIs across a WIDE area (grid of SerpAPI queries)
and build an H3 density layer that matches the surrounding DEM grid.

A single SerpAPI Google Maps query is radius-limited (~top 20 results around
one point). To fill a wide topic area (e.g. the n x n DEM grid), this script
queries at a grid of centers, merges + dedupes the results, and rebuilds H3.

Usage:
  .venv\\Scripts\\python.exe fetch_grid_pois.py 35.7649 -82.2651 --n 4 --cell 0.08 \
      --query "hiking trails waterfalls overlooks" --out web/topics/mount-mitchell
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from pathlib import Path

from gis_common import fix_proj, load_env, http_get


def _serp(query: str, lat: float, lon: float, zoom: int, key: str) -> list[dict]:
    ll = f"@{lat},{lon},{zoom}z"
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
    return results


def to_feature(r: dict) -> dict | None:
    gc = r.get("gps_coordinates") or {}
    if gc.get("latitude") is None or gc.get("longitude") is None:
        return None
    props = {k: v for k, v in {
        "name": r.get("title") or r.get("name"),
        "address": r.get("address"),
        "rating": r.get("rating"),
        "reviews": r.get("reviews"),
        "ptype": r.get("type"),
        "place_id": r.get("place_id"),
    }.items() if v not in (None, "")}
    return {"type": "Feature",
            "geometry": {"type": "Point",
                         "coordinates": [gc["longitude"], gc["latitude"]]},
            "properties": props}


def fetch_grid_pois(center_lat: float, center_lon: float, n: int, cell_deg: float,
                    query: str, out_dir: Path, query_step: int = 1, zoom: int = 13) -> dict:
    fix_proj()
    env = load_env()
    key = env.get("SERPAPI_KEY")
    if not key:
        sys.exit("SERPAPI_KEY missing from .env")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # grid bbox (+ one cell of buffer to keep near-edge results)
    half = n * cell_deg / 2
    bbox = (center_lon - half - cell_deg, center_lat - half - cell_deg,
            center_lon + half + cell_deg, center_lat + half + cell_deg)

    seen = set()
    feats: list[dict] = []
    qcount = 0
    for i in range(0, n, query_step):
        for j in range(0, n, query_step):
            dy = (i - (n - 1) / 2) * cell_deg
            dx = (j - (n - 1) / 2) * cell_deg
            lat = center_lat + dy
            lon = center_lon + dx
            qcount += 1
            for r in _serp(query, lat, lon, zoom, key):
                f = to_feature(r)
                if not f:
                    continue
                flon, flat = f["geometry"]["coordinates"]
                # keep only results inside the grid bbox (SerpAPI sometimes
                # returns far regional matches for a generic query)
                if not (bbox[0] <= flon <= bbox[2] and bbox[1] <= flat <= bbox[3]):
                    continue
                pid = f["properties"].get("place_id")
                key_id = pid or (round(flon, 5), round(flat, 5),
                                 f["properties"].get("name"))
                if key_id in seen:
                    continue
                seen.add(key_id)
                feats.append(f)

    fc = {"type": "FeatureCollection", "features": feats}
    (out_dir / "pois_grid.geojson").write_text(json.dumps(fc, indent=1))
    print(f"  {qcount} SerpAPI queries -> {len(feats)} unique POIs")

    # H3 density
    import h3 as h3lib
    import numpy as np
    cells = {}
    for f in feats:
        lon, lat = f["geometry"]["coordinates"]
        cell = h3lib.latlng_to_cell(lat, lon, 8)
        p = f.get("properties", {})
        rating = p.get("rating")
        cells.setdefault(cell, {"count": 0, "ratings": [], "ptypes": []})
        c = cells[cell]
        c["count"] += 1
        if rating is not None:
            try:
                c["ratings"].append(float(rating))
            except (TypeError, ValueError):
                pass
        if p.get("ptype"):
            c["ptypes"].append(str(p["ptype"]))
    out_feats = []
    for cell, c in cells.items():
        bnd = h3lib.cell_to_boundary(cell)
        ring = [(lng, lat) for lat, lng in bnd]
        out_feats.append({"type": "Feature",
                          "properties": {
                              "h3": cell, "count": c["count"],
                              "mean_rating": round(np.mean(c["ratings"]), 2) if c["ratings"] else None,
                              "category": max(set(c["ptypes"]), key=c["ptypes"].count) if c["ptypes"] else None},
                          "geometry": {"type": "Polygon", "coordinates": [ring + [ring[0]]]}})
    (out_dir / "h3_grid.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "features": out_feats}))
    print(f"  H3 res 8 -> {len(out_feats)} hexagons")
    return {"pois": len(feats), "hexagons": len(out_feats), "queries": qcount}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Query POIs across a grid and rebuild H3")
    p.add_argument("lat", type=float)
    p.add_argument("lon", type=float)
    p.add_argument("--n", type=int, default=4)
    p.add_argument("--cell", type=float, default=0.08)
    p.add_argument("--query", default="points of interest")
    p.add_argument("--step", type=int, default=1, help="query every k-th cell (default 1 = every cell)")
    p.add_argument("--zoom", type=int, default=13)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    fetch_grid_pois(args.lat, args.lon, args.n, args.cell, args.query,
                    Path(args.out), args.step, args.zoom)
