#!/bin/sh
set -eu

APP_DIR="/data/venus-tpms-ble"
SERVICE_NAME="venus-tpms-ble"
SERVICE_LINK="/service/$SERVICE_NAME"
SERVICE_DIR="$APP_DIR/service"
BOOT_HOOK="/data/rc.local"
BOOT_START="$APP_DIR/start-service.sh"
BOOT_MARKER_BEGIN="# BEGIN venus-tpms-ble"
BOOT_MARKER_END="# END venus-tpms-ble"
TRIAL_BOOT_MARKER_BEGIN="# BEGIN venus-tpms-ble-trial"
TRIAL_BOOT_MARKER_END="# END venus-tpms-ble-trial"
GUI_DIR="/opt/victronenergy/gui/qml"
PAGE_MAIN="$GUI_DIR/PageMain.qml"
BACKUP_DIR="$APP_DIR/backups"

TRIAL_DIR="/data/venus-tpms-ble-trial"
TRIAL_RUNTIME_DIR="$TRIAL_DIR/runtime"
TRIAL_SERVICE_DIR="$TRIAL_DIR/service"
TRIAL_GUARD_DIR="$TRIAL_DIR/guard"
TRIAL_SERVICE_LINK="/service/venus-tpms-ble-trial"
TRIAL_GUARD_LINK="/service/venus-tpms-ble-trial-guard"
TRIAL_STATE="$TRIAL_DIR/state"
TRIAL_TIMEOUT_SECONDS=600
TTY="/dev/tty"

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
REPO_DIR=$(CDPATH='' cd -- "$SCRIPT_DIR/.." && pwd)

# This table intentionally fails closed. Add a profile only after real GX testing.
SUPPORTED_PROFILE_V355="2b231c72b3a178e2110171c8cfdc693ead829eafc47c19dcaba9a6746a3b3943"

if [ ! -r "$TTY" ] || [ ! -w "$TTY" ]; then
	echo "ERROR: an interactive SSH terminal is required; no changes were made." >&2
	exit 1
fi

if [ "${TERM:-}" != "dumb" ]; then
	GREEN='\033[32m'
	YELLOW='\033[33m'
	RED='\033[31m'
	BOLD='\033[1m'
	RESET='\033[0m'
else
	GREEN=''
	YELLOW=''
	RED=''
	BOLD=''
	RESET=''
fi

say() {
	printf '%s\n' "$1" >"$TTY"
}

prompt() {
	printf '%s' "$1" >"$TTY"
	IFS= read -r REPLY <"$TTY" || REPLY=""
}

sha256() {
	sha256sum "$1" | awk '{print $1}'
}

current_version() {
	if [ -r /opt/victronenergy/version ]; then
		sed -n '1p' /opt/victronenergy/version
	else
		printf 'unknown'
	fi
}

latest_managed_backup() {
	latest=""
	for backup in "$BACKUP_DIR"/PageMain.qml.*; do
		[ -f "$backup" ] || continue
		latest="$backup"
	done
	printf '%s\n' "$latest"
}

profile_is_supported() {
	version="$1"
	page_hash="$2"
	case "$version:$page_hash" in
		v3.55:"$SUPPORTED_PROFILE_V355") return 0 ;;
	esac

	if grep -q 'PageTpms' "$PAGE_MAIN" 2>/dev/null; then
		backup=$(latest_managed_backup)
		if [ -n "$backup" ]; then
			backup_hash=$(sha256 "$backup")
			case "$version:$backup_hash" in
				v3.55:"$SUPPORTED_PROFILE_V355") return 0 ;;
			esac
		fi
	fi
	return 1
}

backup_target() {
	target="$1"
	name="$2"
	if [ -e "$target" ]; then
		cp "$target" "$TRIAL_DIR/backups/$name"
		: >"$TRIAL_DIR/backups/$name.present"
	else
		: >"$TRIAL_DIR/backups/$name.missing"
	fi
}

