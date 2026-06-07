#!/bin/bash
# Accordance MCP Server installer — sets up a self-contained venv.
# Run from inside the server folder after copying it into place.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "Installing Accordance MCP server in: $DIR"

# Create venv if missing
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
  echo "Created virtualenv."
fi

# Install the MCP SDK
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet mcp
echo "Installed mcp SDK."

# Smoke-test: load the module and fetch a verse
echo "--- Smoke test: John 3:16 (ESVS) ---"
.venv/bin/python -c "import accordance_server as s; print(s.get_passage('John 3:16'))" || {
  echo "Smoke test failed — check that Accordance is installed and can launch."
  exit 1
}

echo ""
echo "Done. Python interpreter for the Claude config:"
echo "  $DIR/.venv/bin/python"
echo "Server script:"
echo "  $DIR/accordance_server.py"
