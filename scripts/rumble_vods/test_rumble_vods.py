"""Stdlib tests for the manual Rumble VOD updater. No network."""

from __future__ import annotations

import contextlib
import io
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.rumble_vods.add_vod import apply_to_html, main
from scripts.rumble_vods.check_site import check_html, check_index
from scripts.rumble_vods.html_block import locate_block, parse_block, write_block
from scripts.rumble_vods.merge import merge_items
from scripts.rumble_vods.metadata import (
    ManualInputSource,
    OfficialApiSource,
    VodRecord,
    get_source,
)
from scripts.rumble_vods.report import UNVERIFIED_NOTE, render_job_summary, render_pr_body
from scripts.rumble_vods.validate import (
    NOTE_CHICAGO,
    NOTE_FRACTION,
    NOTE_OFFSET,
    VodError,
    format_chicago,
    normalize_thumbnail,
    normalize_title,
    normalize_watch_url,
    parse_duration,
    parse_published_at,
    validate_record,
)

REPO_INDEX = Path(__file__).resolve().parents[2] / "index.html"
CLOCK = datetime(2026, 11, 13, 18, 0, tzinfo=timezone.utc)


def wrap(data: dict, *, indent: int = 2) -> str:
    body = json.dumps(data, indent=indent, ensure_ascii=False)
    return (
        "PREFIX\n"
        '<script type="application/json" id="featured-rumble-data">\n'
        f"{body}\n"
        "</script>\n"
        "SUFFIX\n"
    )


def item(ident: str, published: str, watch: str, **extra: object) -> dict:
    row = {
        "id": ident,
        "title": extra.pop("title", ident),
        "publishedAt": published,
        "watchUrl": watch,
    }
    row.update(extra)
    return row


def manual(
    url: str,
    *,
    title: str = "Sample Stream Night",
    published: str = "2026-11-12T18:30:00",
    thumbnail: str | None = None,
    duration: object = None,
) -> VodRecord:
    return ManualInputSource(url, title, published, thumbnail, duration).load()


class WatchUrlTests(unittest.TestCase):
    def test_canonical_url_and_video_id(self) -> None:
        video_id, url = normalize_watch_url(
            "https://rumble.com/v7hxibq-fortnite-treasure-hunting-with-ferrouscat.html"
        )
        self.assertEqual(video_id, "v7hxibq")
        self.assertEqual(
            url,
            "https://rumble.com/v7hxibq-fortnite-treasure-hunting-with-ferrouscat.html",
        )

    def test_strips_query_and_fragment(self) -> None:
        video_id, url = normalize_watch_url(
            "https://rumble.com/v7hxibq-fortnite-treasure-hunting-with-ferrouscat.html?x=1#t=10"
        )
        self.assertEqual(video_id, "v7hxibq")
        self.assertNotIn("?", url)
        self.assertNotIn("#", url)

    def test_lowercases_host_only(self) -> None:
        video_id, url = normalize_watch_url("https://Rumble.com/vAbC12-My-Slug.html")
        self.assertEqual(video_id, "vAbC12")
        self.assertTrue(url.startswith("https://rumble.com/"))

    def test_rejects_bad_urls(self) -> None:
        samples = [
            "http://rumble.com/v1-slug.html",
            "https://www.rumble.com/v1-slug.html",
            "https://rumble.com/v1.html",
            "https://rumble.com/1abc-slug.html",
            "https://example.com/v1-slug.html",
            "https://user:pass@rumble.com/v1-slug.html",
            "https://rumble.com/v1-slug.html/",
            "https://rumble.com:8443/v1-slug.html",
            "",
        ]
        for sample in samples:
            with self.subTest(sample=sample):
                with self.assertRaises(VodError):
                    normalize_watch_url(sample)