write_trial_recovery() {
	cat >"$TRIAL_DIR/recover.sh" <<'EOF'
#!/bin/sh
set -eu

TRIAL_DIR="/data/venus-tpms-ble-trial"
BACKUP_DIR="$TRIAL_DIR/backups"
GUI_DIR="/opt/victronenergy/gui/qml"
PAGE_MAIN="$GUI_DIR/PageMain.qml"
SERVICE_LINK="/service/venus-tpms-ble"
TRIAL_SERVICE_LINK="/service/venus-tpms-ble-trial"
TRIAL_GUARD_LINK="/service/venus-tpms-ble-trial-guard"
BOOT_HOOK="/data/rc.local"
TRIAL_BOOT_MARKER_BEGIN="# BEGIN venus-tpms-ble-trial"
TRIAL_BOOT_MARKER_END="# END venus-tpms-ble-trial"

restore_target() {
	target="$1"
	name="$2"
	if [ -f "$BACKUP_DIR/$name.present" ]; then
		cp "$BACKUP_DIR/$name" "$target"
	else
		rm -f "$target"
	fi
}

[ -d "$TRIAL_DIR" ] || exit 0
state=$(cat "$TRIAL_DIR/state" 2>/dev/null || true)
[ "$state" = "confirmed" ] && exit 0

printf 'rolled-back\n' >"$TRIAL_DIR/state"

if [ -f "$BOOT_HOOK" ] && grep -q "^$TRIAL_BOOT_MARKER_BEGIN\$" "$BOOT_HOOK"; then
	tmp="$TRIAL_DIR/rc.local.$$"
	sed "/^$TRIAL_BOOT_MARKER_BEGIN\$/,/^$TRIAL_BOOT_MARKER_END\$/d" "$BOOT_HOOK" >"$tmp"
	mv "$tmp" "$BOOT_HOOK"
	chmod 0755 "$BOOT_HOOK"
fi

if command -v svc >/dev/null 2>&1 && [ -e "$TRIAL_SERVICE_LINK" ]; then
	svc -d "$TRIAL_SERVICE_LINK" 2>/dev/null || true
fi
rm -f "$TRIAL_SERVICE_LINK" "$TRIAL_GUARD_LINK"

restore_target "$PAGE_MAIN" "PageMain.qml"
restore_target "$GUI_DIR/PageTpms.qml" "PageTpms.qml"
restore_target "$GUI_DIR/PageTpmsBind.qml" "PageTpmsBind.qml"
restore_target "$GUI_DIR/PageTpmsDiagnostics.qml" "PageTpmsDiagnostics.qml"
restore_target "$GUI_DIR/PageTpmsDiscovered.qml" "PageTpmsDiscovered.qml"
restore_target "$GUI_DIR/PageTpmsSensorDetails.qml" "PageTpmsSensorDetails.qml"
restore_target "$GUI_DIR/PageTpmsWheel.qml" "PageTpmsWheel.qml"

if command -v svc >/dev/null 2>&1; then
	svc -t /service/gui 2>/dev/null || true
	if [ -f "$TRIAL_DIR/existing-service" ] && [ -e "$SERVICE_LINK" ]; then
		svc -u "$SERVICE_LINK" 2>/dev/null || true
	fi
fi
EOF
	chmod 0755 "$TRIAL_DIR/recover.sh"
}

write_trial_guard() {
	cat >"$TRIAL_GUARD_DIR/run" <<EOF
#!/bin/sh
set -eu

TRIAL_DIR="$TRIAL_DIR"
TRIAL_STATE="\$TRIAL_DIR/state"
TRIAL_BOOT_ID="\$TRIAL_DIR/boot-id"
TRIAL_GUARD_LINK="$TRIAL_GUARD_LINK"
RECOVERY="\$TRIAL_DIR/recover.sh"
TIMEOUT_SECONDS=$TRIAL_TIMEOUT_SECONDS

current_boot_id() {
	cat /proc/sys/kernel/random/boot_id 2>/dev/null || printf unknown
}

gui_pid() {
	svstat /service/gui 2>/dev/null | sed -n 's/.*pid \([0-9][0-9]*\).*/\1/p'
}

rollback() {
	sh "\$RECOVERY" || true
	rm -f "\$TRIAL_GUARD_LINK"
	rm -rf "\$TRIAL_DIR"
	exit 0
}

[ -f "\$TRIAL_STATE" ] || exit 0
[ "\$(cat "\$TRIAL_STATE" 2>/dev/null || true)" = running ] || exit 0
[ "\$(current_boot_id)" = "\$(cat "\$TRIAL_BOOT_ID" 2>/dev/null || true)" ] || rollback

last_pid="\$(gui_pid)"
restarts=0
elapsed=0
while [ "\$elapsed" -lt "\$TIMEOUT_SECONDS" ]; do
	state="\$(cat "\$TRIAL_STATE" 2>/dev/null || true)"
	[ "\$state" = confirmed ] && exit 0
	[ "\$state" = running ] || exit 0
	[ "\$(current_boot_id)" = "\$(cat "\$TRIAL_BOOT_ID" 2>/dev/null || true)" ] || rollback

	pid="\$(gui_pid)"
	if [ -z "\$pid" ]; then
		restarts=\$((restarts + 1))
	elif [ -n "\$last_pid" ] && [ "\$pid" != "\$last_pid" ]; then
		restarts=\$((restarts + 1))
	fi
	last_pid="\$pid"
	[ "\$restarts" -lt 3 ] || rollback
	sleep 2
	elapsed=\$((elapsed + 2))
done

rollback
EOF
	chmod 0755 "$TRIAL_GUARD_DIR/run"
}

