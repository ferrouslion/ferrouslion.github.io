"""Duplicate checks, newest-first sort, and the three-item cap.

Existing item dicts are kept as parsed so unknown keys and key order survive.
The new item is a fresh dict. ``id`` on that new item is the watch-URL video
id; existing rows may still carry an embed id, and both are accepted.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cmp_to_key

from scripts.rumble_vods.metadata import VodRecord
from scripts.rumble_vods.validate import (
    VodError,
    normalize_watch_url,
    parse_stored_published_at,
)

KEEP_COUNT = 3


@dataclass(frozen=True)
class MergeResult:
    kept: list[dict]
    removed: list[dict]
    added: dict


def record_to_item(record: VodRecord) -> dict:
    """JSON object for a new row. Omit thumbnail and duration when absent.

    ``site.js`` treats a missing ``durationSeconds``, ``null``, and ``""`` as
    "no duration" and still renders the card. The card never displays it.
    """
    item = {
        "id": record.id,
        "title": record.title,
        "publishedAt": record.published_at_text,
        "watchUrl": record.watch_url,
    }
    if record.thumbnail_url is not None:
        item["thumbnailUrl"] = record.thumbnail_url
    if record.duration_seconds is not None:
        item["durationSeconds"] = record.duration_seconds
    return item


def compare_items(left: dict, right: dict) -> int:
    """Newest ``publishedAt`` first. Equal times break ties by ``id`` ascending.

    This matches the sort in ``site.js`` ``loadFeaturedRumble``.
    """
    left_time = parse_stored_published_at(left.get("publishedAt"))
    right_time = parse_stored_published_at(right.get("publishedAt"))
    if left_time != right_time:
        return -1 if left_time > right_time else 1
    left_id = left.get("id") if isinstance(left.get("id"), str) else ""
    right_id = right.get("id") if isinstance(right.get("id"), str) else ""
    if left_id < right_id:
        return -1
    if left_id > right_id:
        return 1
    return 0


def merge_items(existing: list, record: VodRecord) -> MergeResult:
    """Insert ``record``, sort, and keep at most three.

    Raises ``VodError`` on a duplicate or when the new video would not be
    shown. The caller leaves the file untouched in those cases.
    """
    if not isinstance(existing, list):
        raise VodError("items must be a list")
    for index, item in enumerate(existing):
        if not isinstance(item, dict):
            raise VodError(f"items[{index}] is not an object")

    _reject_duplicates(existing, record)
    added = record_to_item(record)
    combined = [*existing, added]
    combined.sort(key=cmp_to_key(compare_items))
    kept = combined[:KEEP_COUNT]
    if all(item is not added for item in kept):
        raise VodError(_not_kept_message(kept, record))
    kept_ids = {id(item) for item in kept}
    removed = [item for item in existing if id(item) not in kept_ids]
    return MergeResult(kept=kept, removed=removed, added=added)


def _label(item: dict) -> str:
    title = item.get("title")
    if isinstance(title, str) and title.strip():
        return f" ({title.strip()})"
    return ""


def _reject_duplicates(existing: list[dict], record: VodRecord) -> None:
    new_id = record.id.casefold()
    for item in existing:
        watch = item.get("watchUrl")
        if isinstance(watch, str) and watch.strip():
            try:
                video_id, canonical = normalize_watch_url(watch)
            except VodError as exc:
                raise VodError(f"existing item watchUrl cannot be read: {exc}") from exc
            if canonical == record.watch_url:
                raise VodError(
                    "duplicate: watch URL already in featured-rumble-data: "
                    f"{record.watch_url}{_label(item)}"
                )
            if video_id.casefold() == new_id:
                raise VodError(
                    f"duplicate: video id {record.id} is already present on "
                    f"{canonical}{_label(item)}"
                )
        item_id = item.get("id")
        if isinstance(item_id, str) and item_id.strip().casefold() == new_id:
            raise VodError(
                f"duplicate: video id {record.id} is already present as an item id"
                f"{_label(item)}"
            )


def _not_kept_message(kept: list[dict], record: VodRecord) -> str:
    if not kept:
        span = "there is nothing else in the gallery"
    else:
        span = (
            f"the kept range is {kept[0].get('publishedAt')} down to "
            f"{kept[-1].get('publishedAt')}"
        )
    return (
        "the new VOD is not among the three newest and was not added. "
        f"Its publishedAt is {record.published_at_text}; {span}. "
        "No file was changed."
    )
