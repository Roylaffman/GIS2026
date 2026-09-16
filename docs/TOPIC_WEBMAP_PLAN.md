# Topic → Webmap System (Quarto-embeddable) — Plan

> Generalize DSHtest from "fetch DEMs + POIs for a place" into **"pick a topic,
> assemble layers, emit an embeddable Mapbox GL webmap with a Source Quality
> Legend + references, ready for a Quarto document."**

## 0. Renderer decision (primary)

- **Primary map engine: Mapbox GL JS** — chosen because it renders **3D terrain**
  natively (`raster-dem` + `setTerrain`) and ingests **GeoJSON** that can be
  coded inline (addSource/addLayer) with full style control. Needs the
  `MAPBOX_TOKEN` (already in `.env`, served via `/config.js`).
- **MapLibre GL, Deck.gl, Kepler.gl, Leaflet, Cesium** remain in the toolkit and
  are used *when the task calls for them*:
  - MapLibre GL — tokenless fallback / where Mapbox terms don't apply
  - Deck.gl — big-data overlays (hexagons, scatter, trips) on top of a basemap
  - Kepler.gl — quick drag-drop data exploration
  - Leaflet — lightweight static/vector maps
  - Cesium — full globe / time-dynamic scenes
- The topic schema stays **engine-agnostic** (layers + style + quality), but the
  emitted `index.html` targets **Mapbox GL JS** first, with a MapLibre template
  kept as a drop-in alternative.

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
3. **Emit `index.html`** — a **self-contained Mapbox GL JS page** (vendored or
   CDN; token via `/config.js`), reading the topic JSON and rendering:
   - basemap (dark/light/OSM/satellite via raster source)
   - **3D terrain + hillshade** (`raster-dem` + `setTerrain`, exaggeration)
   - every layer as fill/line/circle/raster/symbol, with **GeoJSON coded in**
     (addSource/addLayer) and popups + toggles
   - **Source Quality Legend** (from `quality_legend`, each layer tagged)
   - **References** section
   - **attribution control** + a footer credit list
4. **Emit an embed snippet** — a `<iframe src="topics/foo/index.html">` block
   + a `<script>`-less fallback, so it drops straight into Quarto.

## 4. Embeddability in Quarto

- Self-contained single-file HTML → works in Quarto via either:
  - `{{< embed ... >}}` shortcode, or
  - a raw HTML block with `<iframe src="/topics/foo/index.html" width="100%" height="600" frameborder="0">`.
- Serve `web/topics/` from `serve_map.py` (already serves `web/`).
- Mapbox GL JS needs the token (served via `/config.js` from `.env`); MapLibre
  fallback template stays tokenless if ever needed.

## 5. Implementation phases

### Phase A — Topic schema + generic topic builder (this is the core)
- [x] `topics/` dir + example topic JSONs (`aegean-coast`, `mount-mitchell`)
- [x] `build_topic.py`: validate schema, copy layer files, colorize rasters into
      tiles, generate terrain tiles, emit topic + `<iframe>` snippet;
      routes by `"engine"` (default `mapbox`)
- [x] **`web/topic-mapbox.html` — Mapbox GL JS renderer (PRIMARY)**
  - token from `/config.js`; vendored `mapbox-gl.js`/`.css` v3.4.0 in `web/lib/`
  - Mapbox basemap styles (dark / light / satellite / outdoors / streets)
  - **3D terrain** (`raster-dem` + `setTerrain`, exaggeration) + hillshade —
    uses our own terrain-RGB tiles, or Mapbox-hosted terrain-dem
  - raster / fill / line / circle / **symbol (labels)** layers + toggles
  - popups (properties-driven), pitch/bearing, fullscreen, scale
  - **Source Quality Legend** table + **References** list + attribution footer
- [x] `web/topic.html` — MapLibre renderer kept as the **tokenless fallback**
- [x] Verified: mount-mitchell (terrain + 3 GeoJSON layers) and aegean-coast
      (bathymetry raster + extents) build and serve; terrain tiles decode
      0–2028 m.

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
.venv\Scripts\python.exe build_topic.py topics/mount-mitchell.json
```
…produces `web/topics/mount-mitchell/` with 3D terrain + coded GeoJSON layers,
a **Source Quality Legend** and **References**, viewable at
`/topic-mapbox.html?topic=mount-mitchell`, embeddable in Quarto via `<iframe>`.

**Status: met** (Mapbox GL JS primary; MapLibre fallback retained).

## 7. Risks / notes

- **Mapbox GL JS needs the token** — served at runtime via `/config.js` from
  `.env` (never baked into the HTML). If the token is missing/unset the page
  shows a clear error banner. MapLibre page remains the tokenless fallback.
- **Terrain source** — we prefer our own terrain-RGB tiles (works regardless of
  Mapbox plan/terrain entitlements); `use_mapbox: true` switches to
  `mapbox://mapbox.mapbox-terrain-dem-v1`.
- **Symbol layers** — Mapbox GL has hosted glyphs, so `symbol` (text labels)
  is supported here (it was avoided in the offline MapLibre page).
- **Quarto embedding** — iframes work but can't share state; that's fine for
  attribution-style maps. A future option is injecting the map's JS directly.
- **Manual verification needed** — the sandbox can't run a browser/WebGL, so
  map *rendering* must be eyeballed by the user; we verify data, tiles, JSON,
  and JS syntax programmatically.