patch_page_main() {
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

if "PageTpms" not in text:
    marker = '\t\t\tMbSubMenu {\n\t\t\t\tdescription: qsTr("Settings")'
    if marker not in text:
        raise SystemExit("Could not find the supported Settings insertion point in PageMain.qml")
    path.write_text(text.replace(marker, replacement + "\n\n" + marker, 1))
    raise SystemExit(0)

lines = text.splitlines()
target = next((index for index, line in enumerate(lines) if 'description: qsTr("TPMS")' in line), None)
if target is None:
    raise SystemExit("PageTpms marker is present but the TPMS menu block is invalid")
start = target
while start >= 0 and "MbSubMenu {" not in lines[start]:
    start -= 1
if start < 0:
    raise SystemExit("Could not locate the existing TPMS menu block")

depth = 0
end = None
for index in range(start, len(lines)):
    depth += lines[index].count("{")
    depth -= lines[index].count("}")
    if depth == 0:
        end = index
        break
if end is None:
    raise SystemExit("Existing TPMS menu block is incomplete")
lines[start:end + 1] = replacement.splitlines()
path.write_text("\n".join(lines) + "\n")
PY
}

write_service_run() {
	target_dir="$1"
	runtime="$2"
	mkdir -p "$target_dir"
	cat >"$target_dir/run" <<EOF
#!/bin/sh
exec python3 "$runtime/venus-tpms-ble.py" >/dev/null 2>&1
EOF
	chmod 0755 "$target_dir/run"
}

write_service_finish() {
	cat >"$SERVICE_DIR/finish" <<'EOF'
#!/bin/sh
# Avoid a tight runit restart loop if a future Venus release breaks a dependency.
sleep 5
exit 0
EOF
	chmod 0755 "$SERVICE_DIR/finish"
}

write_boot_start() {
	cat >"$BOOT_START" <<EOF
#!/bin/sh
set -eu

SERVICE_DIR="$SERVICE_DIR"
SERVICE_LINK="$SERVICE_LINK"

i=0
while [ ! -d /service ] && [ "\$i" -lt 30 ]; do
	sleep 1
	i=\$((i + 1))
done
[ -d /service ] || exit 0

if [ -e "\$SERVICE_LINK" ] || [ -L "\$SERVICE_LINK" ]; then
	[ "\$(readlink "\$SERVICE_LINK" 2>/dev/null || true)" = "\$SERVICE_DIR" ] || exit 1
else
	ln -s "\$SERVICE_DIR" "\$SERVICE_LINK"
fi

i=0
while [ "\$i" -lt 10 ]; do
	svc -u "\$SERVICE_LINK" 2>/dev/null && exit 0
	sleep 1
	i=\$((i + 1))
done
exit 0
EOF
	chmod 0755 "$BOOT_START"
}

install_boot_hook() {
	tmp="$APP_DIR/rc.local.$$"
	if [ -f "$BOOT_HOOK" ]; then
		sed "/^$BOOT_MARKER_BEGIN\$/,/^$BOOT_MARKER_END\$/d" "$BOOT_HOOK" >"$tmp"
	else
		printf '%s\n' '#!/bin/sh' >"$tmp"
	fi
	cat >>"$tmp" <<EOF

$BOOT_MARKER_BEGIN
"$BOOT_START" >/dev/null 2>&1 &
$BOOT_MARKER_END
EOF
	mv "$tmp" "$BOOT_HOOK"
	chmod 0755 "$BOOT_HOOK"
}

install_trial_boot_hook() {
	tmp="$TRIAL_DIR/rc.local.$$"
	if [ -f "$BOOT_HOOK" ]; then
		sed "/^$TRIAL_BOOT_MARKER_BEGIN\$/,/^$TRIAL_BOOT_MARKER_END\$/d" "$BOOT_HOOK" >"$tmp"
	else
		printf '%s\n' '#!/bin/sh' >"$tmp"
	fi
	cat >>"$tmp" <<EOF

$TRIAL_BOOT_MARKER_BEGIN
(sh "$TRIAL_DIR/recover.sh"; rm -rf "$TRIAL_DIR") >/dev/null 2>&1 &
$TRIAL_BOOT_MARKER_END
EOF
	mv "$tmp" "$BOOT_HOOK"
	chmod 0755 "$BOOT_HOOK"
}

