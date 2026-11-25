#!/usr/bin/env python3
"""Read-only MCP server for inspecting a local codebase."""
from functools import wraps
from itertools import islice
import os
from pathlib import Path
import re

from mcp.server import MCPServer

mcp = MCPServer("codebase-server")

SKIP = {".git", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache", "dist", "build"}
MAX_FILE_BYTES = 2_000_000
# ponytail: single root for every tool; set MCP_ROOT to inspect another directory.
ROOT = Path(os.getenv("MCP_ROOT", Path.cwd())).resolve()


def _path(raw: str) -> Path:
    p = Path(raw).expanduser()
    p = (p if p.is_absolute() else ROOT / p).resolve()
    if not p.is_relative_to(ROOT):
        raise ValueError(f"Path outside MCP_ROOT ({ROOT}): {p}")
    return p


def _safe(fn):
    """Turn path errors into text the model can read and act on."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (ValueError, OSError) as e:
            return str(e)
    return wrapper


def _files(root: Path, pattern: str = "*"):
    for f in root.rglob(pattern):
        rel = f.relative_to(root).parts
        if (f.is_file() and not f.is_symlink() and f.resolve().is_relative_to(ROOT)
                and not any(part in SKIP for part in rel) and f.stat().st_size <= MAX_FILE_BYTES):
            yield f


@mcp.tool()
@_safe
def project_summary(path: str = ".") -> str:
    """Count files, lines and languages under a directory."""
    root = _path(path)
    if not root.is_dir():
        return f"Not a directory: {root}"
    files = lines = 0
    by_ext: dict[str, int] = {}
    largest: list[tuple[int, Path]] = []
    for f in _files(root):
        try:
            n = sum(1 for _ in f.open(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
        files += 1
        lines += n
        ext = f.suffix or "(none)"
        by_ext[ext] = by_ext.get(ext, 0) + 1
        largest.append((n, f.relative_to(root)))
    if not files:
        return f"No readable files under {root}"
    top = "\n".join(f"  {rel} - {n} lines" for n, rel in sorted(largest, reverse=True)[:5])
    langs = ", ".join(f"{e}: {c}" for e, c in sorted(by_ext.items(), key=lambda kv: -kv[1])[:8])
    return f"{root}\n{files} files, {lines} lines\nBy extension: {langs}\nLargest files:\n{top}"


@mcp.tool()
@_safe
def list_directory(path: str = ".") -> str:
    """List files and folders in a directory with sizes."""
    d = _path(path)
    if not d.is_dir():
        return f"Not a directory: {d}"
    rows = []
    for p in sorted(d.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
        if p.name in SKIP:
            continue
        size = "" if p.is_dir() else f"  {p.stat().st_size:,} B"
        rows.append(f"{'dir' if p.is_dir() else 'file':4} {p.name}{size}")
    return f"{d}\n" + "\n".join(rows[:100])


@mcp.tool()
@_safe
def read_file(path: str, start_line: int = 1, max_lines: int = 200) -> str:
    """Read a text file with line numbers, from start_line for max_lines lines."""
    f = _path(path)
    if not f.is_file():
        return f"Not a file: {f}"
    if f.stat().st_size > MAX_FILE_BYTES:
        return f"File too large ({f.stat().st_size:,} B): {f}"
    max_lines = min(max(max_lines, 1), 500)
    skip = max(start_line - 1, 0)
    with f.open(encoding="utf-8", errors="replace") as fh:
        lines = [line.rstrip("\n") for line in islice(fh, skip, skip + max_lines)]
        more = fh.readline() != ""
    body = "\n".join(f"{i:4} | {line}" for i, line in enumerate(lines, skip + 1))
    suffix = "\n... truncated" if more else ""
    return f"{f}\n{body}{suffix}"


@mcp.tool()
@_safe
def search_code(query: str, path: str = ".", file_glob: str = "*", max_results: int = 50) -> str:
    """Search a regex across files, returning file:line:match."""
    root = _path(path)
    max_results = min(max(max_results, 1), 200)
    try:
        pattern = re.compile(query)
    except re.error as e:
        return f"Invalid regex: {e}"
    out = []
    for f in _files(root, file_glob):
        try:
            for i, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if pattern.search(line):
                    out.append(f"{f.relative_to(root)}:{i}: {line.strip()[:160]}")
                    if len(out) >= max_results:
                        return "\n".join(out) + f"\n... capped at {max_results} results"
        except OSError:
            continue
    return "\n".join(out) if out else f"No matches for {query!r} under {root}"


@mcp.prompt()
def codebase_report(path: str = ".") -> list[dict]:
    """Guide the model through inspecting a codebase and writing a short report."""
    return [{
        "role": "user",
        "content": {"type": "text", "text":
            f"Inspect the codebase in `{path}`. Use tools in this order:\n"
            f"1. project_summary(path='{path}')\n"
            f"2. list_directory(path='{path}')\n"
            f"3. search_code(query='TODO|FIXME|pass', path='{path}')\n"
            f"4. read_file(path=...) on the two most interesting files\n"
            f"Then reply with: what the project does, its main components, "
            f"and two concrete improvements."
        }
    }]


def main():
    mcp.run()


if __name__ == "__main__":
    main()
