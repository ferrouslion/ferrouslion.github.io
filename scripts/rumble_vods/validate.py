"""Local checks for one VOD record and for values already stored in the block.

Nothing in this module opens a socket. Thumbnail and watch URLs are parsed
and compared to an allowlist; they are not fetched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

CHICAGO = ZoneInfo("America/Chicago")
FUTURE_TOLERANCE = timedelta(minutes=5)
MAX_TITLE_LENGTH = 300
MAX_DURATION_SECONDS = 48 * 60 * 60

NOTE_CHICAGO = (
    "Input had no offset; interpreted as America/Chicago and converted to UTC."
)
NOTE_OFFSET = "Input included an explicit offset and was converted to UTC."
NOTE_FRACTION = " Fractional seconds were truncated."

PUBLISHED_AT_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$",
    re.ASCII,
)
_OFFSET_RE = re.compile(
    r"^(?P<body>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?)(?P<tz>Z|[+-]\d{2}:\d{2})$",
    re.ASCII | re.IGNORECASE,
)
_NAIVE_RE = re.compile(
    r"^(?P<body>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?)$",
    re.ASCII,
)
_WATCH_PATH_RE = re.compile(
    r"^/(?P<id>v[0-9A-Za-z]+)-(?P<slug>[0-9A-Za-z]+(?:-[0-9A-Za-z]+)*)\.html$",
    re.ASCII,
)
_DURATION_TEXT_RE = re.compile(r"^(?:0|[1-9][0-9]*)$", re.ASCII)
_SCRIPT_CLOSE_RE = re.compile(r"<\s*/\s*script", re.IGNORECASE)
_THUMB_SUFFIXES = ("rumble.cloud", "rmbl.ws", "rumble.com")

_ACCEPTED_PUBLISHED_AT = (
    "published_at must be ISO 8601 with seconds: "
    "YYYY-MM-DDTHH:MM:SSZ, YYYY-MM-DDTHH:MM:SS±HH:MM, "
    "or YYYY-MM-DDTHH:MM:SS with no offset "
    "(no offset is interpreted as America/Chicago and converted to UTC)"
)


class VodError(Exception):
    """A problem with an input, the gallery block, or a merge. Safe to print."""


@dataclass(frozen=True)
class ParsedTime:
    instant: datetime
    text: str
    note: str
    assumed_chicago: bool


def format_utc(instant: datetime) -> str:
    """UTC timestamp in the ``+00:00`` form already used by ``publishedAt``."""
    utc = instant.astimezone(timezone.utc).replace(microsecond=0)
    return utc.strftime("%Y-%m-%dT%H:%M:%S+00:00")


def format_updated_at(instant: datetime) -> str:
    """UTC timestamp in the ``Z`` form already used by ``updatedAt``."""
    utc = instant.astimezone(timezone.utc).replace(microsecond=0)
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def format_chicago(instant: datetime) -> str:
    """Clock time in America/Chicago, for pull-request text."""
    local = instant.astimezone(CHICAGO)
    hour = local.hour % 12 or 12
    ampm = "AM" if local.hour < 12 else "PM"
    return (
        f"{local.strftime('%b')} {local.day}, {local.year}, "
        f"{hour}:{local.minute:02d}:{local.second:02d} {ampm} CT"
    )


def normalize_watch_url(value: object) -> tuple[str, str]:
    """Return ``(video_id, canonical_url)`` with query and fragment removed."""
    if not isinstance(value, str):
        raise VodError("video_url must be a string")
    raw = value.strip()
    if not raw:
        raise VodError("video_url is empty")
    parts = urlsplit(raw)
    if parts.scheme.lower() != "https":
        raise VodError("video_url must start with https://")
    if parts.username or parts.password:
        raise VodError("video_url must not include a username or password")
    if parts.hostname != "rumble.com":
        raise VodError("video_url host must be rumble.com")
    if parts.port not in (None, 443):
        raise VodError("video_url must not include a port")
    match = _WATCH_PATH_RE.match(parts.path)
    if not match:
        raise VodError(
            "video_url must look like https://rumble.com/<videoId>-<slug>.html "
            "(videoId is v followed by letters and digits). "
            "Query and fragment are removed."
        )
    video_id = match.group("id")
    slug = match.group("slug")
    return video_id, f"https://rumble.com/{video_id}-{slug}.html"


def normalize_title(value: object) -> str:
    if not isinstance(value, str):
        raise VodError("title must be a string")
    title = value.strip()
    if not title:
        raise VodError("title is empty")
    if len(title) > MAX_TITLE_LENGTH:
        raise VodError(
            f"title is {len(title)} characters; the maximum is {MAX_TITLE_LENGTH}"
        )
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in title):
        raise VodError("title contains control characters")
    if _SCRIPT_CLOSE_RE.search(title):
        raise VodError("title cannot contain a closing script tag")
    return title


def parse_published_at(value: object) -> ParsedTime:
    """Parse an operator-supplied time and convert it to UTC.

    A value with ``Z`` or ``±hh:mm`` uses that offset. A value with no offset
    is interpreted as America/Chicago (standard or daylight time) and converted
    to UTC. The returned note states which of those happened. Sub-second
    precision is truncated.
    """
    if not isinstance(value, str):
        raise VodError("published_at must be a string")
    raw = value.strip()
    if not raw:
        raise VodError("published_at is empty")
    if " " in raw:
        raise VodError(
            "published_at must use T between the date and time "
            "(for example 2026-11-12T18:30:00 or 2026-11-13T00:30:00Z)"
        )

    offset_match = _OFFSET_RE.match(raw)
    naive_match = None if offset_match else _NAIVE_RE.match(raw)
    if offset_match is None and naive_match is None:
        raise VodError(_ACCEPTED_PUBLISHED_AT)

    if offset_match:
        body = offset_match.group("body")
        tz_text = offset_match.group("tz")
        iso = body + ("+00:00" if tz_text.upper() == "Z" else tz_text)
        note = NOTE_OFFSET
        assumed_chicago = False
    else:
        assert naive_match is not None
        body = naive_match.group("body")
        iso = ""
        note = NOTE_CHICAGO
        assumed_chicago = True

    if "." in body:
        note += NOTE_FRACTION

    try:
        if assumed_chicago:
            aware = _attach_chicago(datetime.fromisoformat(body))
        else:
            aware = datetime.fromisoformat(iso)
    except ValueError as exc:
        raise VodError(f"published_at is not a real date/time: {raw}") from exc
    if aware.tzinfo is None:
        raise VodError("published_at is missing a timezone")

    instant = aware.astimezone(timezone.utc).replace(microsecond=0)
    return ParsedTime(
        instant=instant,
        text=format_utc(instant),
        note=note,
        assumed_chicago=assumed_chicago,
    )


def _attach_chicago(naive: datetime) -> datetime:
    aware = naive.replace(tzinfo=CHICAGO)
    round_trip = aware.astimezone(timezone.utc).astimezone(CHICAGO).replace(tzinfo=None)
    if round_trip != naive:
        raise VodError(
            "published_at is not a valid America/Chicago time "
            "(it falls in a daylight-saving gap). Provide an explicit offset."
        )
    return aware


def assert_not_future(instant: datetime, now: datetime) -> None:
    if now.tzinfo is None or instant.tzinfo is None:
        raise VodError("published_at comparisons require timezone-aware datetimes")
    limit = now.astimezone(timezone.utc) + FUTURE_TOLERANCE
    if instant.astimezone(timezone.utc) > limit:
        raise VodError("published_at is more than 5 minutes in the future")


def parse_stored_published_at(value: object) -> datetime:
    """Parse a ``publishedAt`` already stored in the block (offset required)."""
    if not isinstance(value, str) or PUBLISHED_AT_RE.fullmatch(value.strip()) is None:
        raise VodError(
            "an existing item has publishedAt the site would drop; "
            "expected ISO 8601 with Z or ±HH:MM"
        )
    text = value.strip()
    if text[-1] in "Zz":
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise VodError(
            "an existing item has a publishedAt that is not a real timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise VodError("an existing item publishedAt is missing a timezone")
    return parsed.astimezone(timezone.utc)


def thumbnail_host_allowed(hostname: str) -> bool:
    host = hostname.lower().rstrip(".")
    return any(host == suffix or host.endswith("." + suffix) for suffix in _THUMB_SUFFIXES)


def normalize_thumbnail(value: object) -> str | None:
    """Return a canonical thumbnail URL, or None when the input is blank.

    Hosts must be rumble.cloud, rmbl.ws, rumble.com, or a subdomain of those.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise VodError("thumbnail_url must be a string")
    raw = value.strip()
    if raw == "":
        return None
    parts = urlsplit(raw)
    if parts.scheme.lower() != "https":
        raise VodError("thumbnail_url must start with https://")
    if parts.username or parts.password:
        raise VodError("thumbnail_url must not include a username or password")
    host = parts.hostname
    if not host or not thumbnail_host_allowed(host):
        raise VodError(
            "thumbnail_url host must be rumble.cloud, rmbl.ws, rumble.com, "
            "or a subdomain of one of those"
        )
    if parts.port not in (None, 443):
        raise VodError("thumbnail_url must not include a port")
    if parts.path in ("", "/"):
        raise VodError("thumbnail_url must include a path")
    return urlunsplit(("https", host.lower().rstrip("."), parts.path, parts.query, ""))


