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

import re
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


# --------------------------------------------------------------------------- #
# Tool (commentary/dictionary/lexicon) access — UI + clipboard bridge
# --------------------------------------------------------------------------- #
MODULES_ROOT = Path.home() / "Library" / "Application Support" / "Accordance" / "Modules"


@mcp.tool()
def list_tools() -> str:
    """List installed Accordance *Tool* modules — commentaries, dictionaries,
    lexicons, study-bible notes — the resources get_passage cannot reach.

    Their text can't be pulled back (Accordance exposes no hook for it); use
    open_tool to navigate Accordance to one for in-app reading. The name shown
    is the on-disk module filename; that exact spelling is what open_tool's
    `tool` argument expects.
    """
    if not MODULES_ROOT.is_dir():
        raise RuntimeError(f"Accordance Modules folder not found at: {MODULES_ROOT}")
    # Accordance Tool modules are .atool bundles (often folders). Match the
    # bundle itself and DO NOT descend into it, or we'd list its internals.
    bundles = sorted(MODULES_ROOT.rglob("*.atool"), key=lambda p: str(p).lower())
    if not bundles:
        raise RuntimeError(
            f"No .atool modules found under {MODULES_ROOT}. "
            f"Subfolders present: {', '.join(sorted(c.name for c in MODULES_ROOT.iterdir() if c.is_dir()))}"
        )
    groups: dict[str, list[str]] = {}
    for p in bundles:
        rel = p.relative_to(MODULES_ROOT)
        top = rel.parts[0] if len(rel.parts) > 1 else "(root)"
        groups.setdefault(top, []).append(p.stem)
    out: list[str] = [f"{len(bundles)} Tool module(s) installed:"]
    for folder in sorted(groups):
        items = sorted(set(groups[folder]))
        out.append(f"\n=== {folder} ({len(items)}) ===")
        out.extend(items)
    return "\n".join(out)


@mcp.tool()
def open_tool(reference: str, tool: str) -> str:
    """Open an Accordance *Tool* (commentary, dictionary, lexicon) at a reference.

    Accordance exposes no scripting hook to return Tool text, so this navigates
    the Accordance UI to the right spot for you to read there. (Bible *text* is
    different and can be pulled back directly — use get_passage / search_text.)

    Args:
        reference: e.g. "Rom 8:28" for a Scripture-keyed commentary, or a
            headword/article title for a dictionary.
        tool: the Tool module name (see list_tools), e.g. "WBC-NT-25", "BDAG".
    """
    url_ref = reference.strip().replace(" ", "_")
    url = f"accord://read/{tool}?{url_ref}"
    subprocess.run(["open", url], check=False)
    return f"Opened Accordance to {tool} at {reference}."


# --------------------------------------------------------------------------- #
# Bible-text search (built on the readable AccdTxRf hook, verse by verse)
# --------------------------------------------------------------------------- #
def _fetch_single_verse(module: str, book: str, chapter: int, verse: int):
    """Fetch one verse and parse its trailing "(Book C:V ABBR)" citation.

    Returns (text, actual_chapter, actual_verse), or None if nothing usable.
    Accordance clamps out-of-range verses to the last real verse, so a returned
    verse/chapter that differs from what was asked marks an edge (end of chapter
    or end of book).
    """
    raw = _fetch_passage(module, f"{book} {chapter}:{verse}", include_citation=True)
    m = re.search(r"\(([^()]*)\)\s*$", raw)
    if not m:
        return None
    pairs = re.findall(r"(\d+):(\d+)", m.group(1))
    if not pairs:
        return None
    actual_chapter, actual_verse = int(pairs[-1][0]), int(pairs[-1][1])
    text = raw[: m.start()].strip()
    return text, actual_chapter, actual_verse


@mcp.tool()
def search_text(
    query: str,
    book: str,
    module: str = "ESVS",
    start_chapter: int = 1,
    end_chapter: int = 0,
    regex: bool = False,
    ignore_case: bool = True,
    max_hits: int = 200,
    max_verses: int = 4000,
) -> str:
    """Search a book (or chapter range) of a Bible *text* module and return the
    matching verses with their references.

    Works entirely on the readable text hook, walking verse by verse, so it is
    exact but not instant — scope it to a book or a chapter range. Works on any
    text module from list_modules, including tagged Greek/Hebrew (pass the query
    in the module's script for original-language searches).

    Args:
        query: substring to find (default) or a regular expression if regex=True.
        book: Accordance book name, e.g. "Romans", "John", "1 Corinthians", "Gen".
        module: Bible text module code (default "ESVS"). See list_modules.
        start_chapter: first chapter to scan (default 1).
        end_chapter: last chapter to scan; 0 means "to the end of the book".
        regex: treat query as a Python regular expression.
        ignore_case: case-insensitive match (default True).
        max_hits: stop after this many matches.
        max_verses: safety cap on total verses scanned.

    Returns:
        A header line plus each matching verse, labeled by reference.
    """
    flags = re.IGNORECASE if ignore_case else 0
    if regex:
        pattern = re.compile(query, flags)
        def matches(text: str) -> bool:
            return bool(pattern.search(text))
    else:
        needle = query.lower() if ignore_case else query
        def matches(text: str) -> bool:
            hay = text.lower() if ignore_case else text
            return needle in hay

    hits: list[tuple[int, int, str]] = []
    scanned = 0
    capped = False
    chapter = max(1, start_chapter)
    last_chapter = end_chapter if end_chapter and end_chapter > 0 else 10_000

    while chapter <= last_chapter:
        verse = 1
        chapter_had_verses = False
        while True:
            if scanned >= max_verses or len(hits) >= max_hits:
                capped = True
                break
            try:
                result = _fetch_single_verse(module, book, chapter, verse)
            except RuntimeError:
                result = None
            if result is None:
                break
            text, actual_chapter, actual_verse = result
            if actual_chapter != chapter or actual_verse != verse:
                break  # clamped -> past the end of this chapter (or the book)
            chapter_had_verses = True
            scanned += 1
            if matches(text):
                hits.append((chapter, actual_verse, text))
            verse += 1
        if capped or not chapter_had_verses:
            break  # no verse 1 in this chapter -> book has ended
        chapter += 1

    header = (
        f'Search "{query}" in {book} ({module}): '
        f"{len(hits)} hit(s), {scanned} verse(s) scanned"
    )
    if capped:
        header += " [stopped at a limit — narrow the scope or raise max_hits/max_verses]"
    if not hits:
        return header + "\n(no matches)"
    lines = [header]
    for ch, vs, text in hits:
        lines.append(f"\n{book} {ch}:{vs} — {text}")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
