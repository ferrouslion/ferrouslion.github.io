"""Insert one manually supplied Rumble VOD into ``index.html``.

The command does not contact Rumble or any other host. It reads workflow
inputs, validates them, and rewrites the ``featured-rumble-data`` block.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from scripts.rumble_vods.html_block import parse_block, write_block
from scripts.rumble_vods.merge import merge_items
from scripts.rumble_vods.metadata import VodRecord, get_source
from scripts.rumble_vods.report import render_pr_body
from scripts.rumble_vods.validate import (
    VodError,
    format_chicago,
    format_updated_at,
    is_https_rumble,
    parse_published_at,
    validate_record,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Add one manually supplied Rumble VOD to the featured-rumble-data "
            "block. Makes no network calls."
        )
    )
    parser.add_argument("--index", required=True, help="Path to index.html")
    parser.add_argument("--video-url", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--published-at", required=True)
    parser.add_argument("--thumbnail-url", default="")
    parser.add_argument("--duration-seconds", default="")
    parser.add_argument("--result", required=True, help="Path for the JSON result")
    parser.add_argument(
        "--write-pr-dir",
        help="Directory for pr-body.md, pr-title.txt, commit-message.txt, and video-id.txt",
    )
    parser.add_argument(
        "--source",
        default="manual_input",
        choices=("manual_input", "official_api"),
        help="official_api is a stub and raises NotImplementedError",
    )
    parser.add_argument(
        "--now",
        help="Override the clock (ISO 8601 with Z or an explicit offset). Tests only.",
    )
    return parser


def parse_clock(value: str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    try:
        parsed = parse_published_at(value)
    except VodError as exc:
        raise VodError(f"--now: {exc}") from exc
    if parsed.assumed_chicago:
        raise VodError("--now must include an explicit offset or Z")
    return parsed.instant


def apply_to_html(html: str, record: VodRecord, now: datetime) -> tuple[str, object]:
    data = parse_block(html)
    if not is_https_rumble(data.get("channelUrl")):
        raise VodError("channelUrl must be an https://rumble.com URL")
    items = data.get("items")
    if not isinstance(items, list):
        raise VodError("featured-rumble-data items must be a list")
    merged = merge_items(items, record)
    if "updatedAt" in data:
        data["updatedAt"] = format_updated_at(now)
        data["items"] = merged.kept
        updated = data
    else:
        updated = {}
        if "channelUrl" in data:
            updated["channelUrl"] = data["channelUrl"]
        updated["updatedAt"] = format_updated_at(now)
        for key, value in data.items():
            if key not in updated and key != "items":
                updated[key] = value
        updated["items"] = merged.kept
    return write_block(html, updated), merged


def _pr_title(record: VodRecord) -> str:
    prefix = "Add Rumble VOD: "
    text = prefix + record.title.replace("\n", " ").strip()
    if len(text) > 120:
        text = text[:117].rstrip() + "..."
    return text


def _commit_message(record: VodRecord) -> str:
    return (
        f"Add Rumble VOD {record.id}\n\n"
        "Manually supplied inputs. Not verified against Rumble.\n"
    )


def build_payload(record: VodRecord, merged: object) -> dict:
    from scripts.rumble_vods.merge import MergeResult

    if not isinstance(merged, MergeResult):
        raise VodError("merge did not return a result")
    payload = {
        "ok": True,
        "changed": True,
        "source": record.source,
        "video_id": record.id,
        "title": record.title,
        "watch_url": record.watch_url,
        "published_at_utc": record.published_at_text,
        "published_at_chicago": format_chicago(record.published_at),
        "published_at_note": record.published_at_note,
        "thumbnail_url": record.thumbnail_url,
        "thumbnail_display": record.thumbnail_url or "fallback",
        "duration_seconds": record.duration_seconds,
        "added": merged.added,
        "removed": merged.removed,
        "final": merged.kept,
    }
    payload["pr_title"] = _pr_title(record)
    payload["pr_body"] = render_pr_body(payload)
    payload["commit_message"] = _commit_message(record)
    return payload


def run(args: argparse.Namespace) -> dict:
    now = parse_clock(args.now)
    source = get_source(
        args.source,
        video_url=args.video_url,
        title=args.title,
        published_at=args.published_at,
        thumbnail_url=args.thumbnail_url,
        duration_seconds=args.duration_seconds,
    )
    record = source.load()
    validate_record(record, now=now)
    index_path = Path(args.index)
    html = index_path.read_text(encoding="utf-8")
    updated, merged = apply_to_html(html, record, now)
    if updated == html:
        raise VodError("update produced no change; refusing to continue")
    index_path.write_text(updated, encoding="utf-8")
    return build_payload(record, merged)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_pr_dir(directory: Path, payload: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "pr-body.md").write_text(payload["pr_body"], encoding="utf-8")
    (directory / "pr-title.txt").write_text(payload["pr_title"] + "\n", encoding="utf-8")
    (directory / "commit-message.txt").write_text(payload["commit_message"], encoding="utf-8")
    (directory / "video-id.txt").write_text(payload["video_id"] + "\n", encoding="utf-8")


def _set_output(**values: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            if "\n" in value or "\r" in value:
                raise VodError(f"refusing to write multiline workflow output {key}")
            handle.write(f"{key}={value}\n")


def _fail(result_path: Path, source: str, message: str) -> int:
    _write_json(
        result_path,
        {"ok": False, "changed": False, "error": message, "source": source},
    )
    _set_output(changed="false")
    print(f"error: {message}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result_path = Path(args.result)
    try:
        payload = run(args)
    except NotImplementedError as exc:
        return _fail(result_path, args.source, str(exc))
    except VodError as exc:
        return _fail(result_path, args.source, str(exc))
    _write_json(result_path, payload)
    if args.write_pr_dir:
        _write_pr_dir(Path(args.write_pr_dir), payload)
    _set_output(changed="true", video_id=payload["video_id"])
    print(
        f"added {payload['video_id']}: kept {len(payload['final'])}, "
        f"removed {len(payload['removed'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
