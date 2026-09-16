# Topic → Webmap System (Quarto-embeddable) — Plan

> Generalize DSHtest from "fetch DEMs + POIs for a place" into **"pick a topic,
> assemble layers, emit an embeddable MapLibre webmap with a Source Quality
> Legend + references, ready for a Quarto document."**

## 1. What we learned from the reference pages

| Page | Type | Tech | Notable |
|------|------|------|---------|
| `lithium_analysis.html` | Quarto **article** | Quarto + inline data + charts | **Source Quality Legend** table (tags: `Peer-rev.`, `Gov.`, `Gray lit.`, `Industry`) + numbered **References** |
| `critical-minerals.html` | Quarto **article** | Quarto + D3 + images | Same legend/references pattern; data-heavy |
| `chimney-rock.html` | **interactive map** | MapLibre GL 4.7 (unpkg), dark CARTO basemap | Many GeoJSON sources (hillshade, landuse, water, trails, cliffs, climbing, peaks, waterfalls, viewpoints, places) → fill/line/circle/label layers + attribution control |

**So the pattern to replicate:**
1. A **map** (MapLibre, self-contained HTML, no build step) with named, styled,
   toggleable layers.
2. A **Source Quality Legend** — a table mapping each layer/source to a
   quality tag (Peer-rev. / Gov. / Gray lit. / Industry / Computed).
3. A **References** list (numbered citations).
4. **Attribution** (data providers + © notices) — both on-map and in a footer.
5. **Embeddable** — a single self-contained file that drops into a Quarto doc
   via an `<iframe>` or a raw-HTML block.

## 2. The data model (what defines a "topic")

A topic is one JSON file that describes every layer + its provenance:

```jsonc
// topics/<slug>.json
{
  "title": "Chimney Rock: geology & climbing",
  "subtitle": "Rumbling Bald and the Hickory Nut Gorge",
  "center": [-82.258, 35.43],
  "zoom": 13,
  "basemap": "dark",                 // dark | light | satellite | osm
  "terrain": { "dem": "dem_cog.tif" },   // optional 3D terrain
  "quality_legend": [
    { "tag": "Peer-rev.", "color": "#1b9e77", "meaning": "Peer-reviewed journal" },
    { "tag": "Gov.", "color": "#377eb8", "meaning": "Government agency data" },
    { "tag": "Gray lit.", "color": "#e6ab02", "meaning": "Reports / journalism" },
    { "tag": "Computed", "color": "#7570b3", "meaning": "Derived in this project" }
  ],
  "layers": [
    {
      "id": "trails",
      "label": "Trails",
      "type": "line",                 // fill | line | circle | raster | symbol
      "file": "trails.geojson",       // relative to topic dir (or data/ path)
      "color": "#f4a261",
      "width": 1.6,
      "quality": "Gov.",              // -> appears in legend with this tag
      "source_name": "OpenStreetMap",
      "source_url": "https://www.openstreetmap.org",
      "visible": true
    },
    {
      "id": "hillshade",
      "label": "Hillshade",
      "type": "raster",
      "tiles": "tiles/{z}/{x}/{y}.png",   // or a single .png overlay
      "opacity": 0.6,
      "quality": "Computed",
      "source_name": "USGS 3DEP",
      "source_url": "https://apps.nationalmap.gov/downloader/"
    }
  ],
  "references": [
    { "id": 1, "text": "USGS. 2024. 3DEP Elevation. https://..." },
    { "id": 2, "text": "NCGS. 2011. Geologic map of the Hickory Nut Gorge. ..." }
  ]
}
```

## 3. The pipeline (topic → artifacts)

`build_topic.py <topics/foo.json> [--out web/topics/foo]`:

1. **Ingest layers** — copy/normalize each layer's GeoJSON/GeoTIFF into the
   topic output dir. (Sources can be local files, or we add fetchers later.)
2. **Raster pre-processing** (when a layer is a GeoTIFF):
   - DEM → `make_terrain.py` (terrain-RGB tiles) if `terrain`
   - value raster → `make_bathymetry.py`-style **colorized tiles + colormap**
     (already built for bathymetry; generalize to any value ramp)
