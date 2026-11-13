"""Pluggable sources that produce one normalized VOD record.

``manual_input`` copies fields a person already verified. ``official_api`` is
a stub for an authorized Rumble API or feed. Neither source may call the
network: there is no oEmbed client, no channel fetch, and no scraper here.

Validation policy, the three-item merge, and the HTML rewrite are separate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from scripts.rumble_vods.validate import (
    VodError,
    normalize_thumbnail,
    normalize_title,
    normalize_watch_url,
    parse_duration,
    parse_published_at,
)


@dataclass(frozen=True)
class VodRecord:
    """One normalized video.

    ``id`` is the watch-URL video id (the ``v...`` segment of
    ``https://rumble.com/<videoId>-<slug>.html``). ``site.js`` requires a
    non-empty ``id`` and uses it only as a stable key and as a tie-break when
    two ``publishedAt`` values match. The card does not read ``id`` and does
    not build a player from it.

    Older hand-edited rows store the Rumble embed id from oEmbed instead.
    That embed id is not in the watch URL, and this package does not call
    Rumble, so new rows use the watch-URL video id.
    """

    id: str
    title: str
    published_at: datetime
    published_at_text: str
    published_at_note: str
    watch_url: str
    thumbnail_url: str | None
    duration_seconds: int | None
    source: str


class MetadataSource(Protocol):
    """Build one normalized VOD record from somewhere other than the HTML file."""

    name: str

    def load(self) -> VodRecord:
        """Return a normalized record. Do not merge, sort, or edit HTML."""


class ManualInputSource:
    """Normalized record from workflow inputs. Performs no network I/O."""

    name = "manual_input"

    def __init__(
        self,
        video_url: str,
        title: str,
        published_at: str,
        thumbnail_url: str | None = None,
        duration_seconds: object = None,
    ) -> None:
        self.video_url = video_url
        self.title = title
        self.published_at = published_at
        self.thumbnail_url = thumbnail_url
        self.duration_seconds = duration_seconds

    def load(self) -> VodRecord:
        video_id, watch_url = normalize_watch_url(self.video_url)
        parsed = parse_published_at(self.published_at)
        return VodRecord(
            id=video_id,
            title=normalize_title(self.title),
            published_at=parsed.instant,
            published_at_text=parsed.text,
            published_at_note=parsed.note,
            watch_url=watch_url,
            thumbnail_url=normalize_thumbnail(self.thumbnail_url),
            duration_seconds=parse_duration(self.duration_seconds),
            source=self.name,
        )


class OfficialApiSource:
    """Future hook for an authorized Rumble API or official feed.

    ``load`` raises ``NotImplementedError``. Do not fetch oEmbed, the channel
    page, or any other Rumble URL from this class. When an official source
    exists, return a ``VodRecord`` and leave validation, merging, and the
    HTML writer unchanged.
    """

    name = "official_api"

    def load(self) -> VodRecord:
        raise NotImplementedError(
            "official_api metadata source is not implemented. "
            "Wire this to an authorized Rumble API or feed later. "
            "This workflow does not call Rumble or any third party."
        )


def get_source(name: str, **manual_fields: object) -> MetadataSource:
    """Return the named source. Unknown names fail before any I/O."""
    if name == "official_api":
        return OfficialApiSource()
    if name != "manual_input":
        raise VodError(
            f"unknown metadata source {name!r}. "
            "Implemented: manual_input. Stub: official_api."
        )
    thumbnail = manual_fields.get("thumbnail_url")
    if thumbnail is not None and not isinstance(thumbnail, str):
        raise VodError("thumbnail_url must be a string")
    return ManualInputSource(
        video_url=str(manual_fields.get("video_url", "")),
        title=str(manual_fields.get("title", "")),
        published_at=str(manual_fields.get("published_at", "")),
        thumbnail_url=thumbnail,
        duration_seconds=manual_fields.get("duration_seconds"),
    )
