#!/usr/bin/env bash
# Traegt ComicDesk ins Anwendungsmenue ein.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
target="$HOME/.local/share/applications/comicdesk.desktop"
mkdir -p "$(dirname "$target")"
sed "s|@PREFIX@|$here|" "$here/comicdesk.desktop.in" > "$target"
"$here/.venv/bin/python" -m comicdesk.appicon > /dev/null
command -v gtk-update-icon-cache >/dev/null && \
  gtk-update-icon-cache -q -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
command -v update-desktop-database >/dev/null && \
  update-desktop-database -q "$HOME/.local/share/applications" 2>/dev/null || true
echo "Eingetragen: $target"
echo "Symbole:     $HOME/.local/share/icons/hicolor/*/apps/comicdesk.png"
