# DeepSeek Harness - Working Guide

2026-09-07 - Ryan Lafferty

A practical reference for running, configuring, and extending DSH for GIS reporting and web map workflows.

## Quick Start

### Daily Commands

| Scenario | Command |
|---|---|
| **Restart the UI** | `pnpm dsh web` |
| **After editing source** | `pnpm run build` then `pnpm dsh web` |
| **Active dev (auto-rebuild)** | `pnpm run dev:web` |
| **One-shot headless agent** | `pnpm dsh --profile headless "your prompt"` |
| **Typecheck only** | `pnpm run typecheck` |
| **Inspect plugin tree** | `pnpm dsh --profile web --dump-config` |

### When Do You Need to Rebuild?

- **No rebuild needed:** restarting the server, changing `.env` values, editing `cordis.patch.yml` overlays, switching model providers in the UI
- **Rebuild required:** any change to TypeScript source under `packages/`, `apps/`, or `vendor/`
- **Use dev mode** (`pnpm run dev:web`) when actively editing source; requires an initial `pnpm run build` first

### First Launch Checklist

1. Open `http://127.0.0.1:3080`
2. Settings > Models > enter your DeepSeek API key and save
3. Choose workspace > add your project directory
4. Start a session and send a test prompt

### Environment Variables

Set in `.env` at the repo root (gitignored):

```
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://...   # optional
```

## Core Architecture

DSH is built on an "everything-is-a-plugin" design powered by Cordis. Every capability (model adapter, tool registry, file system, shell, sandbox, session log) is a plugin. There is no privileged core to patch.

### Key Concepts

- **Plugin:** a TypeScript module exporting an `apply(ctx)` function. The framework calls it when loading and passes a context object.
- **Context (`ctx`):** a repository of services. Each plugin claims a key like `ctx.tools`, `ctx.llm`, `ctx.fs`, or `ctx.shell`.
- **Service dependency:** declared via an `inject` array. Cordis waits for all required services before loading a dependent plugin.
- **Reversible effects:** everything registered through `ctx.effect()`, `ctx.on()`, or `ctx.tools.register()` unwinds automatically when a plugin unloads.
- **Events:** extension points with dispatch modes: `emit` (fire-and-forget), `waterfall` (around-middleware), `parallel`, `serial`, `bail`.

### Configuration Layers

A running DSH instance is composed from layers applied in order:

1. Each **bundle's** `cordis.patch.yml` (in profile's bundle order)
2. The **profile's** own `cordis.patch.yml`
3. **Home-level** `$DSH_HOME/cordis.patch.yml` (applies to all profiles)
4. Any `--patch <file>` overlays passed at launch

A patch entry replaces its target row's entire config (no deep merge). Later layers win per row. Inspect the final composed tree with `pnpm dsh --profile web --dump-config`.

## Built-In Tools

These ship in the default Web profile and are available out of the box.

### File System

| Tool | What it does |
|---|---|
| `read`, `write`, `edit`, `read_image` | Full filesystem I/O with read-before-write policy |
| `glob`, `grep` | File discovery via bundled ripgrep (no host rg needed) |
| `str_replace_editor` | View/create/edit with unique literal string replacement |

### Shell and Terminal

| Tool | What it does |
|---|---|
| `bash` | One-shot `bash -c` with optional `run_in_background` |
| `pwsh` | PowerShell equivalent for Windows |
| `bash` (persistent) | PTY-backed session that survives across calls |
| `terminal_open/send/read/close/list/signal` | Full interactive PTY management (opt-in) |

### Web Access

| Tool | What it does |
|---|---|
| `web_search` | Search via Exa, Perplexity, or DeepSeek backends |
| `web_fetch` | Fetch public HTTP(S) pages anonymously |

### Agent Delegation

| Tool | What it does |
|---|---|
| `subagent` | Spawn child agent sessions (in-process, ACP, Claude Code, Codex) |
| `list_subagent_models` | Discover available delegation targets |
| `send_message`, `interrupt_agent`, `list_agents` | Control running subagents |

### Planning and Workflow

