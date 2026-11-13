# Suno music

The homepage block “Albums and songs” is a hand-edited list. The Music item in the header scrolls to it (`#music`). The page does not call Suno, load a Suno player, or run a feed job.

Do not add a scraper, an oEmbed call, a proxy, or a client fetch to `suno.com`. Automated discovery stays off. Cover art is a file committed in this repo. Do not hotlink a Suno image.

## Add a song or an album

1. Open `index.html` and edit only the JSON in `#suno-music-data`.
2. Copy an item in `items` and fill the fields below. Order in the array is the order on the page.
3. For cover art, commit a file FerrousLion supplies. Photos on this site are JPEG (see `games/` and the page images). Brand marks are PNG. The site does not use WebP, so prefer `.jpg`. Put the file in `music/` with a lowercase hyphenated name, for example `music/forged-not-born.jpg`. The current album cover is a 600×600 JPEG. Match that size when you can, because the card sets `width="600"` and `height="600"`.
4. Set `artUrl` to a same-site path such as `./music/forged-not-born.jpg`, and set `alt` to a short description of that image.
5. Set `updatedAt` to the time you edited the block, with a timezone. No HTML, CSS, or JS change is required for a normal addition.

A missing `artUrl`, an `artUrl` the page will not accept, or an image that fails to load uses the styled placeholder: a gradient tile, a music note, and initials from the title. That placeholder is drawn in the page. It is not an external asset.

An empty `items` array, or a list with no valid records, shows “No music to show yet.” If `profileUrl` is a valid Suno https URL, the empty state also links to that profile.

## Schema

```json
{
  "profileUrl": null,
  "updatedAt": "2026-11-13T02:20:00Z",
  "items": [
    {
      "id": "UaKR3kLXhf8arBJf",
      "title": "Forged, Not Born",
      "type": "album",
      "url": "https://suno.com/s/UaKR3kLXhf8arBJf",
      "artUrl": "./music/forged-not-born.jpg",
      "alt": "Forged, Not Born album cover by FerrousLion",
      "note": "Optional short line under the title."
    }
  ]
}
```

- `profileUrl`: optional. `null`, omit it, or use an `https` URL on `suno.com` or `www.suno.com`. A valid URL adds a “Suno profile” link and the empty-state profile link. Anything else is ignored.
- `updatedAt`: when the block was edited, with a timezone. The page does not display it.
- `id`: non-empty stable key. The share id from the Suno URL is a good choice. The page does not turn it into a request.
- `title`: non-empty. This is the card name.
- `type`: `album` or `song`.
- `url`: required. `https` and host `suno.com` or `www.suno.com` only. The card opens this page in a new tab (`rel="noopener noreferrer"`). The accessible name says that it opens Suno in a new tab.
- `artUrl`: optional. A same-site path starting with `./` or `/`, ending in `.jpg`, `.jpeg`, `.png`, or `.webp`, with no `..` and no host. External URLs are ignored so the page cannot hotlink. `null` or a missing field means the placeholder.
- `alt`: optional text, and the text to use whenever `artUrl` is set. It becomes the image `alt`. Example: `Forged, Not Born album cover by FerrousLion`. If art is shown and `alt` is blank, the renderer uses the title followed by “ cover”.
- `note`: optional short line on the card.

Records that fail the checks on `id`, `title`, `type`, or `url` are dropped. Card text is set with `textContent` and attributes, not `innerHTML`. The image uses `loading="lazy"`, `width="600"`, and `height="600"`.
