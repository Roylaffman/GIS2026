"""Aggregate the Mount Mitchell POIs into H3 hexagonal cells (open-source
hexagonal grid index) and export the result for Deck.gl / Kepler.gl.

Outputs:
  web/h3_hexagons.geojson  - H3 cells (res 8 by default) with POI counts,
                             mean rating, and category breakdown
  data/h3_summary.json     - machine-readable stats
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import h3
import pandas as pd
from shapely.geometry import Polygon

from gis_common import DATA_DIR, WEB_DIR

POIS = DATA_DIR / "pois.geojson"
OUT = WEB_DIR / "h3_hexagons.geojson"


def build_hexagons(res: int = 8) -> None:
    gdf = gpd.read_file(POIS)  # EPSG:4326 (GeoJSON)
    gdf = gdf.to_crs(epsg=4326)
    # lon/lat per point
    lons = gdf.geometry.x.to_numpy()
    lats = gdf.geometry.y.to_numpy()

    # assign each POI an H3 cell at `res` (res 8 ~ 0.737 km avg edge)
    cells = [h3.latlng_to_cell(lat, lon, res) for lat, lon in zip(lats, lons)]
    gdf["h3"] = cells

    # optional: include name/category for downstream tooltips
    name = gdf.columns[-1] if False else None

    rows = []
    for cell, grp in gdf.groupby("h3"):
        polys = grp.geometry
        # category: take the most common value if a 'type' field exists
        cat = None
        if "type" in grp.columns:
            cat = grp["type"].mode(dropna=True)
            cat = cat.iloc[0] if len(cat) else None
        rows.append({
            "h3": cell,
            "count": int(len(grp)),
            "mean_rating": float(grp["rating"].mean()) if "rating" in grp.columns else None,
            "lat": float(polys.y.mean()),
            "lng": float(polys.x.mean()),
            "category": cat,
        })

    df = pd.DataFrame(rows)
    # hexagon polygon geometry for each cell (H3 -> GeoJSON polygon)
    df["geometry"] = [
        Polygon(
            [(lon, lat) for lat, lon in
             h3.cell_to_boundary(h)]  # boundary returns (lat, lng) pairs
        )
        for h in df["h3"]
    ]
    hexgdf = gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326")

    WEB_DIR.mkdir(exist_ok=True)
    hexgdf.to_file(OUT, driver="GeoJSON")
    print(f"H3 res {res}: {len(hexgdf)} hexagons covering {len(gdf)} POIs")
    print("cells:", sorted(df["h3"])[:10], "...")

    summary = {
        "resolution": res,
        "n_hexagons": len(hexgdf),
        "n_pois": len(gdf),
        "max_count": int(df["count"].max()) if len(df) else 0,
        "hexagons_with_1_poi": int((df["count"] == 1).sum()),
    }
    (DATA_DIR / "h3_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    print("wrote", OUT)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--res", type=int, default=8,
                   help="H3 resolution (8 ~ 0.74 km, 9 ~ 0.17 km)")
    args = p.parse_args()
    build_hexagons(args.res)