def parse_duration(value: object) -> int | None:
    """Parse optional duration. Blank becomes None so the JSON key is omitted."""
    if value is None:
        return None
    if isinstance(value, str):
        raw = value.strip()
        if raw == "":
            return None
        if _DURATION_TEXT_RE.fullmatch(raw) is None:
            raise VodError(
                "duration_seconds must be a non-negative whole number of seconds "
                f"(maximum {MAX_DURATION_SECONDS}, 48 hours). Leave it empty to omit."
            )
        number = int(raw)
    elif isinstance(value, bool) or not isinstance(value, int):
        raise VodError(
            "duration_seconds must be a non-negative whole number of seconds"
        )
    else:
        number = value
    if number < 0 or number > MAX_DURATION_SECONDS:
        raise VodError(
            f"duration_seconds must be between 0 and {MAX_DURATION_SECONDS} (48 hours)"
        )
    return number


def is_https_rumble(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parts = urlsplit(value.strip())
    return (
        parts.scheme == "https"
        and parts.hostname == "rumble.com"
        and not parts.username
        and not parts.password
        and parts.port in (None, 443)
    )


def is_https_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parts = urlsplit(value.strip())
    return (
        parts.scheme == "https"
        and bool(parts.hostname)
        and not parts.username
        and not parts.password
    )


def validate_record(record: object, *, now: datetime) -> None:
    """Policy checks for a record a metadata source already normalized.

    Shape (URL, title, thumbnail host, duration, Chicago conversion) is
    applied again so a future ``official_api`` source cannot skip it.
    Duplicate detection lives in ``merge``. The record is checked by the
    attributes ``VodRecord`` provides, not by importing that type, so this
    module stays independent of the metadata sources.
    """
    required = (
        "id",
        "title",
        "published_at",
        "published_at_text",
        "published_at_note",
        "watch_url",
        "thumbnail_url",
        "duration_seconds",
    )
    if any(not hasattr(record, name) for name in required):
        raise VodError("metadata source did not return a VOD record")
    if now.tzinfo is None:
        raise VodError("clock must be timezone-aware")
    video_id, watch_url = normalize_watch_url(record.watch_url)
    if record.id != video_id or record.watch_url != watch_url:
        raise VodError("record id must be the watch-URL video id")
    if normalize_title(record.title) != record.title:
        raise VodError("title is not normalized")
    if record.published_at.tzinfo is None:
        raise VodError("published_at must be timezone-aware")
    if record.published_at_text != format_utc(record.published_at):
        raise VodError("published_at_text does not match the UTC instant")
    assert_not_future(record.published_at, now)
    if record.thumbnail_url is not None:
        if normalize_thumbnail(record.thumbnail_url) != record.thumbnail_url:
            raise VodError("thumbnail_url is not normalized")
    if record.duration_seconds is not None:
        if parse_duration(record.duration_seconds) != record.duration_seconds:
            raise VodError("duration_seconds is not a whole number of seconds")
    if not isinstance(record.published_at_note, str) or not record.published_at_note:
        raise VodError("published_at_note must explain how the time was read")