class PublishedAtTests(unittest.TestCase):
    def test_zulu_and_explicit_offset_convert_to_utc(self) -> None:
        zulu = parse_published_at("2026-11-13T00:30:00Z")
        plus = parse_published_at("2026-11-13T00:30:00+00:00")
        offset = parse_published_at("2026-11-12T18:30:00-06:00")
        lower = parse_published_at("2026-11-13t00:30:00z")
        for parsed in (zulu, plus, offset, lower):
            self.assertEqual(parsed.text, "2026-11-13T00:30:00+00:00")
            self.assertFalse(parsed.assumed_chicago)
            self.assertEqual(parsed.note, NOTE_OFFSET)

    def test_naive_chicago_standard_time(self) -> None:
        parsed = parse_published_at("2026-11-12T18:30:00")
        self.assertEqual(parsed.text, "2026-11-13T00:30:00+00:00")
        self.assertTrue(parsed.assumed_chicago)
        self.assertEqual(parsed.note, NOTE_CHICAGO)
        self.assertEqual(format_chicago(parsed.instant), "Nov 12, 2026, 6:30:00 PM CT")

    def test_naive_chicago_daylight_time(self) -> None:
        parsed = parse_published_at("2026-07-15T20:00:00")
        self.assertEqual(parsed.text, "2026-07-16T01:00:00+00:00")
        self.assertEqual(format_chicago(parsed.instant), "Jul 15, 2026, 8:00:00 PM CT")

    def test_fractional_seconds_are_truncated(self) -> None:
        parsed = parse_published_at("2026-11-13T00:30:00.9Z")
        self.assertEqual(parsed.text, "2026-11-13T00:30:00+00:00")
        self.assertIn(NOTE_FRACTION.strip(), parsed.note)

    def test_future_tolerance_is_five_minutes(self) -> None:
        now = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
        allowed = manual(
            "https://rumble.com/vfuture1-ok.html",
            published="2026-11-13T12:05:00Z",
        )
        blocked = manual(
            "https://rumble.com/vfuture2-no.html",
            published="2026-11-13T12:05:01Z",
        )
        validate_record(allowed, now=now)
        with self.assertRaises(VodError) as ctx:
            validate_record(blocked, now=now)
        self.assertIn("5 minutes", str(ctx.exception))

    def test_rejects_date_only_space_and_dst_gap(self) -> None:
        with self.assertRaises(VodError):
            parse_published_at("2026-11-13")
        with self.assertRaises(VodError) as spaced:
            parse_published_at("2026-11-13 00:30:00Z")
        self.assertIn("T", str(spaced.exception))
        with self.assertRaises(VodError) as gap:
            parse_published_at("2026-03-08T02:30:00")
        self.assertIn("daylight-saving", str(gap.exception))


class ThumbnailAndTitleTests(unittest.TestCase):
    def test_allowlisted_hosts_and_blank(self) -> None:
        self.assertEqual(
            normalize_thumbnail("https://Hugh.CDN.rumble.cloud/a.jpg#x"),
            "https://hugh.cdn.rumble.cloud/a.jpg",
        )
        self.assertEqual(
            normalize_thumbnail("https://sp.rmbl.ws/s8/image.jpg"),
            "https://sp.rmbl.ws/s8/image.jpg",
        )
        self.assertTrue(
            normalize_thumbnail("https://cdn.rumble.com/img.jpg").endswith("/img.jpg")
        )
        self.assertIsNone(normalize_thumbnail(""))
        self.assertIsNone(normalize_thumbnail(None))

    def test_rejects_lookalike_and_insecure_hosts(self) -> None:
        for sample in (
            "http://hugh.cdn.rumble.cloud/a.jpg",
            "https://evil.com/a.jpg",
            "https://rumble.cloud.attacker.com/a.jpg",
            "https://evilrumble.com/a.jpg",
            "https://cdn.rumble.com.evil.com/a.jpg",
            "https://user@hugh.cdn.rumble.cloud/a.jpg",
            "https://hugh.cdn.rumble.cloud",
        ):
            with self.subTest(sample=sample):
                with self.assertRaises(VodError):
                    normalize_thumbnail(sample)

    def test_title_and_duration_bounds(self) -> None:
        self.assertEqual(normalize_title("  Sample Stream Night  "), "Sample Stream Night")
        self.assertEqual(len(normalize_title("a" * 300)), 300)
        self.assertIsNone(parse_duration(""))
        self.assertIsNone(parse_duration(None))
        self.assertEqual(parse_duration("0"), 0)
        self.assertEqual(parse_duration(5709), 5709)
        for sample in ("", "   ", "a" * 301, "hello\nworld", "bad </script> tag"):
            with self.subTest(sample=sample):
                with self.assertRaises(VodError):
                    normalize_title(sample)
        for sample in ("-1", "1.5", "172801", 172801, True):
            with self.subTest(sample=sample):
                with self.assertRaises(VodError):
                    parse_duration(sample)


