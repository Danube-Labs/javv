#!/usr/bin/env bash
# Renders the videos from the screenshots of record.sh, then encodes each one for the docs site
# into docs/use/videos/. With no argument, all six; else the numbers given (render.sh 3 5).
set -euo pipefail
# shellcheck source=SCRIPTDIR/stack/env.sh
source "$(dirname "$0")/stack/env.sh"
cd "$VIDEO_DIR"

# the app's fonts and icon, not copies kept here
mkdir -p public/fonts out
for f in hanken-grotesk-latin-{400,500,600,700}-normal spline-sans-mono-latin-{400,700}-normal; do
  family=${f%%-latin-*}
  cp "$REPO/frontend/node_modules/@fontsource/$family/files/$f.woff2" public/fonts/
done
cp "$REPO/frontend/src/assets/brand/icon.svg" public/icon.svg
[ -d node_modules ] || npm ci

names=(from-a-scan-to-a-finding set-the-state-of-a-finding accept-a-risk change-many-findings
  when-a-scanner-stops who-changed-what)
for n in "${@:-1 2 3 4 5 6}"; do
  for v in $n; do
    npx remotion render src/index.ts "V$v" "out/V$v.mp4" --codec=h264 --crf=20 --log=error
    # for the web: full width, more compression (text stays sharp at crf 28), no sound track,
    # and the index at the start so a page can play it before it all loads
    ffmpeg -nostdin -loglevel error -y -i "out/V$v.mp4" -c:v libx264 -preset slow -crf 28 \
      -pix_fmt yuv420p -an -movflags +faststart "$REPO/docs/use/videos/${names[$((v - 1))]}.mp4"
    echo "video $v: docs/use/videos/${names[$((v - 1))]}.mp4"
  done
done
