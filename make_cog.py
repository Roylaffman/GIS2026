"""Convert the DEM GeoTIFF to a Cloud-Optimized GeoTIFF (COG).

A COG stores overviews + tiling + a header such that web clients can read
specific spatial windows / zoom levels over HTTP range requests without
downloading the whole file — the format Deck.gl / MapLibre / Cesium terrain
pipelines expect for streaming rasters.

Output: data/dem_cog.tif
"""
from __future__ import annotations

from gis_common import DATA_DIR

SRC = DATA_DIR / "dem_mount_mitchell.tif"
DST = DATA_DIR / "dem_cog.tif"


def to_cog() -> None:
    import rasterio
    from rasterio.enums import Resampling

    with rasterio.open(SRC) as src:
        profile = src.profile.copy()
        profile.update(
            driver="COG",          # GDAL Cloud-Optimized GeoTIFF driver
            tiled=True,
            compress="deflate",
            blockxsize=256,
            blockysize=256,
            # overviews for zoom-level pyramid; small file so a few levels
            RESAMPLING="average",
        )
        with rasterio.open(DST, "w", **profile) as dst:
            dst.write(src.read(1), 1)
            # COG driver builds overviews automatically on write; add explicit
            # overviews too for robustness across GDAL versions.
            try:
                dst.build_overviews([2, 4, 8], Resampling.average)
            except Exception as e:
                print("(overviews note)", e)

    # verify: report internal structure
    with rasterio.open(DST) as ds:
        print("driver:", ds.driver)
        print("compression:", ds.compression)
        print("size:", ds.width, "x", ds.height)
        print("is tiled:", ds.profile.get("tiled"), "block:", ds.profile.get("blockxsize"))
        ov = ds.overviews(1)
        print("overviews:", ov)
        print("crs:", ds.crs)
    print("wrote", DST, f"({DST.stat().st_size} bytes)")


if __name__ == "__main__":
    to_cog()
