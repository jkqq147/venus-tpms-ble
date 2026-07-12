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

	if [ -f "$PAGE_MAIN" ] && grep -q 'BEGIN venus-tpms-ui' "$PAGE_MAIN"; then
		patched="/tmp/PageMain.qml.venus-tpms.$$"
		sed '/^[[:space:]]*\/\/ BEGIN venus-tpms-ui$/,/^[[:space:]]*\/\/ END venus-tpms-ui$/d' \
			"$PAGE_MAIN" >"$patched"
		mv "$patched" "$PAGE_MAIN"
	fi

rm -f \
	"$GUI_DIR/PageTpms.qml" \
	"$GUI_DIR/PageTpmsBind.qml" \
	"$GUI_DIR/PageTpmsDiagnostics.qml" \
	"$GUI_DIR/PageTpmsDiscovered.qml" \
	"$GUI_DIR/PageTpmsSensorDetails.qml" \
	"$GUI_DIR/PageTpmsWheel.qml"

if command -v svc >/dev/null 2>&1; then
	svc -t /service/gui 2>/dev/null || true
fi

rm -rf "$APP_DIR"

echo "Uninstalled $SERVICE_NAME"
