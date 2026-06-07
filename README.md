# Accordance MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io) server that exposes
**Accordance Bible Software**'s Scripture text to Claude and any other MCP
client — believed to be the first MCP server for Accordance.

## What it does

Wraps Accordance's `AccdTxRf` Apple event (the app's one reliable data-out
scripting hook) so an MCP client can pull Bible text directly from your
installed Accordance modules.

### Tools

| Tool | What it does |
|---|---|
| `list_modules` | Lists installed Bible text module codes (ESVS, KJVS, NA28-T, …) |
| `get_passage` | Fetches one passage from one module |
| `compare_translations` | Same passage across several modules, side by side |
| `open_in_accordance` | Navigates the Accordance UI to a reference (no text returned) |

### Known limits

- **Bible text only.** Commentaries and dictionaries (Accordance "Tools" like
  NICOT, WBC, ZIBBC) have no scripting hook and are not reachable.
- Reference syntax is Accordance's own: `John 3:16`, `John 3:1-5`, `Psalm 117`.
- Module codes are the internal `.atext` names. Use `list_modules` to see them.
- macOS only (uses `osascript`). Accordance must be installed.
- If a module cannot render a reference (e.g. John in a Hebrew Bible module),
  the server raises a proper error; `compare_translations` lists it under
  `[Skipped]` and returns the rest.

## Requirements

- macOS with [Accordance](https://www.accordancebible.com) installed
- Python 3.10+

## Install

```bash
git clone https://github.com/bodiequirk/accordance-mcp-server.git
cd accordance-mcp-server
bash install.sh
```

The installer creates a self-contained virtualenv and runs a John 3:16 smoke
test against your Accordance install.

Then add this to your Claude desktop config
(`~/Library/Application Support/Claude/claude_desktop_config.json`) inside
`"mcpServers"`, and restart Claude:

```json
"accordance": {
  "command": "/FULL/PATH/TO/accordance-mcp-server/.venv/bin/python",
  "args": ["/FULL/PATH/TO/accordance-mcp-server/accordance_server.py"]
}
```

(Use full absolute paths — the Claude config does not expand `~`.)

## Test from the command line

```bash
.venv/bin/python -c "import accordance_server as s; print(s.get_passage('John 3:16'))"
```

## Troubleshooting

- **Apple event error -609 ("Connection is invalid")** — Accordance is not
  running, or it launched and quit because a startup dialog (e.g. "locate My
  Highlights") went unanswered. Launch Accordance manually once, answer any
  dialogs, then retry.
- **First run from a new terminal** — macOS will ask permission for your
  terminal to control Accordance. Allow it.
- Accordance auto-launches when a tool is called, but an already-open
  Accordance is the most reliable setup.

## License

MIT — see [LICENSE](LICENSE).
