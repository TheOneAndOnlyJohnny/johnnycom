#!/usr/bin/env bash
# Build the site and put exactly the files to upload in deploy/.
#
# Usage:  ./tools/deploy.sh
# Then upload the *contents* of deploy/ to the web root (it includes .htaccess).
# Uploading doesn't delete anything on the server: remove retired files there by hand.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/deploy"
PYTHON="${PYTHON:-python3}"
FILES=(
  .htaccess index.html es/index.html sitemap.xml robots.txt
  content/en.yaml content/es.yaml
  og-en.png og-es.png favicon.ico favicon.svg apple-touch-icon.png
  img/projects/finsanity-640.webp img/projects/finsanity-1280.webp img/projects/finsanity-1280.jpg
  img/projects/juanderful-640.webp img/projects/juanderful-1280.webp img/projects/juanderful-1280.jpg
)

cd "$ROOT"
rm -rf "$OUT"  # never leave a stale folder behind, even if the build fails

"$PYTHON" tools/build_seo.py

for file in "${FILES[@]}"; do
  if [[ ! -f "$file" ]]; then
    echo "✗ missing $file; nothing to deploy" >&2
    rm -rf "$OUT"
    exit 1
  fi
  mkdir -p "$OUT/$(dirname "$file")"
  cp "$file" "$OUT/$file"
done

echo "✓ deploy/ is ready (${#FILES[@]} files). Upload its contents to the web root:"
(cd "$OUT" && find . -type f | sed 's|^\./|  |' | sort)