| Tool | What it does |
|---|---|
| `exit_plan_mode` | Plan-review gate: model proposes, human approves before acting |
| `todo_write` | Session-owned checklist rendered in the UI |
| `create_goal`, `get_goal`, `update_goal` | Persistent session goals |
| `workflow` | Scripted structured workflow execution |

### Other

| Tool | What it does |
|---|---|
| `ask_user_question` | Pause to ask the user a question with optional choices |
| `skill` | Load instruction sets (skills) into model context |
| `lsp` | Language server queries (go-to-definition, find-references) |
| `job_list`, `job_output`, `job_kill` | Manage background jobs |

### Opt-In Tools (not enabled by default)

| Tool | Activation |
|---|---|
| `schedule_create/delete/list` | `--patch apps/cli/config/examples/schedule/cordis.yml` |
| `session_event_read/search/trace` | `--patch` with session-query overlay |
| `cordis_define/run/stop/inspect_*` | `--patch apps/cli/config/examples/cordis/cordis.yml` |
| `run_code` (PTC mode) | Explicit config opt-in |

## Plugin Management

### Installing Plugins

Use the `dsh plugin` subcommand, which is a pnpm pass-through scoped to a profile directory:

```bash
# Install from npm
dsh plugin --profile web add dsh-my-plugin

# Install from local path
dsh plugin --profile web add ./my-plugin

# Install from GitHub
dsh plugin --profile web add github:author/my-plugin

# Remove a plugin
dsh plugin --profile web remove dsh-my-plugin
```

### What Makes a Package a DSH Plugin?

A package becomes a true DSH bundle when its `package.json` includes:

```json
{
  "dsh": { "bundle": { "patch": "./cordis.patch.yml" } }
}
```

Without this declaration, pnpm installs the dependency but DSH prints a warning and activates no layer.

### Configuration Overlays

For quick opt-in features without installing a full plugin, use `--patch` overlays at launch:

```bash
pnpm dsh web --patch apps/cli/config/examples/schedule/cordis.yml
```

The repo ships several example overlays under `apps/cli/config/examples/`:

- `cordis/` for dynamic runtime Cordis tools
- `schedule/` for session-local scheduled reminders
- `mcp-memory/` for memory MCP servers (Memorix, Engram, mcp-reference-memory)
- `github-review/` for GitHub webhook PR review

### Distribution

There is no central plugin marketplace. Plugins distribute via:

- **npm:** publish and `dsh plugin add <package-name>`
- **Tarball:** `dsh plugin add ./plugin-0.1.0.tgz`
- **GitHub:** `dsh plugin add github:you/plugin`

Discover community plugins by searching the `dsh-plugin` GitHub topic.

## Model Providers

### Built-In Providers

Selectable via Settings > Models > Add provider:

| Provider | Protocol |
|---|---|
| DeepSeek | Native adapter |
| Anthropic (Claude) | Anthropic Messages API |
| OpenAI | OpenAI Chat Completions / Responses API |
| Moonshot AI (Kimi) | OpenAI-compatible |
| ZAI (GLM) | OpenAI-compatible |

### Custom Providers

Any OpenAI-compatible or Anthropic-compatible endpoint can be added as a custom provider. In the UI, supply:

- **Provider ID** (your label)
- **Base URL** of the endpoint
- **API protocol:** `openai-completions`, `openai-responses`, or `anthropic-messages`

A gateway that speaks two protocols needs two separate provider entries. The form supports "Fetch available models" for auto-discovery, or manual model ID entry.

### Per-Model Configuration

Advanced per-model overrides live in `$DSH_HOME/settings.yaml` under `llm-pi-ai.providers`:

- Image input support
- Reasoning effort levels
- Compatibility flags: `supportsDeveloperRole`, `maxTokensField`, `thinkingFormat`

This means you can connect local models (Ollama, LM Studio, vLLM) or cloud endpoints (Azure OpenAI, Groq, Together) as long as they expose an OpenAI-compatible API.

## MCP Integration

DSH can connect external MCP (Model Context Protocol) servers, exposing their tools as native `mcp__<serverName>__<toolName>` calls. Only the Tools capability is bridged; Resources and Prompts are not.