class MergeTests(unittest.TestCase):
    def test_sorts_and_trims_to_three(self) -> None:
        existing = [
            item("v3", "2026-11-03T00:00:00+00:00", "https://rumble.com/v3-three.html"),
            item("v2", "2026-11-02T00:00:00+00:00", "https://rumble.com/v2-two.html"),
            item("v1", "2026-11-01T00:00:00+00:00", "https://rumble.com/v1-one.html"),
        ]
        record = manual(
            "https://rumble.com/v4-four.html",
            published="2026-11-04T00:00:00Z",
        )
        merged = merge_items(existing, record)
        self.assertEqual([row["id"] for row in merged.kept], ["v4", "v3", "v2"])
        self.assertEqual([row["id"] for row in merged.removed], ["v1"])
        self.assertNotIn("durationSeconds", merged.added)
        self.assertNotIn("thumbnailUrl", merged.added)

    def test_keeps_all_when_fewer_than_three(self) -> None:
        existing = [
            item("v2", "2026-11-02T00:00:00+00:00", "https://rumble.com/v2-two.html"),
        ]
        record = manual(
            "https://rumble.com/v1-one.html",
            published="2026-11-01T00:00:00Z",
        )
        merged = merge_items(existing, record)
        self.assertEqual([row["id"] for row in merged.kept], ["v2", "v1"])
        self.assertEqual(merged.removed, [])
        self.assertEqual(merge_items([], record).kept, [merged.added])

    def test_equal_times_break_ties_by_id(self) -> None:
        stamp = "2026-11-04T00:00:00+00:00"
        existing = [
            item("vc", stamp, "https://rumble.com/vc-ccc.html"),
            item("vb", stamp, "https://rumble.com/vb-bbb.html"),
        ]
        record = manual("https://rumble.com/va-aaa.html", published=stamp)
        merged = merge_items(existing, record)
        self.assertEqual([row["id"] for row in merged.kept], ["va", "vb", "vc"])

    def test_rejects_watch_url_video_id_and_item_id_duplicates(self) -> None:
        existing = [
            item(
                "vembed1",
                "2026-11-06T01:20:57+00:00",
                "https://rumble.com/v7hxibq-fortnite-treasure-hunting-with-ferrouscat.html",
                title="Fortnite",
            )
        ]
        with self.assertRaises(VodError) as same_url:
            merge_items(
                existing,
                manual(
                    "https://rumble.com/v7hxibq-fortnite-treasure-hunting-with-ferrouscat.html?utm=1"
                ),
            )
        self.assertIn("duplicate: watch URL already in featured-rumble-data", str(same_url.exception))

        with self.assertRaises(VodError) as same_video:
            merge_items(existing, manual("https://rumble.com/v7hxibq-other-slug.html"))
        self.assertIn("duplicate: video id v7hxibq is already present on", str(same_video.exception))

        keyed = [
            item(
                "v7hxibq",
                "2026-11-01T00:00:00+00:00",
                "https://rumble.com/vother1-other.html",
                title="Other",
            )
        ]
        with self.assertRaises(VodError) as same_key:
            merge_items(keyed, manual("https://rumble.com/v7hxibq-new-slug.html"))
        self.assertIn("already present as an item id", str(same_key.exception))

    def test_rejects_a_video_that_would_not_be_shown(self) -> None:
        existing = [
            item("v3", "2026-11-03T00:00:00+00:00", "https://rumble.com/v3-three.html"),
            item("v2", "2026-11-02T00:00:00+00:00", "https://rumble.com/v2-two.html"),
            item("v1", "2026-11-01T00:00:00+00:00", "https://rumble.com/v1-one.html"),
        ]
        with self.assertRaises(VodError) as ctx:
            merge_items(
                existing,
                manual("https://rumble.com/v0-old.html", published="2020-01-01T00:00:00Z"),
            )
        self.assertIn("not among the three newest", str(ctx.exception))

    def test_duration_is_stored_when_provided(self) -> None:
        record = manual(
            "https://rumble.com/v9-nine.html",
            published="2026-11-09T00:00:00Z",
            thumbnail="https://hugh.cdn.rumble.cloud/video/sample.jpg",
            duration="5709",
        )
        merged = merge_items([], record)
        self.assertEqual(merged.added["durationSeconds"], 5709)
        self.assertEqual(
            merged.added["thumbnailUrl"],
            "https://hugh.cdn.rumble.cloud/video/sample.jpg",
        )
        self.assertEqual(merged.added["id"], "v9")


