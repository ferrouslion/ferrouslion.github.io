# Rumble VOD gallery

The homepage block “Latest from FerrousLion” is a short list in `index.html`, inside `<script type="application/json" id="featured-rumble-data">`. The Videos item in the header scrolls to it (`#videos`). The page does not call Rumble, load a Rumble player, or run a feed job.

There is no `rumble-vods.json`. The list stays in that inline block so the static page can render it without a fetch.

Automated discovery stays off until Rumble documents an official feed or API, or gives written permission to fetch one. Do not add a scraper, a scheduled fetch, or a client that calls Rumble. The **Add New Rumble VOD** workflow is manual: it only writes values a person types in, and it does not contact Rumble.

## Update the videos by hand

1. Open https://rumble.com/user/ferrouslion and choose the newest completed VODs. Skip anything still live.
2. Copy each canonical watch URL (`https://rumble.com/v….html`).
3. Look up oEmbed by hand (the site and the workflow do not do this):

   `https://wn0.rumble.com/api/Media/oembed.json?url=<watch URL>`

   Use `title`, `thumbnail_url`, and `author_name` (expect `ferrouslion`). `duration` may be copied to `durationSeconds`. The `html` field is only a hint for the embed id; do not put an embed URL in the data.
4. For `publishedAt`, open the public embed page from that oEmbed response (`https://rumble.com/embed/<id>/`) and copy `pubDate`. It must be ISO 8601 with an explicit timezone (`Z` or `±hh:mm`). The watch page often returns Cloudflare 403 to scripts. Do not bypass that. If you cannot verify a field, leave it out.
5. Edit only the JSON in `index.html` (`#featured-rumble-data`). Keep the newest three verified videos. Fewer is fine when you cannot verify more. Set `updatedAt` to the time you edited the block, with a timezone. No HTML, CSS, or JS change is required for a normal swap.
6. The page sorts by `publishedAt`, newest first, and shows at most three valid records. Fewer valid records means fewer cards. None means a short empty state plus the channel link.

## Add one video from Actions

Use this when you already have the title, date, and optional thumbnail from the checks above.

1. On GitHub, open the **Actions** tab.
2. Choose **Add New Rumble VOD**.
3. Choose **Run workflow**. The workflow checks out `main` itself. Leave the branch selector alone.
4. Fill in the inputs and run it.

The workflow validates the inputs, keeps the three newest videos, and opens a pull request. It does not merge, push to `main`, or deploy. Review the pull request before merging. The inputs are not checked against Rumble.

### Inputs

| Input | Required | Meaning |
| --- | --- | --- |
| `video_url` | yes | `https://rumble.com/<videoId>-<slug>.html`. `videoId` is `v` plus letters and digits. A query string or fragment is removed. |
| `title` | yes | Card title, 1–300 characters, after trimming. No control characters. |
| `published_at` | yes | ISO 8601 date and time. See the formats below. |
| `thumbnail_url` | no | `https` URL on `rumble.cloud`, `rmbl.ws`, `rumble.com`, or a subdomain of those. Empty means the crest placeholder. |
| `duration_seconds` | no | Whole seconds from 0 through 48 hours. The card does not show it. Empty omits the field. |

`published_at` must include seconds and a `T` between the date and the time:

- `2026-11-13T00:30:00Z`
- `2026-11-12T18:30:00-06:00` (any explicit `±hh:mm` offset)
- `2026-11-13T00:30:00.250Z` (fractional seconds are accepted, then truncated, not rounded)
- `2026-11-12T18:30:00` with **no offset** is interpreted as America/Chicago, including daylight-saving time, and converted to UTC. The pull request says that this assumption was used.

A date with no time is rejected. A local time that falls in a daylight-saving gap is rejected; send an explicit offset for that hour. An ambiguous local time (the repeated hour when clocks fall back) uses the first offset. Send an explicit offset if you need the other one. Times more than 5 minutes in the future are rejected. The stored `publishedAt` is UTC with a `+00:00` offset. `updatedAt` is written in UTC with a `Z` suffix.

If the watch URL or the watch-URL video id is already in the block, the run fails. An item whose `id` equals that video id also counts as a duplicate, so a second run cannot reuse a key. If the new video is older than three newer ones, the run fails and does not open a pull request. The file is left unchanged when validation fails.

### Verify the inputs yourself

Do this before you run the workflow, and again when you review the pull request. The workflow will not do it.

