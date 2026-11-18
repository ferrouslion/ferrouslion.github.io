#!/usr/bin/env bash
# Unit tests and the music catalog check.
# This static site has no package.json and no production build.
# pip install of the pinned jsonschema release is the only network used here.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
python3 -m pip install --disable-pip-version-check --no-input -q -r scripts/music_catalog/requirements.txt
python3 -m unittest scripts.music_catalog.test_music_catalog -v
if [[ -f music/catalog.json ]]; then
  python3 -m scripts.music_catalog.validate --catalog music/catalog.json --role production
fi
