"""Generate a small synthetic bathymetry GeoTIFF for testing analyze_dem.py."""
import numpy as np
import rasterio
from rasterio.transform import from_origin

from gis_common import fix_proj

fix_proj()

# a bowl-shaped lake bed, depths 0..-120 m, 200x200 cells @ ~10m
n = 200
x = np.linspace(-1, 1, n)
y = np.linspace(-1, 1, n)
xx, yy = np.meshgrid(x, y)
r = np.sqrt(xx ** 2 + yy ** 2)
depth = -120.0 * np.clip(1 - r, 0, 1)  # -120 at center, 0 at rim
depth = np.where(r > 1.0, 0.0, depth)

rng = np.random.default_rng(42)
depth = depth + rng.normal(0, 1.5, depth.shape)
depth = np.clip(depth, -125, 0)

transform = from_origin(-1000, 1000, 10, 10)  # 10m cells, origin NW
with rasterio.open(
    "data/sample_bathymetry.tif", "w", driver="GTiff",
    height=n, width=n, count=1, dtype="float32",
    crs="EPSG:3857", transform=transform, nodata=-9999, compress="deflate",
) as dst:
    dst.write(depth.astype("float32"), 1)
print("wrote data/sample_bathymetry.tif", depth.min(), "to", depth.max(), "m")
