"""Static check for the featured Rumble block in ``index.html``.

There is no site build. This script parses the inline JSON and checks the
rules the page actually enforces, plus the canonical watch-URL shape from
``docs/rumble-vods.md``. It does not fetch URLs.

Thumbnail hosts are only required to be ``https``, matching ``site.js``.
The add workflow is stricter and allowlists Rumble CDN hosts before it writes.
``durationSeconds`` may be missing, ``null``, or a non-negative number. The
card does not read it. ``id`` may be an embed id or a watch-URL video id;
``site.js`` only requires a non-empty string.
"""

from __future__ import annotations

import argparse
import math
import sys
from functools import cmp_to_key
from pathlib import Path

from scripts.rumble_vods.html_block import parse_block
from scripts.rumble_vods.merge import compare_items
from scripts.rumble_vods.validate import (
    PUBLISHED_AT_RE,
    VodError,
    is_https_rumble,
    is_https_url,
    normalize_watch_url,
    parse_stored_published_at,
)


def check_data(data: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["featured-rumble-data JSON must be an object"]
    if not is_https_rumble(data.get("channelUrl")):
        errors.append("channelUrl must be an https://rumble.com URL")
    updated = data.get("updatedAt")
    if not isinstance(updated, str) or PUBLISHED_AT_RE.fullmatch(updated.strip()) is None:
        errors.append("updatedAt must be ISO 8601 with Z or ±HH:MM")
    else:
        try:
            parse_stored_published_at(updated)
        except VodError as exc:
            errors.append(f"updatedAt: {exc}")

    items = data.get("items")
    if not isinstance(items, list):
        errors.append("items must be a list")
        return errors
    if not 1 <= len(items) <= 3:
        errors.append(f"items must contain 1 to 3 videos, found {len(items)}")

    for index, item in enumerate(items):
        errors.extend(_check_item(index, item))

    if items and all(isinstance(item, dict) for item in items):
        try:
            ordered = sorted(items, key=cmp_to_key(compare_items))
        except VodError as exc:
            errors.append(str(exc))
        else:
            if ordered != items:
                errors.append(
                    "items must be sorted by publishedAt descending "
                    "(id ascending when times match)"
                )
    return errors


def _check_item(index: int, item: object) -> list[str]:
    prefix = f"items[{index}]"
    if not isinstance(item, dict):
        return [f"{prefix} is not an object"]
    errors: list[str] = []
    ident = item.get("id")
    if not isinstance(ident, str) or not ident.strip():
        errors.append(f"{prefix}.id must be a non-empty string")
    title = item.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append(f"{prefix}.title must be a non-empty string")
    published = item.get("publishedAt")
    if not isinstance(published, str) or PUBLISHED_AT_RE.fullmatch(published.strip()) is None:
        errors.append(f"{prefix}.publishedAt must be ISO 8601 with Z or ±HH:MM")
    else:
        try:
            parse_stored_published_at(published)
        except VodError as exc:
            errors.append(f"{prefix}.publishedAt: {exc}")

    watch = item.get("watchUrl")
    if not isinstance(watch, str):
        errors.append(f"{prefix}.watchUrl must be a string")
    else:
        try:
            _video_id, canonical = normalize_watch_url(watch)
        except VodError as exc:
            errors.append(f"{prefix}.watchUrl: {exc}")
        else:
            if watch.strip() != canonical:
                errors.append(f"{prefix}.watchUrl must be canonical ({canonical})")

    if "thumbnailUrl" in item:
        thumb = item.get("thumbnailUrl")
        if thumb is not None and thumb != "":
            if not is_https_url(thumb):
                errors.append(f"{prefix}.thumbnailUrl must be an https URL")
    if "durationSeconds" in item:
        duration_error = _duration_error(item.get("durationSeconds"))
        if duration_error:
            errors.append(f"{prefix}.{duration_error}")
    return errors


def _duration_error(value: object) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "durationSeconds must be a non-negative number, null, or omitted"
    if isinstance(value, float) and not math.isfinite(value):
        return "durationSeconds must be a non-negative finite number"
    if value < 0:
        return "durationSeconds must be a non-negative finite number"
    return None


def check_html(html: str) -> list[str]:
    try:
        data = parse_block(html)
    except VodError as exc:
        return [str(exc)]
    return check_data(data)


def check_index(path: Path) -> list[str]:
    try:
        html = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"could not read {path}: {exc}"]
    return check_html(html)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check the featured-rumble-data block in index.html."
    )
    parser.add_argument("--index", required=True)
    args = parser.parse_args(argv)
    errors = check_index(Path(args.index))
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    data = parse_block(Path(args.index).read_text(encoding="utf-8"))
    count = len(data["items"])
    print(f"featured-rumble-data OK ({count} items)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
