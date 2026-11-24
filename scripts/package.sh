#!/usr/bin/env bash
# Construit une archive .plasmoid installable via kpackagetool6 / KDE Store.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(python3 -c 'import json,sys;print(json.load(open("'"$ROOT"'/plasmoid/metadata.json"))["KPlugin"]["Version"])')"
OUT_DIR="$ROOT/dist"
OUT="$OUT_DIR/opencode-meter-$VERSION.plasmoid"

mkdir -p "$OUT_DIR"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cp -a "$ROOT/plasmoid/." "$TMP/"
# Chemins standards (ceux produits par install.sh). Pour une installation
# non standard, régénérer via install.sh.
sed -e "s|@USAGE_FILE@|$HOME/.cache/opencode-meter/usage.json|g" \
    -e "s|@REFRESH_COMMAND@|$HOME/.local/bin/opencode-meter --quiet|g" \
    "$ROOT/plasmoid/contents/ui/paths.js.template" > "$TMP/contents/ui/paths.js"
rm -f "$TMP/contents/ui/paths.js.template"

cd "$TMP"
zip -qr "$OUT" . -x '*.DS_Store'
echo "Built $OUT"