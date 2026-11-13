"""Read and rewrite only the ``#featured-rumble-data`` JSON block.

The surrounding HTML, including the script tag and its indentation, stays
byte for byte. The JSON inside uses the block's existing indent width
(the live page uses two spaces) and ``json.dumps`` key order, which is the
order ``json.loads`` preserved.
"""

from __future__ import annotations

import json

from scripts.rumble_vods.validate import VodError

OPEN_TAG = '<script type="application/json" id="featured-rumble-data">'
CLOSE_TAG = "</script>"


def locate_block(html: str) -> tuple[int, int]:
    """Return the half-open span of the text inside the script tag."""
    start = html.find(OPEN_TAG)
    if start < 0:
        raise VodError(
            "featured-rumble-data block not found. Expected "
            '<script type="application/json" id="featured-rumble-data">.'
        )
    if html.find(OPEN_TAG, start + len(OPEN_TAG)) != -1:
        raise VodError("multiple featured-rumble-data blocks found")
    content_start = start + len(OPEN_TAG)
    content_end = html.find(CLOSE_TAG, content_start)
    if content_end < 0:
        raise VodError("featured-rumble-data block is missing </script>")
    return content_start, content_end


def parse_block(html: str) -> dict:
    content_start, content_end = locate_block(html)
    inner = html[content_start:content_end]
    try:
        data = json.loads(inner)
    except json.JSONDecodeError as exc:
        raise VodError(f"featured-rumble-data is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise VodError("featured-rumble-data JSON must be an object")
    return data


def _indent_of(inner: str) -> int:
    for line in inner.splitlines():
        stripped = line.lstrip(" ")
        if stripped.startswith('"') and len(stripped) < len(line):
            return len(line) - len(stripped)
    return 2


def _edge_whitespace(inner: str) -> tuple[str, str]:
    """Whitespace around the JSON, including the indent before ``</script>``."""
    stripped_left = inner.lstrip(" \t\r\n")
    leading = inner[: len(inner) - len(stripped_left)]
    core = stripped_left.rstrip(" \t\r\n")
    trailing = stripped_left[len(core) :]
    return leading, trailing


def render_inner(data: dict, template_inner: str) -> str:
    indent = _indent_of(template_inner)
    text = json.dumps(data, indent=indent, ensure_ascii=False)
    leading, trailing = _edge_whitespace(template_inner)
    return f"{leading}{text}{trailing}"


def write_block(html: str, data: dict) -> str:
    """Replace the JSON text of the block and nothing else."""
    content_start, content_end = locate_block(html)
    inner = html[content_start:content_end]
    rendered = render_inner(data, inner)
    return html[:content_start] + rendered + html[content_end:]