class BlockRewriteTests(unittest.TestCase):
    def test_real_index_round_trip(self) -> None:
        html = REPO_INDEX.read_text(encoding="utf-8")
        rewritten = write_block(html, parse_block(html))
        if rewritten != html:
            import difflib

            diff = "".join(
                difflib.unified_diff(
                    html.splitlines(keepends=True),
                    rewritten.splitlines(keepends=True),
                    n=1,
                )
            )
            self.fail(diff[:4000])

    def test_preserves_indent_and_surrounding_html(self) -> None:
        data = {
            "channelUrl": "https://rumble.com/user/ferrouslion",
            "updatedAt": "2026-01-01T00:00:00Z",
            "items": [
                item("v1", "2026-01-01T00:00:00+00:00", "https://rumble.com/v1-one.html")
            ],
        }
        html = wrap(data, indent=4)
        self.assertEqual(write_block(html, parse_block(html)), html)
        record = manual(
            "https://rumble.com/v2-two.html",
            published="2026-02-01T00:00:00Z",
        )
        updated, _merged = apply_to_html(html, record, CLOCK)
        self.assertTrue(updated.startswith("PREFIX\n"))
        self.assertTrue(updated.endswith("SUFFIX\n"))
        prefix, suffix = _outside(html)
        new_prefix, new_suffix = _outside(updated)
        self.assertEqual(prefix, new_prefix)
        self.assertEqual(suffix, new_suffix)
        self.assertIn('"id": "v2"', updated)
        self.assertNotIn("v2-two", html)

    def test_missing_and_duplicate_blocks(self) -> None:
        with self.assertRaises(VodError):
            parse_block("<html></html>")
        doubled = wrap({}) + wrap({})
        with self.assertRaises(VodError):
            parse_block(doubled)


class CheckSiteTests(unittest.TestCase):
    def test_real_index_passes(self) -> None:
        self.assertEqual(check_index(REPO_INDEX), [])

    def test_allows_embed_id_null_duration_and_one_item(self) -> None:
        data = _gallery(
            [
                item(
                    "vembed1",
                    "2026-11-01T00:00:00+00:00",
                    "https://rumble.com/vwatch01-slug.html",
                    title="Title",
                    durationSeconds=None,
                )
            ]
        )
        self.assertNotEqual(data["items"][0]["id"], "vwatch01")
        self.assertEqual(check_html(wrap(data)), [])

    def test_rejects_count_order_and_bad_url(self) -> None:
        four = _gallery(
            [
                item(f"v{i}", f"2026-11-0{i}T00:00:00+00:00", f"https://rumble.com/v{i}-item.html")
                for i in (1, 2, 3, 4)
            ]
        )
        self.assertTrue(any("1 to 3" in error for error in check_html(wrap(four))))
        unsorted = _gallery(
            [
                item("v1", "2026-11-01T00:00:00+00:00", "https://rumble.com/v1-one.html"),
                item("v2", "2026-11-02T00:00:00+00:00", "https://rumble.com/v2-two.html"),
            ]
        )
        self.assertTrue(any("sorted" in error for error in check_html(wrap(unsorted))))
        bad = _gallery(
            [
                item("v1", "2026-11-01T00:00:00+00:00", "https://example.com/v1-one.html"),
            ]
        )
        self.assertTrue(check_html(wrap(bad)))


