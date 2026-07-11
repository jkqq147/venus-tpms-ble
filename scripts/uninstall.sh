#!/bin/sh
set -eu

APP_DIR="/data/venus-tpms-ble"
SERVICE_NAME="venus-tpms-ble"
SERVICE_LINK="/service/$SERVICE_NAME"
GUI_DIR="/opt/victronenergy/gui/qml"
PAGE_MAIN="$GUI_DIR/PageMain.qml"
BACKUP_DIR="$APP_DIR/backups"

if command -v svc >/dev/null 2>&1 && [ -e "$SERVICE_LINK" ]; then
	svc -d "$SERVICE_LINK" 2>/dev/null || true
fi

if [ -L "$SERVICE_LINK" ]; then
	rm -f "$SERVICE_LINK"
fi

latest_backup=""
if [ -d "$BACKUP_DIR" ]; then
	latest_backup=$(ls -1t "$BACKUP_DIR"/PageMain.qml.* 2>/dev/null | head -n 1 || true)
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
text = path.read_text()
block = '''\t\t\tMbSubMenu {
\t\t\t\tdescription: qsTr("TPMS")
\t\t\t\titem: VBusItem {
\t\t\t\t\tbind: "com.victronenergy.tpms.main/DiscoveredCount"
\t\t\t\t}
\t\t\t\tsubpage: Component { PageTpms {} }
\t\t\t}

'''
path.write_text(text.replace(block, "", 1))
PY
	fi
fi

rm -f "$GUI_DIR/PageTpms.qml" "$GUI_DIR/PageTpmsBind.qml" "$GUI_DIR/PageTpmsWheel.qml"

if command -v svc >/dev/null 2>&1; then
	svc -t /service/gui 2>/dev/null || true
fi

echo "Uninstalled $SERVICE_NAME"
