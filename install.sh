#!/usr/bin/env bash
# Installe OpenCode Meter : collecteur, unités systemd --user, plasmoid KDE.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$HOME/.local/lib/opencode-meter"
BIN="$HOME/.local/bin/opencode-meter"
CACHE_DIR="$HOME/.cache/opencode-meter"
UNIT_DIR="$HOME/.config/systemd/user"
PLASMOID_ID="io.github.mattia.opencodemeter"

say() { printf '\033[1m==>\033[0m %s\n' "$*"; }

say "Collecteur → $APP_DIR"
mkdir -p "$APP_DIR" "$HOME/.local/bin" "$CACHE_DIR"
install -m 0755 "$SRC/collector/collect.py" "$APP_DIR/collect.py"

cat > "$BIN" <<EOF
#!/bin/sh
exec /usr/bin/python3 "$APP_DIR/collect.py" "\$@"
EOF
chmod 0755 "$BIN"

say "Unités systemd --user"
mkdir -p "$UNIT_DIR"
sed "s|@APP_DIR@|$APP_DIR|g" "$SRC/systemd/opencode-meter.service" > "$UNIT_DIR/opencode-meter.service"
install -m 0644 "$SRC/systemd/opencode-meter.timer" "$UNIT_DIR/opencode-meter.timer"
systemctl --user daemon-reload
systemctl --user enable --now opencode-meter.timer

say "Premier relevé"
"$BIN" --quiet || true

say "Plasmoid"
TMP_PLASMOID="$(mktemp -d)"
trap 'rm -rf "$TMP_PLASMOID"' EXIT
cp -a "$SRC/plasmoid/." "$TMP_PLASMOID/"
sed -e "s|@USAGE_FILE@|$CACHE_DIR/usage.json|g" \
    -e "s|@REFRESH_COMMAND@|$BIN --quiet|g" \
    "$SRC/plasmoid/contents/ui/paths.js.template" > "$TMP_PLASMOID/contents/ui/paths.js"
rm -f "$TMP_PLASMOID/contents/ui/paths.js.template"

if kpackagetool6 --type Plasma/Applet --list 2>/dev/null | grep -qx "$PLASMOID_ID"; then
  kpackagetool6 --type Plasma/Applet --upgrade "$TMP_PLASMOID"
else
  kpackagetool6 --type Plasma/Applet --install "$TMP_PLASMOID"
fi

say "Terminé."
printf 'CLI     : %s\n' "$BIN"
printf 'Données : %s/usage.json\n' "$CACHE_DIR"
printf 'Widget  : ajoute « OpenCode Meter » à ton panneau (clic droit sur le panneau → Ajouter des widgets).\n'