### Adding an MCP Server

Create or edit a `cordis.patch.yml` overlay with an entry like:

```yaml
- id: mcp-github
  name: '@deepseek-ai/dsh-mcp-client'
  config:
    serverName: github
    transport: stdio
    command: npx
    args: ['-y', '@modelcontextprotocol/server-github']
    env:
      GITHUB_TOKEN: ghp_your_token_here
```

Then launch with `--patch your-overlay.yml`.

### Supported Transports

- **stdio:** launches a local program as a child process
- **streamable-http:** connects to a running service by URL with optional headers

### Security

Child environment is scrubbed of credential-pattern names (`KEY`, `PASSWORD`, `SECRET`, `TOKEN`) and all `DSH_*` vars before launching stdio servers.

### Reliability

On connection loss, the plugin reconnects with exponential backoff (500ms to 30s). After 10 consecutive failures, tools are unregistered and reconnection stops until config reload or restart.

### Shipped MCP Examples

All opt-in via `--patch` overlays under `apps/cli/config/examples/mcp-memory/`:

- **Memorix** for persistent memory
- **mcp-reference-memory** (`@modelcontextprotocol/server-memory`)
- **Engram** for memory management

### Useful MCP Servers for GIS/Reporting Workflows

| Server | What it adds |
|---|---|
| `@modelcontextprotocol/server-filesystem` | Broad file access outside workspace |
| `@modelcontextprotocol/server-github` | GitHub issues, PRs, repo management |
| `@modelcontextprotocol/server-memory` | Persistent cross-session memory |
| Custom Python MCP server | Wrap geopandas, folium, or quarto render as callable tools |

## Permissions and Sandboxing

DSH has three interlocking safety layers.

### Sandbox Modes

Control what the agent's subprocesses can write:

| Mode | Behavior |
|---|---|
| `read-only` | Deny all writes except required sinks like `/dev/null` |
| `workspace-write` | Allow writes under the workspace root and a backend temp area |
| `danger-full-access` | Bypass confinement entirely |

Platform backends: Linux uses bwrap/Landlock, macOS uses Seatbelt, Windows uses restricted token + ACL.

### Approval Policy

Per-session policy for tool calls that need confirmation:

- **`ask`** (default): the Web UI prompts you before risky operations
- **`never`**: rejects every approval request automatically (for headless/CI use)

Missing or failing answerers are fail-closed as `unavailable`.

### Permission Presets

Named bundles that set both knobs at once:

| Preset | Sandbox | Approval |
|---|---|---|
| `workspace-write` | workspace-write | ask |
| `danger-full-access` | danger-full-access | never |

Presets can be extended in `$DSH_HOME/settings.yaml`. For most work, `workspace-write` with `ask` approval is the right default. Switch to `danger-full-access` only for trusted automation where the agent needs to write outside the workspace.

## Recommended Setup for Quarto Reports and Web Maps

DSH has no built-in geospatial or Quarto plugins, but its tool surface is well suited for driving your existing Python/Quarto toolchain. Here is the recommended configuration.

### What Works Out of the Box

The default Web profile already gives the agent everything it needs for your workflow:

| Capability | How it helps |
|---|---|
| `bash` tool | Run `quarto render`, `python`, `ogr2ogr`, any CLI tool on the host |
| `write`/`edit` tools | Author and modify `.qmd` files, Python scripts, GeoJSON, HTML |
| `glob`/`grep` tools | Search datasets, find shapefiles, locate config files |
| `web_fetch` | Pull remote GeoJSON, tile metadata, ArcGIS REST endpoints |
| `web_search` | Research data sources, find open datasets, check API docs |
| `subagent` | Delegate subtasks (data cleaning, map generation, report writing) |

### Recommended Workflow: Quarto Reports

1. **Set your workspace** to the project directory containing your `.qmd` files
2. Ask the agent to scaffold a Quarto document: it writes `.qmd` via the `write` tool
3. For data analysis, the agent writes Python scripts and runs them via `bash`
4. The agent renders with `bash` running `quarto render report.qmd`
5. For iterative refinement, the agent uses `edit` to modify sections and re-renders

