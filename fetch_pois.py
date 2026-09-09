"""Query points of interest around the Mount Mitchell DEM tile using the
SerpAPI Google Maps engine (SERPAPI_KEY from .env).

Output: data/pois_raw.json (full SerpAPI reply), data/pois.geojson (cleaned,
CRS84 points with name/address/rating/place id where available).
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from pathlib import Path

from gis_common import AOI, DATA_DIR, SUMMIT_LAT, SUMMIT_LON, load_env, http_get

RAW_OUT = DATA_DIR / "pois_raw.json"
GEOJSON_OUT = DATA_DIR / "pois.geojson"

API = "https://serpapi.com/search.json"


def fetch_pois(query: str, zoom: int = 13) -> dict:
    env = load_env()
    key = env.get("SERPAPI_KEY")
    if not key:
        sys.exit("SERPAPI_KEY missing from .env")
    ll = f"@{SUMMIT_LAT},{SUMMIT_LON},{zoom}z"
    params = {
        "engine": "google_maps",
        "q": query,
        "ll": ll,
        "type": "search",
        "hl": "en",
        "api_key": key,
    }
    url = API + "?" + urllib.parse.urlencode(params)
    print(f"SerpAPI query: {query!r} centered at {ll}")
    raw = http_get(url, RAW_OUT)
    return json.loads(raw)


def to_geojson(payload: dict) -> dict:
    feats = []
    results = []
    results += payload.get("local_results") or []
    pr = payload.get("place_results")
    if isinstance(pr, dict):
        results.append(pr)
    elif isinstance(pr, list):
        results += pr
    for r in results:
        gc = r.get("gps_coordinates") or {}
        lat, lng = gc.get("latitude"), gc.get("longitude")
        if lat is None or lng is None:
            continue  # skip entries without coordinates
        props = {
            "name": r.get("title") or r.get("name"),
            "address": r.get("address"),
            "rating": r.get("rating"),
            "reviews": r.get("reviews"),
            "type": r.get("type"),
            "place_id": r.get("place_id") or r.get("place_id_search"),
            "phone": r.get("phone"),
            "website": r.get("website"),
            "thumbnail": r.get("thumbnail"),
        }
        props = {k: v for k, v in props.items() if v not in (None, "", [])}
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lng, lat]},
            "properties": props,
        })
    return {
        "type": "FeatureCollection",
        "name": payload.get("search_metadata", {}).get("raw_html_file", "serp"),
        "features": feats,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--query", default="hiking trails near Mount Mitchell NC")
    p.add_argument("--zoom", type=int, default=13)
    p.add_argument("--save-name", default=None, help="extra GeoJSON filename")
    args = p.parse_args()

    payload = fetch_pois(args.query, zoom=args.zoom)
    if payload.get("error"):
        sys.exit(f"SerpAPI error: {payload['error']}")
    fc = to_geojson(payload)
    GEOJSON_OUT.write_text(json.dumps(fc, indent=1))
    print(f"Saved {len(fc['features'])} POIs -> {GEOJSON_OUT}")
    if args.save_name:
        extra = DATA_DIR / args.save_name
        extra.write_text(json.dumps(fc, indent=1))
        print(f"Also saved -> {extra}")
    for f in fc["features"][:10]:
        pr = f["properties"]
        print(f"  - {pr.get('name')} | {pr.get('type')} | {pr.get('rating')}* | "
              f"{f['geometry']['coordinates']}")