3. **Emit `index.html`** — a **self-contained MapLibre page** (vendored libs
   already in `web/lib/`), reading the topic JSON and rendering:
   - basemap (dark/light/OSM/satellite via raster source)
   - 3D terrain + hillshade (optional)
   - every layer as fill/line/circle/raster with popups + toggles
   - **Source Quality Legend** (from `quality_legend`, each layer tagged)
   - **References** section
   - **attribution control** (MapLibre built-in) + a footer credit list
4. **Emit an embed snippet** — a `<iframe src="topics/foo/index.html">` block
   + a `<script>`-less fallback, so it drops straight into Quarto.

## 4. Embeddability in Quarto

- Self-contained single-file HTML → works in Quarto via either:
  - `{{< embed ... >}}` shortcode, or
  - a raw HTML block with `<iframe src="/topics/foo/index.html" width="100%" height="600" frameborder="0">`.
- Serve `web/topics/` from `serve_map.py` (already serves `web/`).
- No token, no CDN dependency (vendored MapLibre/Chart already local).

## 5. Implementation phases

### Phase A — Topic schema + generic topic builder (this is the core)
- [ ] `topics/` dir + one example topic JSON (`chimney-rock`-style, but using
      data we can actually fetch — e.g. the Mount Mitchell / Greek runs as a first topic)
- [ ] `build_topic.py`:
  - validate schema (required fields, layer types, quality tags)
  - copy layer files, run terrain/colorize when needed
  - render `index.html` from a template
- [ ] `web/topic.html` template (MapLibre) with:
  - basemap switch
  - terrain + raster + vector layers + toggles
  - popups (properties-driven)
  - **Source Quality Legend** table (auto from `quality_legend` + per-layer tags)
  - **References** list
  - attribution control + footer
- [ ] `make_topic.py` (or fold into build_topic) → produce `<iframe>` snippet

### Phase B — Raster generalization (reuse what we built)
- [ ] Split `make_bathymetry.py` into a generic `make_colormap_tiles.py`
      (value raster + colormap → colorized XYZ tiles + `colormap.json`);
      bathymetry becomes one preset colormap.
- [ ] `make_terrain.py` already generic — reuse as-is.

### Phase C — Layer fetchers (turn "topic" into "grab data")
- [ ] A small registry of `fetchers` keyed by source name, so a topic can say
      `"source": "emodnet"` / `"source": "opentopo"` / `"source": "serpapi"`
      and `build_topic.py` downloads instead of copying.
- [ ] Start with the two we've proven: OpenTopo (DEM) + EMODnet (bathymetry).

### Phase D — Quarto integration proof
- [ ] A minimal Quarto `.qmd` that embeds the topic map + legend + references,
      rendered to HTML, to prove the loop end-to-end.

### Phase E — Polish
- [ ] `topic.html` dark/light theming, mobile-responsive panel
- [ ] popup templates (title/description/image fields)
- [ ] a topic gallery/hub (`topics/index.json` + a listing page)

## 6. Definition of done (for the first slice)

A working demo where one command:
```
.venv\Scripts\python.exe build_topic.py topics/greece-coast.json
```
…produces `web/topics/greece-coast/index.html` showing the Aegean bathymetry +
island DEMs as toggleable layers with a **Source Quality Legend** and
**References**, viewable at `/topics/greece-coast/`, embeddable in Quarto via
an `<iframe>`, all open-source (MapLibre, no Mapbox token, no CDN).

## 7. Risks / notes

- **MapLibre version skew** — reference pages use 4.7.1 via unpkg; we vendor
  (5.24). Styles differ slightly; verify layer rendering manually (sandbox
  can't screenshot).
- **Symbol layers** (text labels) need a glyphs URL. For offline/self-contained
  we avoid `symbol` initially (use `circle` + `line` + `fill` + `raster`).
- **Quarto embedding** — iframes work but can't share state; that's fine for
  attribution-style maps. A future option is injecting the map's JS directly.
