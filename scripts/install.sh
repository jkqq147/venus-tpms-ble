#!/bin/sh
set -eu

APP_DIR="/data/venus-tpms-ble"
SERVICE_NAME="venus-tpms-ble"
SERVICE_LINK="/service/$SERVICE_NAME"
SERVICE_DIR="$APP_DIR/service"
GUI_DIR="/opt/victronenergy/gui/qml"
PAGE_MAIN="$GUI_DIR/PageMain.qml"
BACKUP_DIR="$APP_DIR/backups"

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

if command -v svc >/dev/null 2>&1 && [ -e "$SERVICE_LINK" ]; then
	svc -d "$SERVICE_LINK" 2>/dev/null || true
	sleep 1
fi

mkdir -p "$APP_DIR" "$SERVICE_DIR" "$BACKUP_DIR"
cp "$REPO_DIR/service/venus-tpms-ble.py" "$APP_DIR/venus-tpms-ble.py"
chmod 0755 "$APP_DIR/venus-tpms-ble.py"
cp "$REPO_DIR/gui/qml/PageTpms.qml" "$GUI_DIR/PageTpms.qml"
cp "$REPO_DIR/gui/qml/PageTpmsBind.qml" "$GUI_DIR/PageTpmsBind.qml"
cp "$REPO_DIR/gui/qml/PageTpmsWheel.qml" "$GUI_DIR/PageTpmsWheel.qml"
chmod 0644 "$GUI_DIR/PageTpms.qml" "$GUI_DIR/PageTpmsBind.qml" "$GUI_DIR/PageTpmsWheel.qml"

if [ ! -f "$PAGE_MAIN" ]; then
	echo "ERROR: $PAGE_MAIN not found" >&2
	exit 1
fi

if ! grep -q 'PageTpms' "$PAGE_MAIN"; then
	backup="$BACKUP_DIR/PageMain.qml.$(date +%Y%m%d-%H%M%S)"
	cp "$PAGE_MAIN" "$backup"
PAGE_MAIN="$PAGE_MAIN" python3 - <<'PY'
import os
from pathlib import Path

path = Path(os.environ["PAGE_MAIN"])
text = path.read_text()
marker = '\t\t\tMbSubMenu {\n\t\t\t\tdescription: qsTr("Settings")'
insert = '''\t\t\tMbSubMenu {
\t\t\t\tdescription: qsTr("TPMS")
\t\t\t\titem: VBusItem { value: [] }
\t\t\t\tMbTextBlock { item.bind: "com.victronenergy.tpms.main/Slots/front_left/DeviceListValue"; width: 62; height: 25 }
\t\t\t\tMbTextBlock { item.bind: "com.victronenergy.tpms.main/Slots/front_right/DeviceListValue"; width: 62; height: 25 }
\t\t\t\tMbTextBlock { item.bind: "com.victronenergy.tpms.main/Slots/rear_left/DeviceListValue"; width: 62; height: 25 }
\t\t\t\tMbTextBlock { item.bind: "com.victronenergy.tpms.main/Slots/rear_right/DeviceListValue"; width: 62; height: 25 }
\t\t\t\tsubpage: Component { PageTpms {} }
\t\t\t}

'''
if "PageTpms" not in text:
    if marker not in text:
        raise SystemExit("Could not find Settings menu insertion point in PageMain.qml")
    text = text.replace(marker, insert + marker, 1)
    path.write_text(text)
PY
	echo "Backed up PageMain.qml to $backup"
else
	PAGE_MAIN="$PAGE_MAIN" python3 - <<'PY'
import os
from pathlib import Path

path = Path(os.environ["PAGE_MAIN"])
text = path.read_text()
replacement = '''\t\t\tMbSubMenu {
\t\t\t\tdescription: qsTr("TPMS")
\t\t\t\titem: VBusItem { value: [] }
\t\t\t\tMbTextBlock { item.bind: "com.victronenergy.tpms.main/Slots/front_left/DeviceListValue"; width: 62; height: 25 }
\t\t\t\tMbTextBlock { item.bind: "com.victronenergy.tpms.main/Slots/front_right/DeviceListValue"; width: 62; height: 25 }
\t\t\t\tMbTextBlock { item.bind: "com.victronenergy.tpms.main/Slots/rear_left/DeviceListValue"; width: 62; height: 25 }
\t\t\t\tMbTextBlock { item.bind: "com.victronenergy.tpms.main/Slots/rear_right/DeviceListValue"; width: 62; height: 25 }
\t\t\t\tsubpage: Component { PageTpms {} }
\t\t\t}'''

lines = text.splitlines()
target = None
for index, line in enumerate(lines):
    if 'description: qsTr("TPMS")' in line:
        target = index
        break

updated = text
if target is not None:
    start = target
    while start >= 0 and "MbSubMenu {" not in lines[start]:
        start -= 1
    if start >= 0:
        depth = 0
        end = start
        started = False
        for index in range(start, len(lines)):
            depth += lines[index].count("{")
            depth -= lines[index].count("}")
            if "{" in lines[index]:
                started = True
            if started and depth == 0:
                end = index
                break
        lines[start:end + 1] = replacement.splitlines()
        updated = "\n".join(lines) + "\n"

if updated != text:
    path.write_text(updated)
PY
	echo "PageMain.qml already contains TPMS menu"
fi

cat > "$SERVICE_DIR/run" <<'EOF'
#!/bin/sh
exec python3 /data/venus-tpms-ble/venus-tpms-ble.py >/dev/null 2>&1
EOF
chmod 0755 "$SERVICE_DIR/run"

ps w | awk '/venus_tpms_bluez_dbus.py|venus_tpms_mock_dbus.py|venus-tpms-ble.py/ && !/awk/ {print $1}' |
while read pid; do
	[ -n "$pid" ] && [ "$pid" != "$$" ] && kill "$pid" 2>/dev/null || true
done

if [ ! -e "$SERVICE_LINK" ]; then
	ln -s "$SERVICE_DIR" "$SERVICE_LINK"
else
	rm -f "$SERVICE_LINK"
	ln -s "$SERVICE_DIR" "$SERVICE_LINK"
fi

if command -v svc >/dev/null 2>&1; then
	svc -u "$SERVICE_LINK" 2>/dev/null || true
	i=0
	while [ "$i" -lt 30 ]; do
		if dbus-send --system --print-reply \
			--dest=com.victronenergy.tpms.main \
			/StatusText \
			com.victronenergy.BusItem.GetValue >/dev/null 2>&1; then
			break
		fi
		i=$((i + 1))
		sleep 1
	done
	svc -t /service/gui 2>/dev/null || true
fi

echo "Installed $SERVICE_NAME"
echo "Service: $SERVICE_LINK"
echo "Logs: disabled by default; run manually with VENUS_TPMS_DEBUG=1 for debugging"
