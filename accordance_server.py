#!/usr/bin/env python3
"""
Accordance MCP Server
=====================

Exposes Accordance Bible Software's Scripture text to Claude (and any MCP
client) over stdio, using the only reliable data-out hook Accordance offers:
the `AccdTxRf` Apple event.

Proven primitive (tested 2026-06-06 on macOS):
    osascript -e 'tell application "Accordance" to «event AccdTxRf» {"ESVS", "John 3:16", true}'
    -> "For God so loved the world... (John 3:16)"

Tools exposed:
    - list_modules         : list installed Bible text modules (codes like ESVS, KJVS, NA28-T)
    - get_passage          : fetch text for a reference from one module
    - compare_translations : fetch the same reference across several modules
    - open_in_accordance   : navigate the Accordance UI to a reference (no text returned)

Notes / limitations:
    - Commentaries and other "Tools" (NICOT, WBC, ZIBBC, etc.) have NO data-out
      Apple event (-1708 "doesn't understand"), so they are not reachable here.
      Only Bible *text* modules work via AccdTxRf.
    - Reference syntax follows Accordance's own (e.g. "John 3:16", "John 3:1-5",
      "Psalm 117", "Rom 8:28-30").
    - Module codes are the internal names (the .atext filenames), e.g. ESVS, KJVS,
      NAS95S, NA28-T, LXX1. Use list_modules to see what's installed.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("accordance")

MODULES_DIR = Path.home() / "Library" / "Application Support" / "Accordance" / "Modules" / "Texts"


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #
def _osascript(script: str, timeout: int = 30) -> str:
    """Run an AppleScript snippet and return stdout, raising on error."""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            "Accordance did not respond within the timeout. Is it installed and able to launch?"
        )
    if result.returncode != 0:
        err = (result.stderr or "").strip()
        if "-609" in err:
            err += (
                " (Hint: Accordance may not be running, or may be stuck on a"
                " startup dialog. Launch Accordance manually once, answer any"
                " dialogs, then retry.)"
            )
        raise RuntimeError(err or "osascript failed with no error message.")
    return result.stdout.rstrip("\n")


def _as_string_literal(value: str) -> str:
    """Escape a Python string for safe embedding in an AppleScript double-quoted literal."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _fetch_passage(module: str, reference: str, include_citation: bool) -> str:
    """Fetch Scripture text via the AccdTxRf Apple event."""
    m = _as_string_literal(module)
    r = _as_string_literal(reference)
    cite = "true" if include_citation else "false"
    # The guillemets («») are required raw-event syntax; osascript accepts UTF-8.
    script = (
        f'tell application "Accordance" to '
        f'«event AccdTxRf» {{"{m}", "{r}", {cite}}}'
    )
    text = _osascript(script)
    if text.lstrip().startswith("ERR-"):
        raise RuntimeError(
            f'Accordance error for "{reference}" in module "{module}": '
            + text.strip()[4:].strip()
        )
    if not text.strip():
        raise RuntimeError(
            f'No text returned for "{reference}" in module "{module}". '
            f"Check the module code (see list_modules) and the reference syntax."
        )
    return text


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
@mcp.tool()
def list_modules() -> str:
    """List the installed Accordance Bible *text* module codes.

    These codes (e.g. ESVS, KJVS, NAS95S, NA28-T, LXX1) are what get_passage and
    compare_translations expect as the `module` argument. Only Bible text modules
    are listed; commentaries/dictionaries (Accordance "Tools") are not reachable.
    """
    if not MODULES_DIR.is_dir():
        raise RuntimeError(f"Accordance Texts folder not found at: {MODULES_DIR}")
    codes = sorted(
        p.stem for p in MODULES_DIR.glob("*.atext")
    )
    if not codes:
        raise RuntimeError(f"No .atext modules found in {MODULES_DIR}")
    return "Installed Bible text modules ({}):\n{}".format(len(codes), ", ".join(codes))


@mcp.tool()
def get_passage(reference: str, module: str = "ESVS", include_citation: bool = True) -> str:
    """Fetch the text of a Bible passage from Accordance.

    Args:
        reference: Accordance-style reference, e.g. "John 3:16", "John 3:1-5",
            "Psalm 117", "Rom 8:28-30".
        module: Bible text module code (default "ESVS"). See list_modules.
        include_citation: If True, append/format the reference citation as Accordance does.

    Returns:
        The Scripture text as plain text.
    """
    return _fetch_passage(module, reference, include_citation)


@mcp.tool()
def compare_translations(reference: str, modules: list[str]) -> str:
    """Fetch the same passage across multiple Bible text modules for comparison.

    Args:
        reference: Accordance-style reference, e.g. "John 1:1".
        modules: List of module codes, e.g. ["ESVS", "KJVS", "NAS95S", "NA28-T"].

    Returns:
        Each translation's text, labeled by module code.
    """
    if not modules:
        raise ValueError("Provide at least one module code in `modules`.")
    blocks: list[str] = []
    errors: list[str] = []
    for mod in modules:
        try:
            text = _fetch_passage(mod, reference, include_citation=False)
            blocks.append(f"=== {mod} — {reference} ===\n{text}")
        except Exception as exc:  # noqa: BLE001 - surface per-module failure, keep going
            errors.append(f"{mod}: {exc}")
    out = "\n\n".join(blocks)
    if errors:
        out += "\n\n[Skipped]\n" + "\n".join(errors)
    if not blocks:
        raise RuntimeError("No translations could be fetched.\n" + "\n".join(errors))
    return out


@mcp.tool()
def open_in_accordance(reference: str, module: str = "ESVS") -> str:
    """Open/navigate the Accordance app to a reference (UI action; returns no text).

    Useful when you want to look something up in Accordance itself rather than
    pull the text. Uses the accord:// URL scheme.

    Args:
        reference: e.g. "John 3:16". Spaces are converted to underscores for the URL.
        module: Bible text module code (default "ESVS").
    """
    url_ref = reference.strip().replace(" ", "_")
    url = f"accord://read/{module}?{url_ref}"
    subprocess.run(["open", url], check=False)
    return f"Asked Accordance to open: {url}"


if __name__ == "__main__":
    mcp.run()
