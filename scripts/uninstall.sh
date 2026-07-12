#!/bin/sh
set -eu

APP_DIR="/data/venus-tpms-ble"
SERVICE_NAME="venus-tpms-ble"
SERVICE_LINK="/service/$SERVICE_NAME"
BOOT_HOOK="/data/rc.local"
BOOT_START="$APP_DIR/start-service.sh"
BOOT_MARKER_BEGIN="# BEGIN venus-tpms-ble"
BOOT_MARKER_END="# END venus-tpms-ble"
GUI_DIR="/opt/victronenergy/gui/qml"
PAGE_MAIN="$GUI_DIR/PageMain.qml"
BACKUP_DIR="$APP_DIR/backups"
TRIAL_DIR="/data/venus-tpms-ble-trial"
TRIAL_SERVICE_LINK="/service/venus-tpms-ble-trial"
TRIAL_GUARD_LINK="/service/venus-tpms-ble-trial-guard"

if [ -f "$TRIAL_DIR/recover.sh" ] && [ "$(cat "$TRIAL_DIR/state" 2>/dev/null || true)" = "running" ]; then
	sh "$TRIAL_DIR/recover.sh" || true
fi
if command -v svc >/dev/null 2>&1; then
	svc -d "$TRIAL_SERVICE_LINK" 2>/dev/null || true
	svc -d "$TRIAL_GUARD_LINK" 2>/dev/null || true
fi
rm -f "$TRIAL_SERVICE_LINK" "$TRIAL_GUARD_LINK"
rm -rf "$TRIAL_DIR"

if command -v svc >/dev/null 2>&1 && [ -e "$SERVICE_LINK" ]; then
	svc -d "$SERVICE_LINK" 2>/dev/null || true
fi

if [ -L "$SERVICE_LINK" ]; then
	rm -f "$SERVICE_LINK"
fi

if [ -f "$BOOT_HOOK" ] && grep -q "^$BOOT_MARKER_BEGIN\$" "$BOOT_HOOK"; then
	tmp="$APP_DIR/rc.local.$$"
	sed "/^$BOOT_MARKER_BEGIN\$/,/^$BOOT_MARKER_END\$/d" "$BOOT_HOOK" >"$tmp"
	mv "$tmp" "$BOOT_HOOK"
	chmod 0755 "$BOOT_HOOK"
fi
rm -f "$BOOT_START"

latest_backup=""
if [ -f "$BACKUP_DIR/PageMain.qml.original" ]; then
	latest_backup="$BACKUP_DIR/PageMain.qml.original"
elif [ -d "$BACKUP_DIR" ]; then
	for backup in "$BACKUP_DIR"/PageMain.qml.*; do
		[ -f "$backup" ] || continue
		latest_backup="$backup"
	done
fi

if [ -n "$latest_backup" ]; then
	cp "$latest_backup" "$PAGE_MAIN"
	echo "Restored PageMain.qml from $latest_backup"
else
	if [ -f "$PAGE_MAIN" ] && grep -q 'PageTpms' "$PAGE_MAIN"; then
		PAGE_MAIN="$PAGE_MAIN" python3 - <<'PY'
import os
from pathlib import Path

path = Path(os.environ["PAGE_MAIN"])
lines = path.read_text().splitlines()
target = next((index for index, line in enumerate(lines) if 'description: qsTr("TPMS")' in line), None)
if target is not None:
    start = target
    while start >= 0 and "MbSubMenu {" not in lines[start]:
        start -= 1
    if start >= 0:
        depth = 0
        end = None
        for index in range(start, len(lines)):
            depth += lines[index].count("{")
            depth -= lines[index].count("}")
            if depth == 0:
                end = index
                break
        if end is not None:
            del lines[start:end + 1]
            if start < len(lines) and not lines[start].strip():
                del lines[start]
path.write_text("\n".join(lines) + "\n")
PY
		fi
fi

rm -f "$GUI_DIR/PageTpms.qml" "$GUI_DIR/PageTpmsBind.qml" "$GUI_DIR/PageTpmsWheel.qml"

if command -v svc >/dev/null 2>&1; then
	svc -t /service/gui 2>/dev/null || true
fi

echo "Uninstalled $SERVICE_NAME"
