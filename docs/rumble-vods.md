# Rumble VOD gallery

The homepage block “Latest from FerrousLion” is a hand-edited list. The page does not call Rumble, load a Rumble player, or run a feed job.

Automated discovery stays off until Rumble documents an official feed or API, or gives written permission to fetch one. Do not add a scraper, a scheduled workflow, or a client for Rumble endpoints.

## Update the videos

1. Open https://rumble.com/user/ferrouslion and choose the newest completed VODs. Skip anything still live.
2. Copy each canonical watch URL (`https://rumble.com/v….html`).
3. Look up oEmbed by hand (this is not something the site does):

   `https://wn0.rumble.com/api/Media/oembed.json?url=<watch URL>`

   Use `title`, `thumbnail_url`, and `author_name` (expect `ferrouslion`). `duration` may be copied to `durationSeconds`. The `html` field is only a hint for the embed id; do not put an embed URL in the data.
4. For `publishedAt`, open the public embed page from that oEmbed response (`https://rumble.com/embed/<id>/`) and copy `pubDate`. It must be ISO 8601 with an explicit timezone (`Z` or `±hh:mm`). The watch page often returns Cloudflare 403 to scripts. Do not bypass that. If you cannot verify a field, leave it out.
5. Edit only the JSON in `index.html` (`#featured-rumble-data`). Keep the newest three verified videos. Fewer is fine when you cannot verify more. Set `updatedAt` to the time you edited the block, with a timezone. No HTML, CSS, or JS change is required for a normal swap.
6. The page sorts by `publishedAt`, newest first, and shows at most three valid records. Fewer valid records means fewer cards. None means a short empty state plus the channel link.

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

- `id`: Rumble embed id, non-empty. The site uses it as a stable key. It is not turned into a player.
- `title`: non-empty. This is the card name.
- `publishedAt`: required. Must parse, and must end in `Z` or `±hh:mm`. Dates render in America/Chicago, for example `Nov 5, 2026`.
- `watchUrl`: required. `https` and host `rumble.com` only.
- `thumbnailUrl`: optional. If present, it must be `https`. A missing or failed image uses the crest placeholder.
- `durationSeconds`: optional non-negative number. Stored for the next edit; the card does not show it.
- `channelUrl`: `https` on `rumble.com`. “View all videos” and the empty-state “Visit Rumble channel” link use it.

Records that fail those checks are dropped. Card text is set with `textContent` and attributes, not `innerHTML`.
