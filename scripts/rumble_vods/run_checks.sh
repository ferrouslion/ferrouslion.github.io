#!/usr/bin/env bash
# Unit tests and the featured-rumble-data site check.
# This static site has no package.json and no production build.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
python3 -m unittest scripts.rumble_vods.test_rumble_vods -v
python3 -m scripts.rumble_vods.check_site --index "$ROOT/index.html"