### Recommended Workflow: Folium/Leaflet Web Maps

1. The agent writes a Python script using folium/geopandas via the `write` tool
2. Runs it via `bash` to generate the HTML map
3. Uses `read` to inspect the output, `edit` to adjust styling or layers
4. Can fetch remote data (ArcGIS REST, GeoJSON URLs) via `web_fetch` or `bash` + `curl`

### Recommended MCP Servers

These would extend DSH for your specific workflows:

| Server | Why |
|---|---|
| `@modelcontextprotocol/server-filesystem` | Let the agent access data outside the workspace (shared GIS data directories, network drives) |
| `@modelcontextprotocol/server-memory` | Persist project context across sessions (data source URLs, coordinate systems, style templates) |
| `@modelcontextprotocol/server-github` | Manage your report repos, create issues for data updates, track map versions |

### Recommended --patch Overlays

| Overlay | Why |
|---|---|
| `schedule/cordis.yml` | Schedule recurring data refreshes or report renders |
| `mcp-memory/memorix.yml` | Cross-session memory for your GIS project context |

### Launch Command for Your Stack

Combine overlays in one launch:

```bash
pnpm dsh web \
  --patch apps/cli/config/examples/schedule/cordis.yml \
  --patch apps/cli/config/examples/mcp-memory/memorix.yml
```

### Example Prompts to Try

- "Create a Folium map of climbing areas in North Carolina using this GeoJSON file"
- "Build a Quarto presentation summarizing parcel data in the /data directory"
- "Fetch the ArcGIS REST endpoint at [url] and convert the response to a GeoDataFrame"
- "Write a Python script that joins these two CSVs on parcel ID and exports to GeoJSON"
- "Render this QMD to HTML and fix any warnings in the output"

## Custom Plugin Development

If the bash-tool approach is not enough, you can build native DSH plugins that wrap your geospatial toolchain as first-class model-facing tools.

### Plugin Structure

A minimal plugin is a TypeScript module exporting `apply(ctx)`:

```typescript
import { Context } from '@deepseek-ai/dsh-core'

export function apply(ctx: Context) {
	ctx.tools.register(defineTool({
		name: 'render_quarto',
		description: 'Render a Quarto document to the specified format',
		parameters: {
			type: 'object',
			properties: {
				input: { type: 'string', description: 'Path to .qmd file' },
				format: { type: 'string', enum: ['html', 'pdf', 'revealjs'] }
			},
			required: ['input']
		},
		async execute({ input, format }) {
			const result = await ctx.shell.run(
				`quarto render ${input} --to ${format || 'html'}`
			)
			return { output: result.stdout }
		}
	}))
}
```

### Packaging as a Bundle

1. Create a directory with `package.json` containing `"dsh": { "bundle": { "patch": "./cordis.patch.yml" } }`
2. Write `cordis.patch.yml` that inserts your plugin into the tree
3. Install with `dsh plugin --profile web add ./your-plugin`

### Alternative: MCP Server Route

For Python-heavy workflows, building a custom MCP server in Python may be simpler than a TypeScript DSH plugin:

```python
# A minimal MCP server wrapping geopandas operations
from mcp.server import Server

app = Server("gis-tools")

@app.tool()
async def buffer_geometry(geojson_path: str, distance: float) -> str:
	import geopandas as gpd
	gdf = gpd.read_file(geojson_path)
	buffered = gdf.buffer(distance)
	output = geojson_path.replace('.geojson', '_buffered.geojson')
	buffered.to_file(output, driver='GeoJSON')
	return f'Buffered geometry written to {output}'
```

Then connect it to DSH via a `cordis.patch.yml` entry pointing to your MCP server.

### Development Docs

The repo ships full plugin development guides:

- `docs/user/develop/basic/index.md` for plugin structure
- `docs/user/develop/basic/tool.md` for the `defineTool()` DSL
- `docs/user/develop/basic/config.md` for configuration schemas
- `docs/user/develop/basic/publish.md` for packaging and distribution
- `docs/user/develop/practice/index.md` for the three-role capability pattern
- `docs/cookbook/` for step-by-step recipes