class SourceTests(unittest.TestCase):
    def test_official_api_is_a_stub(self) -> None:
        with self.assertRaises(NotImplementedError) as ctx:
            OfficialApiSource().load()
        self.assertIn("does not call Rumble", str(ctx.exception))
        self.assertIsInstance(get_source("official_api"), OfficialApiSource)

    def test_manual_source_does_not_check_the_future(self) -> None:
        record = manual(
            "https://rumble.com/vfuture9-later.html",
            published="2999-01-01T00:00:00Z",
        )
        self.assertEqual(record.source, "manual_input")
        self.assertEqual(record.id, "vfuture9")
        with self.assertRaises(VodError):
            validate_record(record, now=CLOCK)

    def test_package_does_not_import_network_clients(self) -> None:
        banned = ("urllib.request", "http.client", "httpx", "requests", "aiohttp", "socket")
        root = Path(__file__).resolve().parent
        for path in root.glob("*.py"):
            if path.name.startswith("test_"):
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not (stripped.startswith("import ") or stripped.startswith("from ")):
                    continue
                for token in banned:
                    self.assertNotIn(token, stripped, f"{path.name}: {stripped}")


class CliTests(unittest.TestCase):
    def test_end_to_end_on_a_copy_of_index(self) -> None:
        import tempfile

        html = REPO_INDEX.read_text(encoding="utf-8")
        data = parse_block(html)
        newest = max(
            parse_time(row["publishedAt"]) for row in data["items"]
        )
        published = (newest + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        clock = (newest + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        video_id = _unused_video_id(data)
        with tempfile.TemporaryDirectory() as tmp:
            index = Path(tmp) / "index.html"
            result = Path(tmp) / "result.json"
            pr_dir = Path(tmp) / "pr"
            index.write_text(html, encoding="utf-8")
            before = index.read_text(encoding="utf-8")
            code = _run_main(
                [
                    "--index",
                    str(index),
                    "--video-url",
                    f"https://rumble.com/{video_id}-sample-stream-night.html?utm=test#chapter",
                    "--title",
                    "  Sample Stream Night  ",
                    "--published-at",
                    published,
                    "--thumbnail-url",
                    "https://hugh.cdn.rumble.cloud/video/sample.jpg",
                    "--result",
                    str(result),
                    "--write-pr-dir",
                    str(pr_dir),
                    "--now",
                    clock,
                ]
            )
            self.assertEqual(code, 0, result.read_text(encoding="utf-8") if result.exists() else "")
            after = index.read_text(encoding="utf-8")
            self.assertNotEqual(after, before)
            self.assertEqual(_outside(before), _outside(after))
            payload = json.loads(result.read_text(encoding="utf-8"))
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["video_id"], video_id)
            self.assertEqual(payload["title"], "Sample Stream Night")
            self.assertEqual(payload["final"][0]["id"], video_id)
            self.assertNotIn("durationSeconds", payload["added"])
            self.assertIn(NOTE_OFFSET, payload["published_at_note"])
            self.assertIn(UNVERIFIED_NOTE, payload["pr_body"])
            self.assertIn("hugh.cdn.rumble.cloud", payload["pr_body"])
            self.assertEqual(check_html(after), [])
            self.assertEqual((pr_dir / "video-id.txt").read_text(encoding="utf-8").strip(), video_id)

            duplicate = Path(tmp) / "duplicate.json"
            duplicate_before = after
            code = _run_main(
                [
                    "--index",
                    str(index),
                    "--video-url",
                    f"https://rumble.com/{video_id}-sample-stream-night.html",
                    "--title",
                    "Sample Stream Night",
                    "--published-at",
                    published,
                    "--result",
                    str(duplicate),
                    "--now",
                    clock,
                ]
            )
            self.assertEqual(code, 1)
            self.assertEqual(index.read_text(encoding="utf-8"), duplicate_before)
            self.assertIn("duplicate", json.loads(duplicate.read_text(encoding="utf-8"))["error"])

            nulled = parse_block(after)
            nulled["items"][0]["durationSeconds"] = None
            nulled_html = write_block(after, nulled)
            self.assertEqual(check_html(nulled_html), [])
            self.assertIn('"durationSeconds": null', nulled_html)

    def test_failures_do_not_write_index(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            index = Path(tmp) / "index.html"
            index.write_text(REPO_INDEX.read_text(encoding="utf-8"), encoding="utf-8")
            original = index.read_text(encoding="utf-8")
            result = Path(tmp) / "result.json"
            code = _run_main(
                [
                    "--index",
                    str(index),
                    "--video-url",
                    "https://rumble.com/v0oldvid-too-old.html",
                    "--title",
                    "Too old",
                    "--published-at",
                    "2020-01-01T00:00:00Z",
                    "--result",
                    str(result),
                    "--now",
                    "2026-11-13T18:00:00Z",
                ]
            )
            self.assertEqual(code, 1)
            self.assertIn("not among the three newest", result.read_text(encoding="utf-8"))
            self.assertEqual(index.read_text(encoding="utf-8"), original)

            missing = Path(tmp) / "missing.html"
            code = _run_main(
                [
                    "--index",
                    str(missing),
                    "--video-url",
                    "https://rumble.com/v1-slug.html",
                    "--title",
                    "Title",
                    "--published-at",
                    "2026-11-01T00:00:00Z",
                    "--source",
                    "official_api",
                    "--result",
                    str(result),
                ]
            )
            self.assertEqual(code, 1)
            self.assertIn("does not call Rumble", result.read_text(encoding="utf-8"))
            self.assertFalse(missing.exists())

    def test_summary_covers_success_and_blocked_pr(self) -> None:
        payload = {
            "ok": True,
            "source": "manual_input",
            "video_id": "v1",
            "title": "Sample",
            "watch_url": "https://rumble.com/v1-sample.html",
            "published_at_utc": "2026-11-13T00:30:00+00:00",
            "published_at_chicago": "Nov 12, 2026, 6:30:00 PM CT",
            "published_at_note": NOTE_CHICAGO,
            "thumbnail_display": "fallback",
            "duration_seconds": None,
            "removed": [],
            "final": [
                item("v1", "2026-11-13T00:30:00+00:00", "https://rumble.com/v1-sample.html", title="Sample")
            ],
        }
        body = render_pr_body(payload)
        self.assertIn("fallback", body)
        self.assertIn(UNVERIFIED_NOTE, body)
        self.assertIn("America/Chicago", body)
        self.assertIn("None.", body)
        summary = render_job_summary(
            payload,
            compare_url="https://github.com/example/repo/compare/main...rumble-vod/v1-1?expand=1",
            pr_outcome="failure",
            pr_error="GitHub Actions is not permitted to create or approve pull requests",
        )
        self.assertIn("Compare URL:", summary)
        self.assertIn("Allow GitHub Actions to create and approve pull requests", summary)
        self.assertIn("not permitted", summary)
        failed = render_job_summary({"ok": False, "error": "duplicate: watch URL"})
        self.assertIn("left unchanged", failed)
        self.assertIn("duplicate: watch URL", failed)


def _run_main(argv: list[str]) -> int:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return main(argv)


def _gallery(items: list[dict]) -> dict:
    return {
        "channelUrl": "https://rumble.com/user/ferrouslion",
        "updatedAt": "2026-11-13T00:00:00Z",
        "items": items,
    }


def _outside(html: str) -> tuple[str, str]:
    content_start, content_end = locate_block(html)
    return html[:content_start], html[content_end:]


def parse_time(value: str) -> datetime:
    from scripts.rumble_vods.validate import parse_stored_published_at

    return parse_stored_published_at(value)


def _unused_video_id(data: dict) -> str:
    taken = set()
    for row in data["items"]:
        taken.add(str(row.get("id", "")).casefold())
        try:
            video_id, _url = normalize_watch_url(row["watchUrl"])
        except VodError:
            continue
        taken.add(video_id.casefold())
    for candidate in ("vtestvod1", "vtestvod2", "vtestvod3"):
        if candidate not in taken:
            return candidate
    raise AssertionError("fixture video ids are all in use")


if __name__ == "__main__":
    unittest.main()
