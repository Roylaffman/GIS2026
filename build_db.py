"""Load the Mount Mitchell DEM + POIs into a DuckDB spatial database and run
GIS analysis queries (summit stats, POI counts, distances from summit).

Outputs:
  data/gis.duckdb        - the database
  web/pois.geojson       - POIs as served to the map (from DuckDB query)
  web/dem_bounds.geojson - DEM tile footprint
  data/query_report.txt  - analysis results (also printed)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb

from gis_common import AOI, DATA_DIR, SUMMIT_LAT, SUMMIT_LON, SUMMIT_NAME, WEB_DIR

DB_PATH = DATA_DIR / "gis.duckdb"
DEM_TIF = DATA_DIR / "dem_mount_mitchell.tif"


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(DB_PATH))
    # keep extension cache inside the workspace (sandbox-friendly)
    ext_dir = DATA_DIR / "duckdb_ext"
    ext_dir.mkdir(parents=True, exist_ok=True)
    con.execute(f"SET extension_directory='{ext_dir.as_posix()}'")
    con.execute("INSTALL spatial")
    con.execute("LOAD spatial")
    return con


def ingest(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE OR REPLACE TABLE summit(id INTEGER, name VARCHAR, geom GEOMETRY)")
    con.execute(
        "INSERT INTO summit VALUES (?, ?, ST_Point(?, ?))",
        [1, SUMMIT_NAME, SUMMIT_LON, SUMMIT_LAT],
    )

    # AOI box as a polygon (the requested DEM tile extent)
    b = AOI
    poly = (
        f"POLYGON(({b['west']} {b['south']},{b['east']} {b['south']},"
        f"{b['east']} {b['north']},{b['west']} {b['north']},{b['west']} {b['south']}))"
    )
    con.execute("CREATE OR REPLACE TABLE aoi(id INTEGER, name VARCHAR, geom GEOMETRY)")
    con.execute("INSERT INTO aoi VALUES (1, 'AOI box', ST_GeomFromText(?))", [poly])

    pois_file = DATA_DIR / "pois.geojson"
    con.execute("DROP TABLE IF EXISTS pois_raw")
    con.execute("DROP TABLE IF EXISTS pois")
    if pois_file.exists():
        # ST_Read flattens GeoJSON properties to columns; we don't know the
        # exact set in advance, so inspect and rename dynamically.
        con.execute(
            f"""CREATE TABLE pois_raw AS
                SELECT * FROM ST_Read('{pois_file.as_posix()}')"""
        )
        cols = [r[0] for r in con.execute("DESCRIBE pois_raw").fetchall()]
        print("pois_raw columns:", cols)
        if not cols:
            raise RuntimeError("ST_Read returned no columns for pois.geojson")

        src_map = {
            "geom": next((c for c in ("geom", "geometry", "wkb_geometry") if c in cols), None),
            "name": next((c for c in ("name", "title") if c in cols), None),
            "address": "address" if "address" in cols else None,
            "rating": "rating" if "rating" in cols else None,
            "ptype": ("type" if "type" in cols else "types" if "types" in cols else None),
            "place_id": "place_id" if "place_id" in cols else None,
        }
        exprs = []
        for dst, src in src_map.items():
            if src is None:
                continue
            exprs.append(f'"{src}" AS {dst}')
        if not src_map["geom"]:
            raise RuntimeError("no geometry column found in pois_raw")
        exprs.append("row_number() OVER () AS id")
        sel = ", ".join(exprs)
        con.execute(f"CREATE TABLE pois AS SELECT {sel} FROM pois_raw")
        print("pois rows:", con.execute("SELECT count(*) FROM pois").fetchone()[0])


def analyze(con: duckdb.DuckDBPyConnection) -> list[str]:
    lines: list[str] = []

    def out(s: str = "") -> None:
        print(s)
        lines.append(s)

    out("=" * 64)
    out(f"GIS analysis - {SUMMIT_NAME} study area")
    out("=" * 64)

    out("\n[DuckDB] tables:")
    for (t,) in con.execute(
        "SELECT table_name FROM information_schema.tables ORDER BY 1"
    ).fetchall():
        out(f"  - {t}")

    def has_table(name: str) -> bool:
        return con.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = ?",
            [name],
        ).fetchone()[0] > 0

    n_pois = con.execute("SELECT count(*) FROM pois").fetchone()[0] if has_table("pois") else 0
    out(f"\n[DuckDB] POIs ingested: {n_pois}")

    if n_pois:
        out("\n[DuckDB] POIs by source category:")
        rows = con.execute(
            "SELECT COALESCE(ptype,'(none)'), count(*) FROM pois GROUP BY 1 ORDER BY 2 DESC"
        ).fetchall()
        for t, c in rows:
            out(f"  {t}: {c}")

        out("\n[DuckDB] nearest POIs to summit (haversine km):")
        # haversine in SQL
        con.execute(
            """CREATE OR REPLACE TEMP TABLE poi_dist AS
               SELECT p.id, p.name,
                 6371.0088 * 2 * asin(sqrt(
                     power(sin(radians(st_y(p.geom)-st_y(s.geom))/2), 2)
                   + cos(radians(st_y(s.geom)))
                   * cos(radians(st_y(p.geom)))
                   * power(sin(radians(st_x(p.geom)-st_x(s.geom))/2), 2)
                  )) AS km
               FROM pois p, summit s
               ORDER BY km"""
        )
        for name, km in con.execute(
            "SELECT name, round(km, 2) FROM poi_dist LIMIT 8"
        ).fetchall():
            out(f"  {km:>7} km  {name}")

        out("\n[DuckDB] POIs inside the DEM tile AOI:")
        inside = con.execute(
            """SELECT count(*) FROM pois p, aoi a
               WHERE ST_Within(p.geom, a.geom)"""
        ).fetchone()[0]
        out(f"  {inside} of {n_pois} POIs lie inside the AOI box")

    out("\n[DuckDB] summit point:")
    lon, lat = con.execute(
        "SELECT ST_X(geom), ST_Y(geom) FROM summit"
    ).fetchone()
    out(f"  Mount Mitchell at ({lat:.5f}, {lon:.5f})")

    # DEM facts come from the tif; DuckDB spatial also has raster readers in
    # recent versions - try, but do not fail the report if unsupported.
    try:
        (ver,) = con.execute("SELECT version()").fetchone()
        out(f"\n[DuckDB] engine version: {ver}")
    except Exception:
        pass

    return lines


def export(con: duckdb.DuckDBPyConnection) -> None:
    WEB_DIR.mkdir(exist_ok=True)

    has_pois = con.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = 'pois'"
    ).fetchone()[0] > 0
    if has_pois:
        n_pois = con.execute("SELECT count(*) FROM pois").fetchone()[0]
    else:
        n_pois = 0
    if n_pois:
        # POIs for the map: name + rating, clean geometry
        try:
            con.execute(
                f"""COPY (
                    SELECT geom, name, address, rating, ptype
                    FROM pois
                    WHERE geom IS NOT NULL AND name IS NOT NULL
                ) TO '{WEB_DIR.as_posix()}/pois.geojson'
                WITH (FORMAT GDAL, DRIVER 'GeoJSON')"""
            )
            print("wrote", WEB_DIR / "pois.geojson")
        except duckdb.Error as e:
            print("pois export skipped:", e)

    # DEM footprint from the actual TIFF bounds
    try:
        import rasterio
        with rasterio.open(DEM_TIF) as ds:
            b = ds.bounds
        fc = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "properties": {"name": "DEM tile (SRTMGL1)"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[b.left, b.bottom], [b.right, b.bottom],
                                     [b.right, b.top], [b.left, b.top],
                                     [b.left, b.bottom]]],
                },
            }],
        }
        (WEB_DIR / "dem_bounds.geojson").write_text(json.dumps(fc))
        print("wrote", WEB_DIR / "dem_bounds.geojson")
    except Exception as e:
        print("dem bounds export skipped:", e)


if __name__ == "__main__":
    con = connect()
    ingest(con)
    report = analyze(con)
    export(con)
    (DATA_DIR / "query_report.txt").write_text("\n".join(report) + "\n")
    con.close()
    print("\nreport ->", DATA_DIR / "query_report.txt")
