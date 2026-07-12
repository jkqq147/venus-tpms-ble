#!/bin/sh
set -eu

BRANCH="${VENUS_TPMS_BRANCH:-master}"
BASE_URL="https://codeload.github.com/jkqq147/venus-tpms-ble/zip/refs/heads/$BRANCH"
WORK_DIR="/tmp/venus-tpms-ble-install.$$"
ZIP_FILE="/tmp/venus-tpms-ble.$$.zip"

cleanup() {
	rm -rf "$WORK_DIR" "$ZIP_FILE"
}
trap cleanup EXIT INT TERM

rm -rf "$WORK_DIR" "$ZIP_FILE"
mkdir -p "$WORK_DIR"

echo "Downloading venus-tpms-ble..."
wget -O "$ZIP_FILE" "$BASE_URL"

echo "Extracting..."
unzip -q "$ZIP_FILE" -d "$WORK_DIR"

cd "$WORK_DIR/venus-tpms-ble-$BRANCH"
sh scripts/install.sh

echo "Temporary files cleaned"
