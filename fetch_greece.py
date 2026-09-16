"""fetch_greece.py — pull DEMs around ancient Greek sites + Aegean bathymetry.

DEMs (OpenTopography SRTMGL1, 30 m) are fetched around each site and turned
into quickmap runs (terrain + dashboard profile). Bathymetry (EMODnet mean
depth, no key) is fetched for the Cyclades, which overlaps the island sites
(Delos, Santorini/Akrotiri, Paros).

Usage:
  .venv\\Scripts\\python.exe fetch_greece.py            # all sites
  .venv\\Scripts\\python.exe fetch_greece.py --only delos
"""
from __future__ import annotations

import argparse
import urllib.parse
from pathlib import Path

from gis_common import DATA_DIR, WEB_DIR, fix_proj, http_get
from quickmap import (
    fetch_dem, geocode_nominatim, make_cog, slugify, write_run_meta, update_manifest,
)

# ancient sites (name -> optional display slug). Nominatim resolves coordinates.
SITES = [
    ("Acropolis of Athens, Greece", None),
    ("Delphi archaeological site, Greece", None),
    ("Olympia archaeological site, Greece", None),
    ("Knossos, Crete, Greece", None),
    ("Delos island, Greece", None),
    ("Akrotiri, Santorini, Greece", None),
    ("Mycenae, Greece", None),
    ("Epidaurus ancient theatre, Greece", None),
]

DEM_RADIUS = 0.05   # ~5.5 km half-box around each site
BATHY_BBOX = (24.5, 36.0, 26.5, 38.0)  # Cyclades (overlaps Delos/Santorini)
BATHY_OUT = DATA_DIR / "greece" / "aegean_cyclades_bathymetry.tif"


def safe(s) -> str:
    return str(s).encode("ascii", "replace").decode()


def log(msg: str) -> None:
    print(safe(msg))


def fetch_bathymetry(bbox, out: Path, width=1600, height=1600) -> Path:
    params = {
        "service": "WCS",
        "version": "1.0.0",
        "request": "GetCoverage",
        "coverage": "emodnet:mean",
        "bbox": f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}",
        "crs": "EPSG:4326",
        "format": "GeoTIFF",
        "width": str(width),
        "height": str(height),
    }
    url = "https://ows.emodnet-bathymetry.eu/wcs?" + urllib.parse.urlencode(params)
    out.parent.mkdir(parents=True, exist_ok=True)
    data = http_get(url, out, timeout=240)
    log(f"bathymetry -> {out} ({len(data)} bytes)")
    return out


def run_site(name: str) -> None:
    log(f"\n== {name} ==")
    center = geocode_nominatim(name)
    log(f"  center: {center['lat']:.5f}, {center['lon']:.5f} ({center['display'][:60]})")
    # slug from the ENGLISH query string (geocoded display_name may be Greek)
    slug = slugify(name.split(",")[0])
    out_dir = WEB_DIR / "runs" / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    dem = fetch_dem(center, DEM_RADIUS, "SRTMGL1", out_dir)
    try:
        make_cog(dem, out_dir)
    except Exception as e:
        log(f"  (cog skipped: {e})")
    try:
        from make_terrain import make_terrain
        make_terrain(dem, out_dir, min_zoom=9, max_zoom=13)
    except Exception as e:
        log(f"  (terrain skipped: {e})")
    try:
        from make_dashboard import make_dashboard
        make_dashboard(out_dir)
    except Exception as e:
        log(f"  (dashboard skipped: {e})")

    write_run_meta(out_dir, name.split(",")[0].strip(), center, None, zoom=12)


def main(only: str | None) -> None:
    fix_proj()
    sites = [s for s in SITES if (not only or slugify(s[0].split(",")[0]) == only or only in s[0].lower())]
    if only and not sites:
        log(f"no site matched --only {only!r}")
        return
    for name, _ in sites:
        run_site(name)

    log("\n== Aegean bathymetry (EMODnet) ==")
    bathy = fetch_bathymetry(BATHY_BBOX, BATHY_OUT)

    # colorized tiles + a dedicated Cyclades run (bathymetry + island extents)
    log("\n== Aegean colorized bathymetry run ==")
    try:
        from make_bathymetry import make_bathymetry
        make_bathymetry(bathy, WEB_DIR / "runs" / "aegean-cyclades")
    except Exception as e:
        log(f"  (bathymetry tiles skipped: {e})")

    update_manifest()
    log("\nDONE. Runs registered in web/runs/index.json; hub: /runs.html")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--only", default=None, help="limit to one site (substring or slug)")
    args = p.parse_args()
    main(args.only)
