# Documentation Index

All project documentation lives here. `README.md` stays at the repo root as the
quick-start entry point.

| Doc | What it covers |
|-----|----------------|
| [WORKPLAN.md](WORKPLAN.md) | **Start here.** Project state, done/todo checklists, environment inventory, harness snags, file map, command cheat sheet. |
| [MODERN_GIS_STACK.md](MODERN_GIS_STACK.md) | Architecture & roadmap: GDAL/GeoPandas/DuckDB/H3 + Deck.gl / Kepler.gl / Cesium, phased plan. |
| [TOPIC_WEBMAP_PLAN.md](TOPIC_WEBMAP_PLAN.md) | The "topic → webmap" system: schema, pipeline, **Mapbox GL JS as primary renderer**, Quarto embedding. |
| [DSH_WorkingGuide.md](DSH_WorkingGuide.md) | DeepSeek Harness (DSH) itself — commands, rebuild rules, workspace setup. |

## Quick orientation

- **Run the maps:** `.\\.venv\\Scripts\\python.exe serve_map.py 8090` → http://127.0.0.1:8090
- **Make a quick map:** `python quickmap.py "Place, State" --pois serpapi --query "..."`
- **Build a topic map:** `python build_topic.py topics/<slug>.json`
- **Resume next session:** read `WORKPLAN.md` §0 + §4/§5.

## Conventions

- Project docs live in `docs/`; only `README.md` stays at root.
- Cross-references use `docs/<name>.md` paths.
- Keep `WORKPLAN.md` current — it's the durable memory across sessions.
