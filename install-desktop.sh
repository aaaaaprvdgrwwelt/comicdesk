#!/usr/bin/env bash
# Traegt ComicDesk ins Anwendungsmenue ein.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
target="$HOME/.local/share/applications/comicdesk.desktop"
mkdir -p "$(dirname "$target")"
sed "s|@PREFIX@|$here|" "$here/comicdesk.desktop.in" > "$target"
echo "Eingetragen: $target"
