"""Pull-request body and Actions job summary. No network calls."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

UNVERIFIED_NOTE = (
    "Inputs were manually supplied and were not verified by this workflow. "
    "The reviewer should check the title, thumbnail, and date."
)

_OEMBED_HINT = (
    "Confirm the title and thumbnail yourself with Rumble oEmbed "
    "(`https://wn0.rumble.com/api/Media/oembed.json?url=<watch URL>`, "
    "`author_name` should be `ferrouslion`) and the publish time from that "
    "response's embed page `pubDate` (`https://rumble.com/embed/<id>/`). "
    "This workflow does not call Rumble."
)


def _md(value: object) -> str:
    text = "" if value is None else str(value)
    return text.replace("`", "'").replace("\r", " ").replace("\n", " ")


def _item_lines(items: list) -> list[str]:
    lines = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            lines.append(f"{index}. (unreadable item)")
            continue
        title = _md(item.get("title") or "(untitled)")
        when = _md(item.get("publishedAt") or "")
        url = item.get("watchUrl") if isinstance(item.get("watchUrl"), str) else ""
        ident = _md(item.get("id") or "")
        url_text = f"<{url}>" if url else "(no URL)"
        lines.append(f"{index}. **{title}** (`{ident}`) — {when} — {url_text}")
    return lines


def render_change_sections(payload: dict) -> str:
    thumb = payload.get("thumbnail_display") or "fallback"
    duration = payload.get("duration_seconds")
    duration_text = "omitted" if duration is None else str(duration)
    removed = payload.get("removed") or []
    final = payload.get("final") or []
    removed_text = "None." if not removed else "\n".join(_item_lines(removed))
    count = len(final)
    heading = f"Final ordered list of {count}" if count else "Final ordered list"
    final_text = "\n".join(_item_lines(final)) if final else "None."
    return "\n".join(
        [
            "## Added VOD",
            "",
            f"- **Title:** {_md(payload.get('title'))}",
            f"- **Watch URL:** <{payload.get('watch_url')}>",
            f"- **Video id:** `{_md(payload.get('video_id'))}` "
            "(watch-URL id, stored in `id`; not the Rumble embed id)",
            f"- **Published (UTC):** {_md(payload.get('published_at_utc'))}",
            f"- **Published (America/Chicago):** {_md(payload.get('published_at_chicago'))}",
            f"- **Date note:** {_md(payload.get('published_at_note'))}",
            f"- **Thumbnail:** {_md(thumb)}",
            f"- **Duration:** {duration_text}",
            f"- **Metadata source:** `{_md(payload.get('source'))}`",
            "",
            "## Removed VOD(s)",
            "",
            removed_text,
            "",
            f"## {heading}",
            "",
            final_text,
            "",
        ]
    )


def render_pr_body(payload: dict) -> str:
    return "\n".join(
        [
            render_change_sections(payload).rstrip(),
            "",
            "## Reviewer note",
            "",
            UNVERIFIED_NOTE,
            "",
            _OEMBED_HINT,
            "",
            "Do not merge until those match. This pull request does not deploy the site.",
            "",
        ]
    )


def render_job_summary(
    payload: dict | None,
    *,
    pr_url: str = "",
    compare_url: str = "",
    pr_outcome: str = "",
    pr_error: str = "",
    check_outcome: str = "",
) -> str:
    parts = ["## Add New Rumble VOD", ""]
    if not payload:
        parts.extend(
            [
                "The workflow did not produce a result file. See the failed step log.",
                "",
                "No merge was attempted. This workflow does not push to `main`.",
                "",
            ]
        )
        return "\n".join(parts)

    if not payload.get("ok"):
        parts.extend(
            [
                "The gallery was not updated. `index.html` was left unchanged.",
                "",
                f"**Error:** {_md(payload.get('error') or 'unknown error')}",
                "",
                UNVERIFIED_NOTE,
                "",
                "No pull request was opened. Nothing was pushed to `main`. "
                "This workflow does not call Rumble.",
                "",
            ]
        )
        return "\n".join(parts)

    parts.append(render_change_sections(payload).rstrip())
    parts.append("")
    parts.append(UNVERIFIED_NOTE)
    parts.append("")
    parts.append("This workflow does not call Rumble, does not merge, and does not push to `main`.")
    parts.append("")

    if check_outcome == "failure":
        parts.extend(
            [
                "### Site check failed",
                "",
                "The updated block did not pass `check_site.py`, so no branch was pushed.",
                "",
            ]
        )
    elif pr_outcome == "success" and pr_url:
        parts.extend(["### Pull request", "", pr_url.strip(), ""])
    elif pr_outcome == "failure":
        parts.extend(
            [
                "### Pull request was not created",
                "",
                "The branch was pushed. `gh pr create` failed, so the pull request "
                "has to be opened from the compare URL if Actions is not allowed "
                "to open pull requests.",
                "",
            ]
        )
        if compare_url.strip():
            parts.extend(["Compare URL:", "", compare_url.strip(), ""])
        parts.extend(
            [
                "If the log says GitHub Actions cannot create pull requests, enable "
                "**Allow GitHub Actions to create and approve pull requests** under "
                "Settings → Actions → General → Workflow permissions, then re-run "
                "this workflow. Nothing was merged.",
                "",
            ]
        )
        if pr_error.strip():
            clipped = pr_error.strip()
            if len(clipped) > 2000:
                clipped = clipped[:2000] + "\n…"
            parts.extend(["```", clipped, "```", ""])
    elif pr_outcome == "skipped":
        parts.extend(
            [
                "### Pull request was not opened",
                "",
                "The pull-request step did not run.",
                "",
            ]
        )
    return "\n".join(parts)


def _read_optional(path: str) -> str:
    if not path:
        return ""
    file = Path(path)
    if not file.is_file():
        return ""
    return file.read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the Actions job summary for a Rumble VOD run.")
    parser.add_argument("--result", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--pr-url", default="")
    parser.add_argument("--compare-url", default="")
    parser.add_argument("--pr-outcome", default="")
    parser.add_argument("--check-outcome", default="")
    parser.add_argument("--pr-error-file", default="")
    parser.add_argument("--compare-file", default="")
    args = parser.parse_args(argv)

    result_path = Path(args.result)
    payload = None
    if result_path.is_file():
        try:
            loaded = json.loads(result_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            loaded = {"ok": False, "error": "result file was not valid JSON"}
        if isinstance(loaded, dict):
            payload = loaded
        else:
            payload = {"ok": False, "error": "result file was not a JSON object"}

    compare_url = args.compare_url.strip() or _read_optional(args.compare_file).strip()
    summary = render_job_summary(
        payload,
        pr_url=args.pr_url,
        compare_url=compare_url,
        pr_outcome=args.pr_outcome,
        pr_error=_read_optional(args.pr_error_file),
        check_outcome=args.check_outcome,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a", encoding="utf-8") as handle:
        handle.write(summary)
        if not summary.endswith("\n"):
            handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
