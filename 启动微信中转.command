#!/bin/zsh

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
PORT_FILE="$APP_DIR/data/server.port"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "没有找到 cloudflared，请先在终端运行：brew install cloudflared"
  read "?按回车键关闭…"
  exit 1
fi
if [[ ! -f "$APP_DIR/.env" ]] || ! grep -q '^WECHAT_TOKEN=.' "$APP_DIR/.env" || ! grep -q '^WECHAT_ALLOWED_OPENIDS=.' "$APP_DIR/.env"; then
  echo "请先双击“配置微信接入.command”，完成 Token 和 OpenID 白名单配置。"
  read "?按回车键关闭…"
  exit 1
fi

port=4173
if [[ -f "$PORT_FILE" ]]; then
  saved_port="$(<"$PORT_FILE")"
  if [[ "$saved_port" == <-> ]]; then
    port="$saved_port"
  fi
fi
if ! curl -fsS "http://127.0.0.1:$port/api/health" >/dev/null 2>&1; then
  echo "工作台还没有运行，请先双击“启动序.command”。"
  read "?按回车键关闭…"
  exit 1
fi

echo "正在创建微信 HTTPS 中转地址……"
echo "看到 https://……trycloudflare.com 后，把完整地址加上 /api/wechat/callback"
echo "填入微信公众平台测试号的接口配置信息中。这个终端需要保持开启。"
echo ""
exec cloudflared tunnel --url "http://127.0.0.1:$port"
