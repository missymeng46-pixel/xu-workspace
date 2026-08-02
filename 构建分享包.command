#!/bin/zsh

set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT_DIR="$APP_DIR/../分享包"
BUILD_DIR="$(mktemp -d "${TMPDIR:-/tmp}/xu-release.XXXXXX")"
PACKAGE_NAME="序-XU-工作台-macOS-$(date +%Y%m%d-%H%M%S)"
STAGE_DIR="$BUILD_DIR/序 XU 工作台"

cleanup() {
  rm -rf "$BUILD_DIR"
}
trap cleanup EXIT INT TERM

mkdir -p "$OUTPUT_DIR" "$STAGE_DIR"
rsync -a \
  --exclude '.env' \
  --exclude '.git' \
  --exclude '.DS_Store' \
  --exclude 'data' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude 'sample-transactions.csv' \
  --exclude '构建分享包.command' \
  "$APP_DIR/" "$STAGE_DIR/"

chmod +x "$STAGE_DIR/启动序.command" "$STAGE_DIR/配置DeepSeek.command" \
  "$STAGE_DIR/配置微信接入.command" "$STAGE_DIR/启动微信中转.command"
ditto -c -k --sequesterRsrc --keepParent "$STAGE_DIR" "$OUTPUT_DIR/$PACKAGE_NAME.zip"

echo "分享包已经生成："
echo "$OUTPUT_DIR/$PACKAGE_NAME.zip"
