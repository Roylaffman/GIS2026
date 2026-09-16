"""build_topic.py — turn a topic JSON into a self-contained, Quarto-embeddable
webmap (with Source Quality Legend + References).

A "topic" is one JSON file describing layers + provenance (see
docs/TOPIC_WEBMAP_PLAN.md §2). This script:
  1. validates the schema
  2. copies each layer's data file into web/topics/<slug>/
  3. for raster layers with a `dem` source, colorizes it into XYZ tiles
     (reusing make_bathymetry-style logic) + writes a colormap
  4. for `terrain`, generates terrain-RGB tiles via make_terrain
  5. prints the <iframe> snippet to paste into a Quarto doc

The actual HTML is web/topic.html (served for every topic via ?topic=<slug>);
no per-topic HTML duplication needed.

Usage:
  .venv\\Scripts\\python.exe build_topic.py topics/aegean-coast.json
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from gis_common import PROJECT_ROOT, WEB_DIR, fix_proj

TOPICS_SRC = PROJECT_ROOT / "topics"
TOPICS_OUT = WEB_DIR / "topics"

VALID_LAYER_TYPES = {"fill", "line", "circle", "raster"}


def validate(topic: dict) -> None:
    for k in ("title", "center", "layers"):
        if k not in topic:
            sys.exit(f"topic missing required key: {k!r}")
    if not isinstance(topic["center"], (list, tuple)) or len(topic["center"]) != 2:
        sys.exit("topic.center must be [lon, lat]")
    for l in topic["layers"]:
        if l.get("type") not in VALID_LAYER_TYPES:
            sys.exit(f"layer {l.get('id')}: bad type {l.get('type')!r} (want {sorted(VALID_LAYER_TYPES)})")
        if l.get("type") == "raster":
            if not l.get("tiles") and not l.get("dem"):
                sys.exit(f"raster layer {l.get('id')} needs 'tiles' or 'dem'")
        else:
            if not l.get("file"):
                sys.exit(f"layer {l.get('id')} ({l['type']}) needs a 'file'")
    tags = {q["tag"] for q in topic.get("quality_legend", [])}
    for l in topic["layers"]:
        if l.get("quality") and l["quality"] not in tags:
            print(f"  warn: layer {l['id']} quality tag {l['quality']!r} not in quality_legend")


def resolve_path(ref: str, topic_dir: Path) -> Path:
    p = Path(ref)
    if p.is_absolute():
        return p
    # relative to the topic file's dir first, then project root
    cand = topic_dir / p
    if cand.exists():
        return cand
    cand2 = PROJECT_ROOT / p
    if cand2.exists():
        return cand2
    sys.exit(f"layer file not found: {ref!r} (looked in {topic_dir} and {PROJECT_ROOT})")


def build_topic(topic_path: Path) -> str:
    topic_path = Path(topic_path)
    topic = json.loads(topic_path.read_text(encoding="utf-8"))
    validate(topic)
    slug = topic_path.stem
    out = TOPICS_OUT / slug
    out.mkdir(parents=True, exist_ok=True)
    topic_dir = topic_path.parent

    # POIs across the whole topic area (grid of SerpAPI queries + H3)
    pois_spec = topic.get("pois")
    if pois_spec:
        from fetch_grid_pois import fetch_grid_pois
        grid = pois_spec.get("grid") or (topic.get("terrain") or {}).get("grid") or {"n": 4, "cell": 0.08}
        fetch_grid_pois(topic["center"][1], topic["center"][0],
                        grid.get("n", 4), grid.get("cell", 0.08),
                        pois_spec.get("query", "points of interest"),
                        out, pois_spec.get("step", 1), pois_spec.get("zoom", 13))

    for l in topic["layers"]:
        if l["type"] == "raster" and l.get("dem"):
            dem = resolve_path(l["dem"], topic_dir)
            from make_bathymetry import make_bathymetry
            meta = make_bathymetry(dem, out, min_zoom=l.get("minzoom", 8), max_zoom=l.get("maxzoom", 12))
            l["tiles"] = meta["tiles"]
            l["colormap"] = meta["colormap"]
            l["depth_min"] = meta["depth_min"]
            l["depth_max"] = meta["depth_max"]
            print(f"  colorized raster {l['id']}: {meta['depth_min']}..{meta['depth_max']} m, tiles={meta['tiles']}")
        elif l["type"] != "raster":
            # if the file already lives in the output dir (e.g. written by a
            # fetcher like fetch_grid_pois), use it as-is
            if (out / l["file"]).exists():
                print(f"  layer {l['id']}: {l['file']} (already in output)")
                continue
            src = resolve_path(l["file"], topic_dir)
            # use layer id as the filename to avoid collisions (e.g. two extents)
            dst = out / (l["id"] + Path(src).suffix)
            if src.resolve() != dst.resolve():
                shutil.copy2(src, dst)
            l["file"] = dst.name
            print(f"  layer {l['id']}: {dst.name}")

    # terrain
    terr = topic.get("terrain")
    if terr:
        dem = None
        if terr.get("grid"):
            # fetch surrounding DEMs as an n x n grid around the topic center
            from make_grid_dem import fetch_grid_dem
            g = terr["grid"]
            dem = fetch_grid_dem(topic["center"][1], topic["center"][0],
                                 g.get("n", 4), g.get("cell", 0.08),
                                 terr.get("demtype", "SRTMGL1"), out,
                                 mode=g.get("mode", "single"))
            # register the grid outline as a layer if not already present
            if not any(l["id"] == "dem-grid" for l in topic["layers"]):
                topic["layers"].append({
                    "id": "dem-grid", "label": "DEM grid", "type": "line",
                    "file": "grid.geojson", "color": "#ffffff", "width": 0.8,
                    "dash": [2, 2], "opacity": 0.5, "quality": "Computed",
                    "source_name": "SRTM / OpenTopography", "visible": True,
                })
        elif terr.get("dem"):
            dem = resolve_path(terr["dem"], topic_dir)
        if dem:
            from make_terrain import make_terrain
            make_terrain(dem, out, min_zoom=8, max_zoom=13)
            terr["tiles"] = "tiles/{z}/{x}/{y}.png"
            print(f"  terrain tiles -> {out / 'tiles'}")

    (out / "topic.json").write_text(json.dumps(topic, indent=2))

    # renderer: Mapbox GL JS is the primary engine; MapLibre is the tokenless fallback
    engine = topic.get("engine", "mapbox")
    page = "/topic-mapbox.html" if engine == "mapbox" else "/topic.html"
    url = f"{page}?topic={slug}"
    print(f"\nDONE -> {out}  [{engine}]")
    print(f"  view:  http://127.0.0.1:8090{url}")
    print(f"  embed: <iframe src=\"{url}\" width=\"100%\" height=\"620\" style=\"border:0\" loading=\"lazy\"></iframe>")
    return slug


if __name__ == "__main__":
    fix_proj()
    p = argparse.ArgumentParser()
    p.add_argument("topic", help="path to topics/<slug>.json")
    args = p.parse_args()
    build_topic(Path(args.topic))
