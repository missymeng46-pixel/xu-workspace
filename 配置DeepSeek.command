#!/bin/zsh

APP_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "为序 XU 配置 DeepSeek AI 分类"
echo "密钥只会保存在这台电脑，不会写入网页或分享包。"
echo ""
read -s "api_key?请输入 DeepSeek API Key："
echo ""

if [[ -z "$api_key" ]]; then
  echo "没有输入密钥，配置已取消。"
  read "?按回车键关闭…"
  exit 1
fi

umask 077
printf '%s\n' \
  "DEEPSEEK_API_KEY=$api_key" \
  "DEEPSEEK_BASE_URL=https://api.deepseek.com" \
  "DEEPSEEK_MODEL=deepseek-chat" > "$APP_DIR/.env"

unset api_key
echo "配置完成。请关闭已经运行的工作台，再双击“启动序.command”。"
read "?按回车键关闭…"