- Title and thumbnail: the oEmbed URL in the hand-edit steps. `author_name` should be `ferrouslion`.
- Date: open `https://rumble.com/embed/<embed id>/` from that oEmbed `html` and copy `pubDate`.
- Thumbnail host should be a Rumble CDN (`*.rumble.cloud`, `*.rmbl.ws`, or `*.rumble.com`). If you leave the thumbnail empty, the card uses the crest (`is-fallback` in `site.js`). A thumbnail that later fails to load does the same.
- `duration_seconds` is optional. `site.js` keeps a non-negative `durationSeconds` and drops the whole card if the field is present and not a usable number. The card never displays it. Leaving the input empty omits the field. A JSON `null` is also ignored, and the card still renders.

### Pull request

The workflow pushes `rumble-vod/<videoId>-<run id>` and opens a pull request into `main` as `github-actions[bot]`. The body lists the added video (title, URL, UTC and America/Chicago times, thumbnail or `fallback`), any removed video, and the final order. It also says the inputs were typed in and not verified.

The workflow file sets `contents: write` and `pull-requests: write`. Opening the pull request also needs this repository setting:

**Settings → Actions → General → Workflow permissions → Allow GitHub Actions to create and approve pull requests.**

If that setting is off, the job still pushes the branch, writes the compare URL into the step summary, and fails with an explicit error. It does not stop after a silent `gh` failure. Nothing is merged.

### `id` on new rows

`site.js` requires `id` to be a non-empty string. It uses that string as a stable key and as a tie-break when two `publishedAt` values match. The card does not read `id`, and the page does not build an embed URL from it.

Hand-edited rows use the Rumble embed id from oEmbed. That id is not the video id in the watch URL (for example embed `v7fr5e8` and watch `v7hxibq` are the same video). The embed id cannot be derived from the watch URL without calling Rumble, and this workflow does not call Rumble.

Rows added by the workflow store the watch-URL video id in `id`. Both forms are valid keys. There is no embed-id input.

## Checks

This site has no `package.json`, no frontend test runner, and no production build. GitHub Pages serves the files as they are.

`scripts/rumble_vods/run_checks.sh` runs the standard-library unit tests and `check_site.py`. The **Rumble VOD checks** workflow runs that script on pull requests that change `index.html`, `scripts/`, or the Rumble workflow files. `check_site.py` parses the block, requires 1–3 items with `id`, `title`, `publishedAt`, and a canonical `watchUrl`, checks that URLs are `https`, and requires newest-first order. A thumbnail only has to be `https` to match the page. The add workflow additionally restricts thumbnail hosts to Rumble CDNs. `durationSeconds` may be missing, `null`, or a non-negative number.

## Future: official API

`scripts/rumble_vods/metadata.py` defines `MetadataSource`. The workflow uses `manual_input`.

`OfficialApiSource` is a stub and raises `NotImplementedError`. When Rumble documents an official API or feed, or gives written permission, implement `load` so it returns the same normalized record. Leave validation, the three-item merge, and the HTML writer as they are. Do not scrape the channel page, call oEmbed from the workflow, or bypass Cloudflare.

## Schema

```json
{
  "channelUrl": "https://rumble.com/user/ferrouslion",
  "updatedAt": "2026-11-12T14:16:40Z",
  "items": [
    {
      "id": "v7fr5e8",
      "title": "Video title",
      "publishedAt": "2026-11-06T01:20:57+00:00",
      "watchUrl": "https://rumble.com/v7hxibq-fortnite-treasure-hunting-with-ferrouscat.html",
      "thumbnailUrl": "https://hugh.cdn.rumble.cloud/video/fwe2/47/s8/1/g/G/G/b/gGGbB.qR4e-small-Fortnite-Treasure-Hunting-w..jpg",
      "durationSeconds": 5709
    }
  ]
}
```

The example `id` is an embed id. It intentionally does not match `v7hxibq` in the watch URL. Workflow-added rows put `v7hxibq` in `id` instead.

- `id`: non-empty. Stable key and sort tie-break. Not a player.
- `title`: non-empty. This is the card name.
- `publishedAt`: required. Must parse, and must end in `Z` or `±hh:mm`. Dates render in America/Chicago, for example `Nov 5, 2026`.
- `watchUrl`: required. `https` and host `rumble.com` only. The workflow only accepts the canonical `/<videoId>-<slug>.html` path.
- `thumbnailUrl`: optional. If present, it must be `https`. A missing or failed image uses the crest placeholder. The workflow also requires a Rumble CDN host.
- `durationSeconds`: optional non-negative number, or `null`. Stored for the next edit; the card does not show it. `null` and a missing field both leave the card up.
- `channelUrl`: `https` on `rumble.com`. “View all videos” and the empty-state “Visit Rumble channel” link use it.

Records that fail those checks are dropped. Card text is set with `textContent` and attributes, not `innerHTML`.
