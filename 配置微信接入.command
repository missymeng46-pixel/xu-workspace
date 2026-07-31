#!/bin/zsh

APP_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "为序 XU 配置微信消息入口"
echo "请先在微信公众平台测试号页面取得 Token 和关注者 OpenID。"
echo "这些信息只保存在这台电脑，不会进入分享包。"
echo ""
read -s "wechat_token?请输入公众号 Token："
echo ""
read "allowed_openids?请输入允许记录消息的微信 OpenID（多个用逗号分隔）："
read "auto_answer?收到消息后交给 Codex 自动整理？[Y/n]："

if [[ -z "$wechat_token" || -z "$allowed_openids" ]]; then
  echo "Token 和 OpenID 都不能为空，配置已取消。"
  read "?按回车键关闭…"
  exit 1
fi
if [[ "$wechat_token" == *$'\n'* || "$allowed_openids" == *$'\n'* ]]; then
  echo "配置内容格式无效。"
  exit 1
fi

auto_classify=true
if [[ "$auto_answer" == [nN] || "$auto_answer" == [nN][oO] ]]; then
  auto_classify=false
fi

umask 077
temp_env="$(mktemp "$APP_DIR/.env.tmp.XXXXXX")"
trap 'rm -f "$temp_env"' EXIT INT TERM
if [[ -f "$APP_DIR/.env" ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    case "$line" in
      WECHAT_TOKEN=*|WECHAT_ALLOWED_OPENIDS=*|WECHAT_AUTO_CLASSIFY=*|WECHAT_PROCESSOR=*) ;;
      *) print -r -- "$line" >> "$temp_env" ;;
    esac
  done < "$APP_DIR/.env"
fi
printf '%s\n' \
  "WECHAT_TOKEN=$wechat_token" \
  "WECHAT_ALLOWED_OPENIDS=$allowed_openids" \
  "WECHAT_AUTO_CLASSIFY=$auto_classify" \
  "WECHAT_PROCESSOR=codex" >> "$temp_env"
mv "$temp_env" "$APP_DIR/.env"
chmod 600 "$APP_DIR/.env"
trap - EXIT INT TERM

unset wechat_token allowed_openids
echo "配置完成。请重启工作台，再双击“启动微信中转.command”。"
read "?按回车键关闭…"
