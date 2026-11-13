"""Manual Rumble VOD edits for the inline ``#featured-rumble-data`` block.

Pipeline, with no network calls:

1. ``metadata`` builds one normalized record (``manual_input`` today).
2. ``validate`` checks that record.
3. ``merge`` rejects duplicates, sorts by ``publishedAt``, and keeps three.
4. ``html_block`` rewrites only the JSON inside the existing script tag.

``official_api`` is a stub for a later authorized Rumble API or feed.
"""
