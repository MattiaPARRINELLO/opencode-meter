#!/usr/bin/env bash
# Désinstalle OpenCode Meter. Les données (~/.cache/opencode-meter) sont conservées.
set -euo pipefail

APP_DIR="$HOME/.local/lib/opencode-meter"
BIN="$HOME/.local/bin/opencode-meter"
UNIT_DIR="$HOME/.config/systemd/user"
PLASMOID_ID="io.github.mattia.opencodemeter"

systemctl --user disable --now opencode-meter.timer 2>/dev/null || true
rm -f "$UNIT_DIR/opencode-meter.service" "$UNIT_DIR/opencode-meter.timer"
systemctl --user daemon-reload

kpackagetool6 --type Plasma/Applet --remove "$PLASMOID_ID" 2>/dev/null || true

rm -rf "$APP_DIR" "$BIN"
printf 'Désinstallé. Données conservées dans ~/.cache/opencode-meter\n'