remove_trial_boot_hook() {
	if [ -f "$BOOT_HOOK" ] && grep -q "^$TRIAL_BOOT_MARKER_BEGIN\$" "$BOOT_HOOK"; then
		tmp="$TRIAL_DIR/rc.local.$$"
		sed "/^$TRIAL_BOOT_MARKER_BEGIN\$/,/^$TRIAL_BOOT_MARKER_END\$/d" "$BOOT_HOOK" >"$tmp"
		mv "$tmp" "$BOOT_HOOK"
		chmod 0755 "$BOOT_HOOK"
	fi
}

stop_tpms_processes() {
	ps w | awk '/venus_tpms_bluez_dbus.py|venus_tpms_mock_dbus.py|venus-tpms-ble.py/ && !/awk/ {print $1}' |
	while read -r pid; do
		[ -n "$pid" ] && [ "$pid" != "$$" ] && kill "$pid" 2>/dev/null || true
	done
}

rollback_trial() {
	if [ -f "$TRIAL_DIR/recover.sh" ]; then
		sh "$TRIAL_DIR/recover.sh" || true
	fi
	rm -rf "$TRIAL_DIR"
}

trial_started=0
trap 'if [ "$trial_started" -eq 1 ]; then rollback_trial; fi' INT TERM HUP

if ! command -v svc >/dev/null 2>&1 || ! command -v svstat >/dev/null 2>&1; then
	say "${RED}ERROR: runit tools are unavailable; no changes were made.${RESET}"
	exit 1
fi
if [ ! -f "$PAGE_MAIN" ]; then
	say "${RED}ERROR: $PAGE_MAIN not found; no changes were made.${RESET}"
	exit 1
fi
if [ -e "$BOOT_HOOK" ] && [ ! -f "$BOOT_HOOK" ]; then
	say "${RED}ERROR: $BOOT_HOOK is not a regular file; no changes were made.${RESET}"
	exit 1
fi
if [ -f "$TRIAL_STATE" ] && [ "$(cat "$TRIAL_STATE" 2>/dev/null || true)" = running ]; then
	say "${RED}ERROR: a protected trial is already running; no changes were made.${RESET}"
	exit 1
fi

VERSION=$(current_version)
PAGE_HASH=$(sha256 "$PAGE_MAIN")
if profile_is_supported "$VERSION" "$PAGE_HASH"; then
	PROFILE="supported"
	PROFILE_COLOR="$GREEN"
else
	PROFILE="unknown"
	PROFILE_COLOR="$YELLOW"
fi

say "Detected Venus OS: $VERSION"
say "${PROFILE_COLOR}${BOLD}UI profile: $PROFILE${RESET}"
say "PageMain.qml SHA256: $PAGE_HASH"
say ""
prompt "Start protected temporary trial? [y/N] "
case "$REPLY" in
	y|Y) ;;
	*)
		say "No changes were made."
		exit 0
		;;
esac

rm -rf "$TRIAL_DIR"
mkdir -p "$TRIAL_DIR/backups" "$TRIAL_RUNTIME_DIR" "$TRIAL_SERVICE_DIR" "$TRIAL_GUARD_DIR"
printf 'running\n' >"$TRIAL_STATE"
cat /proc/sys/kernel/random/boot_id 2>/dev/null >"$TRIAL_DIR/boot-id" || printf unknown >"$TRIAL_DIR/boot-id"

backup_target "$PAGE_MAIN" "PageMain.qml"
backup_target "$GUI_DIR/PageTpms.qml" "PageTpms.qml"
backup_target "$GUI_DIR/PageTpmsBind.qml" "PageTpmsBind.qml"
backup_target "$GUI_DIR/PageTpmsDiagnostics.qml" "PageTpmsDiagnostics.qml"
backup_target "$GUI_DIR/PageTpmsDiscovered.qml" "PageTpmsDiscovered.qml"
backup_target "$GUI_DIR/PageTpmsSensorDetails.qml" "PageTpmsSensorDetails.qml"
backup_target "$GUI_DIR/PageTpmsWheel.qml" "PageTpmsWheel.qml"
[ -e "$SERVICE_LINK" ] && : >"$TRIAL_DIR/existing-service"

write_trial_recovery
write_trial_guard
ln -s "$TRIAL_GUARD_DIR" "$TRIAL_GUARD_LINK"
trial_started=1
if ! install_trial_boot_hook; then
	say "${RED}Unable to create the protected trial recovery hook; no UI changes were made.${RESET}"
	rm -f "$TRIAL_GUARD_LINK"
	rm -rf "$TRIAL_DIR"
	trial_started=0
	exit 1
