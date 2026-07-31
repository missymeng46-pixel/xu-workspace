#!/bin/zsh

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
PORT_FILE="$APP_DIR/data/server.port"

cd "$APP_DIR" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  echo "这台 Mac 还没有 Python 3，序 XU 暂时无法启动。"
  echo "请先安装 Python 3，然后再双击“启动序.command”。"
  open "https://www.python.org/downloads/macos/"
  read "?按回车键关闭…"
  exit 1
fi

if [[ -f "$PORT_FILE" ]]; then
  saved_port="$(<"$PORT_FILE")"
  health_payload="$(curl -fsS "http://127.0.0.1:$saved_port/api/health" 2>/dev/null || true)"
  if [[ "$saved_port" == <-> ]] && print -r -- "$health_payload" | grep -Fq "$APP_DIR/data/xu.sqlite3" && print -r -- "$health_payload" | grep -Fq '"mobileAccess": true'; then
    open "http://127.0.0.1:$saved_port/?v=cool-20260731-24&ts=$(date +%s)"
    exit 0
  fi
fi

port=4173
while nc -z 127.0.0.1 "$port" >/dev/null 2>&1; do
  (( port++ ))
  if (( port > 4200 )); then
    echo "序 XU 启动失败：4173–4200 端口均被占用。"
    read "?按回车键关闭…"
    exit 1
  fi
done

mkdir -p "$APP_DIR/data"
python3 "$APP_DIR/server.py" --host 0.0.0.0 --port "$port" &
server_pid=$!
trap 'rm -f "$PORT_FILE"; kill "$server_pid" 2>/dev/null' EXIT INT TERM

for _ in {1..20}; do
  if curl -fsS "http://127.0.0.1:$port/api/health" >/dev/null 2>&1; then
    echo "$port" > "$PORT_FILE"
    open "http://127.0.0.1:$port/?v=cool-20260731-24&ts=$(date +%s)"
    wait "$server_pid"
    exit $?
  fi
  sleep 0.2
done

echo "序 XU 启动失败，请关闭终端后重试。"
kill "$server_pid" 2>/dev/null
exit 1