fi

cp "$REPO_DIR/service/venus-tpms-ble.py" "$TRIAL_RUNTIME_DIR/venus-tpms-ble.py"
chmod 0755 "$TRIAL_RUNTIME_DIR/venus-tpms-ble.py"
write_service_run "$TRIAL_SERVICE_DIR" "$TRIAL_RUNTIME_DIR"

if [ -e "$SERVICE_LINK" ]; then
	svc -d "$SERVICE_LINK" 2>/dev/null || true
	fi
stop_tpms_processes

cp "$REPO_DIR/gui/qml/PageTpms.qml" "$GUI_DIR/PageTpms.qml"
cp "$REPO_DIR/gui/qml/PageTpmsBind.qml" "$GUI_DIR/PageTpmsBind.qml"
cp "$REPO_DIR/gui/qml/PageTpmsDiagnostics.qml" "$GUI_DIR/PageTpmsDiagnostics.qml"
cp "$REPO_DIR/gui/qml/PageTpmsDiscovered.qml" "$GUI_DIR/PageTpmsDiscovered.qml"
cp "$REPO_DIR/gui/qml/PageTpmsSensorDetails.qml" "$GUI_DIR/PageTpmsSensorDetails.qml"
cp "$REPO_DIR/gui/qml/PageTpmsWheel.qml" "$GUI_DIR/PageTpmsWheel.qml"
chmod 0644 \
	"$GUI_DIR/PageTpms.qml" \
	"$GUI_DIR/PageTpmsBind.qml" \
	"$GUI_DIR/PageTpmsDiagnostics.qml" \
	"$GUI_DIR/PageTpmsDiscovered.qml" \
	"$GUI_DIR/PageTpmsSensorDetails.qml" \
	"$GUI_DIR/PageTpmsWheel.qml"

if ! patch_page_main; then
	say "${RED}Unable to patch PageMain.qml. Restoring the original UI.${RESET}"
	rollback_trial
	trial_started=0
	exit 1
fi

ln -s "$TRIAL_SERVICE_DIR" "$TRIAL_SERVICE_LINK"
svc -u "$TRIAL_SERVICE_LINK" 2>/dev/null || true

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
if [ "$i" -eq 30 ]; then
	say "${RED}TPMS trial service did not start. Restoring the original UI.${RESET}"
	rollback_trial
	trial_started=0
	exit 1
fi

svc -t /service/gui 2>/dev/null || true
say ""
say "${YELLOW}${BOLD}Protected trial is active.${RESET}"
say "Check the TPMS page on the GX screen. The trial rolls back on GUI crash loops, timeout, or reboot."
prompt "Type CONFIRM to install permanently; any other input restores the original UI: "

if [ "$REPLY" != "CONFIRM" ] || [ "$(cat "$TRIAL_STATE" 2>/dev/null || true)" != running ]; then
	say "Restoring the original UI."
	rollback_trial
	trial_started=0
	exit 0
fi

mkdir -p "$APP_DIR" "$SERVICE_DIR" "$BACKUP_DIR"
cp "$TRIAL_RUNTIME_DIR/venus-tpms-ble.py" "$APP_DIR/venus-tpms-ble.py"
chmod 0755 "$APP_DIR/venus-tpms-ble.py"
write_service_run "$SERVICE_DIR" "$APP_DIR"
write_service_finish
write_boot_start
install_boot_hook

if [ ! -f "$BACKUP_DIR/PageMain.qml.original" ] && [ -z "$(latest_managed_backup)" ]; then
	cp "$TRIAL_DIR/backups/PageMain.qml" "$BACKUP_DIR/PageMain.qml.original"
fi

printf 'confirmed\n' >"$TRIAL_STATE"
svc -d "$TRIAL_SERVICE_LINK" 2>/dev/null || true
svc -d "$TRIAL_GUARD_LINK" 2>/dev/null || true
rm -f "$TRIAL_SERVICE_LINK" "$TRIAL_GUARD_LINK"
remove_trial_boot_hook

if [ -e "$SERVICE_LINK" ]; then
	svc -d "$SERVICE_LINK" 2>/dev/null || true
	rm -f "$SERVICE_LINK"
fi
ln -s "$SERVICE_DIR" "$SERVICE_LINK"
svc -u "$SERVICE_LINK" 2>/dev/null || true

rm -rf "$TRIAL_DIR"
trial_started=0

say "${GREEN}${BOLD}TPMS installed permanently.${RESET}"
say "Service: $SERVICE_LINK"
say "Logs: disabled by default; run manually with VENUS_TPMS_DEBUG=1 for debugging"
