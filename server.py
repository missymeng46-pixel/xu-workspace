#!/usr/bin/env python3
"""Local-first HTTP server and SQLite API for XU Workspace."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import hmac
import ipaddress
import io
import json
import os
import re
import secrets
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from email.parser import BytesParser
from email.policy import default as email_policy
from email.utils import parsedate_to_datetime
from functools import partial
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen


APP_DIR = Path(__file__).resolve().parent
STATIC_ROOT = APP_DIR
DATA_DIR = APP_DIR / "data"
DB_PATH = DATA_DIR / "xu.sqlite3"
AESTHETIC_UPLOAD_DIR = DATA_DIR / "aesthetic_uploads"
ENV_PATH = APP_DIR / ".env"
MOBILE_COOKIE = "xu_mobile_session"
MOBILE_ACCESS = {
    "enabled": False,
    "port": 4173,
    "lan_ip": "",
    "access_code": "",
    "session_token": "",
}
LOGIN_ATTEMPTS: dict[str, list[float]] = {}
WECHAT_CLASSIFY_LOCK = threading.Lock()
VIBE_REFRESH_LOCK = threading.Lock()
AESTHETIC_FOLDERS = {
    "colors", "homepages", "typography", "charts", "three_d", "motion", "instinct",
}
AESTHETIC_FOLDER_LABELS = {
    "colors": "喜欢的配色",
    "homepages": "喜欢的首页",
    "typography": "喜欢的字体和排版",
    "charts": "喜欢的图表",
    "three_d": "喜欢的 3D",
    "motion": "喜欢的动画",
    "instinct": "不知道为什么，但就是喜欢",
}


def find_lan_ip() -> str:
    """Return the address other devices on the current network can reach."""
    private_networks = tuple(ipaddress.ip_network(cidr) for cidr in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))

    def usable(ip: str) -> bool:
        try:
            address = ipaddress.ip_address(ip)
            return address.version == 4 and any(address in network for network in private_networks)
        except ValueError:
            return False

    # On macOS the default route may point at a VPN. Physical interfaces are a
    # better source for the address another device on the same Wi-Fi can reach.
    for interface in ("en0", "en1", "en2", "en3", "en4", "en5"):
        try:
            candidate = subprocess.check_output(
                ["ipconfig", "getifaddr", interface], stderr=subprocess.DEVNULL, text=True, timeout=1
            ).strip()
            if usable(candidate):
                return candidate
        except (FileNotFoundError, subprocess.SubprocessError):
            continue

    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("10.255.255.255", 1))
        candidate = str(probe.getsockname()[0])
        return candidate if usable(candidate) else ""
    except OSError:
        try:
            candidates = socket.gethostbyname_ex(socket.gethostname())[2]
            return next((ip for ip in candidates if usable(ip)), "")
        except OSError:
            return ""
    finally:
        probe.close()


def load_env() -> None:
    if not ENV_PATH.exists():
        return
    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def init_database() -> None:
    load_env()
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                type TEXT NOT NULL DEFAULT 'other',
                opening_balance REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                kind TEXT NOT NULL CHECK(kind IN ('income', 'expense')),
                color TEXT NOT NULL DEFAULT '#151718',
                UNIQUE(name, kind)
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL CHECK(kind IN ('income', 'expense')),
                amount REAL NOT NULL CHECK(amount > 0),
                transaction_date TEXT NOT NULL,
                category_id INTEGER NOT NULL REFERENCES categories(id),
                account_id INTEGER NOT NULL REFERENCES accounts(id),
                project TEXT NOT NULL DEFAULT '',
                counterparty TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER NOT NULL REFERENCES categories(id),
                month TEXT NOT NULL,
                limit_amount REAL NOT NULL CHECK(limit_amount >= 0),
                UNIQUE(category_id, month)
            );

            CREATE TABLE IF NOT EXISTS monthly_budgets (
                month TEXT PRIMARY KEY,
                amount REAL NOT NULL CHECK(amount >= 0),
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS exercise_checkins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exercise_date TEXT NOT NULL UNIQUE,
                activity TEXT NOT NULL,
                duration_minutes INTEGER CHECK(duration_minutes IS NULL OR duration_minutes >= 0),
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS inbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                raw_text TEXT NOT NULL,
                inferred_type TEXT NOT NULL DEFAULT 'note',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS wechat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT NOT NULL UNIQUE,
                open_id TEXT NOT NULL,
                message_type TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                inbox_id INTEGER REFERENCES inbox(id),
                received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                due_date TEXT NOT NULL,
                completed_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'todo' CHECK(status IN ('todo', 'doing', 'review')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS content_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'idea' CHECK(status IN ('idea', 'creating', 'ready', 'published')),
                source_inbox_id INTEGER UNIQUE REFERENCES inbox(id),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                body TEXT NOT NULL DEFAULT '',
                source_inbox_id INTEGER UNIQUE REFERENCES inbox(id),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS vibe_feed_cache (
                cache_key TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS aesthetic_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                folder TEXT NOT NULL,
                source_url TEXT NOT NULL DEFAULT '',
                image_url TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS aesthetic_profile (
                profile_key TEXT PRIMARY KEY,
                profile_json TEXT NOT NULL,
                item_count INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        db.executemany(
            "INSERT OR IGNORE INTO app_settings(key, value) VALUES (?, ?)",
            [("display_name", "新朋友"), ("workspace_name", "我的工作空间")],
        )
        inbox_columns = {row["name"] for row in db.execute("PRAGMA table_info(inbox)")}
        if "analysis_json" not in inbox_columns:
            db.execute("ALTER TABLE inbox ADD COLUMN analysis_json TEXT NOT NULL DEFAULT '{}' ")
        if "processed_at" not in inbox_columns:
            db.execute("ALTER TABLE inbox ADD COLUMN processed_at TEXT")
        if "destination_id" not in inbox_columns:
            db.execute("ALTER TABLE inbox ADD COLUMN destination_id INTEGER")
        if db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0:
            seed_database(db)
        expense_names = {row["name"] for row in db.execute("SELECT name FROM categories WHERE kind='expense'")}
        if not expense_names.intersection({"饮食", "餐饮"}):
            db.execute("INSERT INTO categories(name, kind, color) VALUES ('饮食', 'expense', '#d7a65a')")
        if not expense_names.intersection({"工作必要开支", "项目成本", "工作支出"}):
            db.execute("INSERT INTO categories(name, kind, color) VALUES ('工作必要开支', 'expense', '#759bb2')")
        orphaned_projects = db.execute(
            """
            SELECT id, raw_text, analysis_json FROM inbox
            WHERE status='processed' AND inferred_type='project' AND destination_id IS NULL
            """
        ).fetchall()
        for item in orphaned_projects:
            analysis = parse_json_object(item["analysis_json"])
            title = str(analysis.get("title") or item["raw_text"]).strip()[:160]
            cursor = db.execute(
                "INSERT INTO projects(title, description, status) VALUES (?, ?, 'todo')",
                (title, item["raw_text"][:500]),
            )
            db.execute("UPDATE inbox SET destination_id=? WHERE id=?", (cursor.lastrowid, item["id"]))
        orphaned_content = db.execute(
            "SELECT id, raw_text, analysis_json FROM inbox WHERE status='processed' AND inferred_type='content' AND destination_id IS NULL"
        ).fetchall()
        for item in orphaned_content:
            analysis = parse_json_object(item["analysis_json"])
            title = str(analysis.get("title") or item["raw_text"]).strip()[:200]
            db.execute(
                "INSERT OR IGNORE INTO content_items(title, description, source_inbox_id) VALUES (?, ?, ?)",
                (title, item["raw_text"][:800], item["id"]),
            )
            destination = db.execute("SELECT id FROM content_items WHERE source_inbox_id=?", (item["id"],)).fetchone()["id"]
            db.execute("UPDATE inbox SET destination_id=? WHERE id=?", (destination, item["id"]))
        orphaned_notes = db.execute(
            "SELECT id, raw_text, analysis_json FROM inbox WHERE status='processed' AND inferred_type='note' AND destination_id IS NULL"
        ).fetchall()
        for item in orphaned_notes:
            analysis = parse_json_object(item["analysis_json"])
            title = str(analysis.get("title") or item["raw_text"]).strip()[:200]
            db.execute(
                "INSERT OR IGNORE INTO notes(title, body, source_inbox_id) VALUES (?, ?, ?)",
                (title, item["raw_text"][:2000], item["id"]),
            )
            destination = db.execute("SELECT id FROM notes WHERE source_inbox_id=?", (item["id"],)).fetchone()["id"]
            db.execute("UPDATE inbox SET destination_id=? WHERE id=?", (destination, item["id"]))


def seed_database(db: sqlite3.Connection) -> None:
    accounts = [
        ("微信", "wallet", 0),
        ("支付宝", "wallet", 0),
        ("银行卡", "bank", 0),
        ("现金", "cash", 0),
    ]
    db.executemany("INSERT INTO accounts(name, type, opening_balance) VALUES (?, ?, ?)", accounts)

    categories = [
        ("项目收入", "income", "#386e5a"),
        ("其他收入", "income", "#9dc8eb"),
        ("餐饮", "expense", "#f16c3d"),
        ("项目成本", "expense", "#151718"),
        ("软件订阅", "expense", "#9dc8eb"),
        ("交通", "expense", "#eaa251"),
        ("学习成长", "expense", "#f2e429"),
        ("生活固定", "expense", "#777d7e"),
        ("其他支出", "expense", "#c6cacb"),
    ]
    db.executemany("INSERT INTO categories(name, kind, color) VALUES (?, ?, ?)", categories)



def row_dict(row: sqlite3.Row) -> dict:
    return {key: row[key] for key in row.keys()}


def parse_json_object(value: str | None) -> dict:
    try:
        return json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}


def inbox_payload(db: sqlite3.Connection) -> list[dict]:
    items = []
    for row in db.execute(
        """
        SELECT id, raw_text AS rawText, inferred_type AS inferredType, status,
               analysis_json AS analysisJson, destination_id AS destinationId,
               created_at AS createdAt, processed_at AS processedAt
        FROM inbox ORDER BY id DESC
        """
    ):
        item = row_dict(row)
        item["analysis"] = parse_json_object(item.pop("analysisJson", "{}"))
        items.append(item)
    return items


def normalize_classification(result: dict, raw_text: str) -> dict:
    item_type = str(result.get("type", "note")).lower()
    if item_type not in {"task", "transaction", "content", "project", "note"}:
        item_type = "note"
    title = str(result.get("title") or raw_text).strip()[:240]
    due_date = str(result.get("dueDate") or "").strip()
    try:
        due_date = date.fromisoformat(due_date).isoformat() if due_date else ""
    except ValueError:
        due_date = ""
    try:
        confidence = max(0, min(1, float(result.get("confidence", 0))))
    except (TypeError, ValueError):
        confidence = 0
    transaction_kind = str(result.get("transactionKind") or "").lower()
    if transaction_kind not in {"income", "expense"}:
        transaction_kind = ""
    try:
        amount = abs(round(float(result.get("amount")), 2)) if result.get("amount") not in {None, ""} else None
    except (TypeError, ValueError):
        amount = None
    return {
        "type": item_type,
        "title": title,
        "dueDate": due_date,
        "summary": str(result.get("summary") or "").strip()[:300],
        "confidence": confidence,
        "transactionKind": transaction_kind,
        "amount": amount,
        "counterparty": str(result.get("counterparty") or "").strip()[:100],
    }


def classify_with_deepseek(raw_text: str) -> dict:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("DeepSeek API 尚未配置")
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    today = date.today().isoformat()
    system_prompt = f"""你是个人工作空间的收件箱分类器。今天是 {today}。
只返回 JSON 对象，不要 Markdown。字段必须为：
type: task|transaction|content|project|note；
title: 精炼后的中文标题；
dueDate: YYYY-MM-DD 或空字符串；
summary: 一句分类理由；
confidence: 0 到 1。
如果是 transaction，额外返回 transactionKind: income|expense、amount: 数字或 null、counterparty: 对方或空字符串；其他类型也保留这三个字段为空。
出现“今天要、需要、提醒、完成、待办、记得”等明确行动时优先判为 task；内容选题或创作灵感判为 content；真实收支记录判为 transaction。不要凭空补充金额、日期或事实。"""
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": raw_text[:1000]},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
        "max_tokens": 350,
    }, ensure_ascii=False).encode("utf-8")
    request = Request(
        f"{base_url}/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=25) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"DeepSeek 请求失败（HTTP {exc.code}）") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError("无法连接 DeepSeek，请稍后重试") from exc
    try:
        content = payload["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.I)
        return normalize_classification(json.loads(content), raw_text)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("DeepSeek 返回了无法识别的分类结果") from exc


def find_codex_binary() -> str:
    candidates = [
        os.environ.get("CODEX_CLI_PATH", "").strip(),
        shutil.which("codex") or "",
        "/Applications/ChatGPT.app/Contents/Resources/codex",
        "/Applications/Codex.app/Contents/Resources/codex",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise RuntimeError("这台 Mac 没有找到 Codex CLI")


def classify_with_codex(raw_text: str) -> dict:
    codex_binary = find_codex_binary()
    schema_path = APP_DIR / "codex-wechat-schema.json"
    if not schema_path.exists():
        raise RuntimeError("缺少 Codex 微信整理规则文件")
    today = date.today().isoformat()
    prompt = f"""你是“序 XU”个人工作台的微信收件助手。今天是 {today}。
理解用户从微信发来的这条记录，将它整理成结构化结果。只依据原文，不补造事实。
type 只能是 task、transaction、content、project、note：
- 有明确行动、提醒、截止时间的内容优先为 task；相对日期换算为 YYYY-MM-DD。
- 已发生的真实收入或支出为 transaction；没有明确金额时不要猜。
- 选题、脚本、创作灵感为 content；持续推进的完整事项为 project；其余为 note。
- title 使用简洁自然的中文；summary 用一句话解释为什么这样整理。

微信原文：{raw_text[:1000]}"""
    allowed_env_names = {
        "HOME", "CODEX_HOME", "PATH", "TMPDIR", "LANG", "LC_ALL",
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
        "http_proxy", "https_proxy", "all_proxy", "no_proxy",
    }
    child_env = {key: value for key, value in os.environ.items() if key in allowed_env_names}
    with tempfile.TemporaryDirectory(prefix="xu-codex-wechat-") as temp_dir:
        output_path = Path(temp_dir) / "result.json"
        command = [
            codex_binary,
            "exec",
            "--ephemeral",
            "--sandbox", "read-only",
            "--ignore-rules",
            "--skip-git-repo-check",
            "--disable", "plugins",
            "--disable", "remote_plugin",
            "--disable", "plugin_sharing",
            "--disable", "shell_tool",
            "-c", "mcp_servers={}",
            "--output-schema", str(schema_path),
            "--output-last-message", str(output_path),
            "-C", temp_dir,
            "-",
        ]
        try:
            result = subprocess.run(
                command,
                input=prompt,
                text=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                env=child_env,
                timeout=120,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Codex 整理超时，请稍后重试") from exc
        if result.returncode != 0 or not output_path.exists():
            detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "未知错误"
            raise RuntimeError(f"Codex 整理失败：{detail[:180]}")
        try:
            return normalize_classification(json.loads(output_path.read_text(encoding="utf-8")), raw_text)
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("Codex 返回了无法识别的整理结果") from exc


def classify_inbox_record(db: sqlite3.Connection, inbox_id: int, processor: str = "deepseek") -> dict:
    row = db.execute("SELECT id, raw_text FROM inbox WHERE id=?", (inbox_id,)).fetchone()
    if not row:
        raise ValueError("收件箱记录不存在")
    analysis = classify_with_codex(row["raw_text"]) if processor == "codex" else classify_with_deepseek(row["raw_text"])
    db.execute(
        "UPDATE inbox SET inferred_type=?, status='review', analysis_json=? WHERE id=?",
        (analysis["type"], json.dumps(analysis, ensure_ascii=False), inbox_id),
    )
    return analysis


def env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def wechat_allowed_openids() -> set[str]:
    raw_value = os.environ.get("WECHAT_ALLOWED_OPENIDS", "")
    return {item.strip() for item in re.split(r"[,\s]+", raw_value) if item.strip()}


def wechat_processor() -> str:
    processor = os.environ.get("WECHAT_PROCESSOR", "codex").strip().lower()
    return processor if processor in {"codex", "deepseek", "manual"} else "codex"


def wechat_processor_ready(processor: str) -> bool:
    if processor == "codex":
        try:
            find_codex_binary()
            return True
        except RuntimeError:
            return False
    if processor == "deepseek":
        return bool(os.environ.get("DEEPSEEK_API_KEY", "").strip())
    return False


def wechat_status_payload(db: sqlite3.Connection) -> dict:
    summary = db.execute(
        "SELECT COUNT(*) AS count, MAX(received_at) AS last_received_at FROM wechat_messages"
    ).fetchone()
    return {
        "configured": bool(os.environ.get("WECHAT_TOKEN", "").strip()),
        "autoClassify": env_flag("WECHAT_AUTO_CLASSIFY", True),
        "processor": wechat_processor(),
        "codexAvailable": bool(shutil.which("codex") or Path("/Applications/ChatGPT.app/Contents/Resources/codex").exists()),
        "allowedOpenIds": len(wechat_allowed_openids()),
        "receivedCount": int(summary["count"]),
        "lastReceivedAt": summary["last_received_at"],
    }


def classify_inbox_async(inbox_id: int, processor: str) -> None:
    def worker() -> None:
        try:
            # Keep Codex calls sequential so a burst of messages cannot start many paid runs at once.
            with WECHAT_CLASSIFY_LOCK, connect() as db:
                classify_inbox_record(db, inbox_id, processor)
        except Exception as exc:
            print(f"微信消息 {inbox_id} 自动分类失败：{exc}")

    threading.Thread(target=worker, daemon=True, name=f"wechat-classify-{inbox_id}").start()


def month_bounds(month: str | None = None) -> tuple[str, str, str]:
    month = month or date.today().strftime("%Y-%m")
    start = date.fromisoformat(f"{month}-01")
    next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return month, start.isoformat(), next_month.isoformat()


def finance_payload(db: sqlite3.Connection, month: str | None = None) -> dict:
    month, start, end = month_bounds(month)
    totals = db.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN kind='income' THEN amount END), 0) AS income,
            COALESCE(SUM(CASE WHEN kind='expense' THEN amount END), 0) AS expense
        FROM transactions WHERE transaction_date >= ? AND transaction_date < ?
        """,
        (start, end),
    ).fetchone()
    all_time = db.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN kind='income' THEN amount ELSE -amount END), 0) AS movement
        FROM transactions
        """
    ).fetchone()["movement"]
    opening = db.execute("SELECT COALESCE(SUM(opening_balance), 0) FROM accounts").fetchone()[0]
    breakdown = [
        row_dict(row)
        for row in db.execute(
            """
            SELECT c.id, c.name, c.color, ROUND(SUM(t.amount), 2) AS amount
            FROM transactions t JOIN categories c ON c.id=t.category_id
            WHERE t.kind='expense' AND t.transaction_date >= ? AND t.transaction_date < ?
            GROUP BY c.id, c.name, c.color ORDER BY amount DESC
            """,
            (start, end),
        )
    ]
    budget_row = db.execute("SELECT amount FROM monthly_budgets WHERE month=?", (month,)).fetchone()
    budget = round(float(budget_row["amount"]), 2) if budget_row else 15000
    category_budgets = []
    for row in db.execute(
        """
        SELECT c.id, c.name, c.color, b.limit_amount,
               COALESCE(SUM(t.amount), 0) AS spent
        FROM categories c
        LEFT JOIN budgets b ON b.category_id=c.id AND b.month=?
        LEFT JOIN transactions t ON t.category_id=c.id AND t.kind='expense'
             AND t.transaction_date >= ? AND t.transaction_date < ?
        WHERE c.kind='expense'
        GROUP BY c.id, c.name, c.color, b.limit_amount
        ORDER BY CASE
            WHEN c.name IN ('饮食', '餐饮') THEN 0
            WHEN c.name IN ('工作必要开支', '项目成本', '工作支出') THEN 1
            ELSE 2 END, c.id
        """,
        (month, start, end),
    ):
        limit_amount = None if row["limit_amount"] is None else round(float(row["limit_amount"]), 2)
        spent = round(float(row["spent"]), 2)
        remaining = None if limit_amount is None else round(limit_amount - spent, 2)
        percent = 0 if not limit_amount else min(100, round((spent / limit_amount) * 100))
        category_budgets.append({
            "categoryId": row["id"],
            "name": row["name"],
            "color": row["color"],
            "budget": limit_amount,
            "spent": spent,
            "remaining": remaining,
            "percent": percent,
            "configured": limit_amount is not None,
        })
    allocated_budget = round(sum(item["budget"] or 0 for item in category_budgets), 2)
    return {
        "month": month,
        "income": round(totals["income"], 2),
        "expense": round(totals["expense"], 2),
        "net": round(totals["income"] - totals["expense"], 2),
        "netWorth": round(opening + all_time, 2),
        "receivable": 0,
        "budget": budget,
        "budgetRemaining": round(budget - totals["expense"], 2),
        "allocatedBudget": allocated_budget,
        "unallocatedBudget": round(budget - allocated_budget, 2),
        "categoryBudgets": category_budgets,
        "breakdown": breakdown,
    }


def exercise_payload(db: sqlite3.Connection) -> list[dict]:
    return [
        row_dict(row)
        for row in db.execute(
            """
            SELECT id, exercise_date AS date, activity, duration_minutes AS durationMinutes,
                   note, created_at AS createdAt, updated_at AS updatedAt
            FROM exercise_checkins ORDER BY exercise_date DESC, id DESC LIMIT 400
            """
        )
    ]


def validate_aesthetic_item(payload: dict, current: sqlite3.Row | None = None) -> dict:
    def value(key: str, default: str = "") -> str:
        if key in payload:
            return str(payload.get(key) or "").strip()
        return str(current[key] if current is not None else default).strip()

    title = value("title")
    folder = value("folder", "instinct")
    if not title:
        raise ValueError("收藏标题不能为空")
    if folder not in AESTHETIC_FOLDERS:
        raise ValueError("请选择有效的审美文件夹")

    def web_url(payload_key: str, database_key: str, label: str, allow_local_image: bool = False) -> str:
        if payload_key in payload:
            raw = str(payload.get(payload_key) or "").strip()
        else:
            raw = str(current[database_key] if current is not None else "").strip()
        if not raw:
            return ""
        if allow_local_image and re.fullmatch(r"/api/aesthetic-images/[a-f0-9]{32}\.(?:jpg|png|webp|gif)", raw):
            return raw
        parsed = urlparse(raw)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"{label}需要是完整的 http 或 https 链接")
        return raw[:2000]

    return {
        "title": title[:200],
        "folder": folder,
        "sourceUrl": web_url("sourceUrl", "source_url", "来源链接"),
        "imageUrl": web_url("imageUrl", "image_url", "图片链接", allow_local_image=True),
        "note": value("note")[:1000],
    }


def uploaded_aesthetic_path(image_url: str) -> Path | None:
    match = re.fullmatch(r"/api/aesthetic-images/([a-f0-9]{32}\.(?:jpg|png|webp|gif))", str(image_url or ""))
    return AESTHETIC_UPLOAD_DIR / match.group(1) if match else None


def remove_uploaded_aesthetic_image(image_url: str) -> None:
    path = uploaded_aesthetic_path(image_url)
    if path and path.is_file():
        path.unlink()


def basic_aesthetic_profile(rows: list[sqlite3.Row]) -> dict:
    counts = {key: 0 for key in AESTHETIC_FOLDERS}
    noted = 0
    for row in rows:
        counts[row["folder"]] = counts.get(row["folder"], 0) + 1
        noted += bool(str(row["note"] or "").strip())
    ranked = sorted(counts, key=lambda key: counts[key], reverse=True)
    used = [key for key in ranked if counts[key]]
    keywords = [AESTHETIC_FOLDER_LABELS[key].replace("喜欢的", "") for key in used[:4]]
    if not rows:
        summary = "你的审美档案还没有开始。先收藏几个真正让你停下来的画面。"
        patterns = ["收藏 3 条后，AI 会开始寻找你反复偏爱的视觉特征。"]
    else:
        leader = used[0]
        summary = f"目前你最常留下的是“{AESTHETIC_FOLDER_LABELS[leader]}”，已占 {counts[leader]} 条。继续写下喜欢的原因，画像会越来越具体。"
        patterns = [f"{AESTHETIC_FOLDER_LABELS[key]}：{counts[key]} 条" for key in used[:3]]
        patterns.append(f"{noted} 条收藏写下了喜欢的原因" if noted else "还没有记录喜欢的原因")
    return {
        "summary": summary,
        "keywords": keywords or ["等待积累"],
        "patterns": patterns[:4],
        "nextQuestion": "下次收藏时，试着写下是颜色、留白、层级还是情绪让你停了下来？",
        "mode": "basic",
        "itemCount": len(rows),
        "updatedAt": "",
    }


def aesthetic_profile_payload(db: sqlite3.Connection) -> dict:
    rows = db.execute("SELECT id, title, folder, source_url, note FROM aesthetic_items ORDER BY id DESC LIMIT 300").fetchall()
    stored = db.execute(
        "SELECT profile_json, item_count, updated_at FROM aesthetic_profile WHERE profile_key='default'"
    ).fetchone()
    if not stored:
        profile = basic_aesthetic_profile(rows)
        profile.update({"itemCount": 0, "currentItemCount": len(rows), "stale": bool(rows), "generated": False})
        return profile
    try:
        profile = json.loads(stored["profile_json"])
    except json.JSONDecodeError:
        return basic_aesthetic_profile(rows)
    profile.update({
        "itemCount": int(stored["item_count"]),
        "currentItemCount": len(rows),
        "updatedAt": stored["updated_at"],
        "stale": int(stored["item_count"]) != len(rows),
        "generated": True,
    })
    return profile


def refresh_aesthetic_profile(db: sqlite3.Connection) -> dict:
    rows = db.execute(
        "SELECT id, title, folder, source_url, note FROM aesthetic_items ORDER BY id DESC LIMIT 300"
    ).fetchall()
    profile = basic_aesthetic_profile(rows)
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if api_key and rows:
        observations = [{
            "title": row["title"],
            "folder": AESTHETIC_FOLDER_LABELS.get(row["folder"], row["folder"]),
            "note": row["note"],
            "sourceHost": urlparse(row["source_url"]).netloc if row["source_url"] else "",
        } for row in rows]
        body = json.dumps({
            "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
            "messages": [
                {
                    "role": "system",
                    "content": "你是审美研究助手。只依据用户真实收藏的分类、标题和理由，归纳其视觉偏好；不要假装看过图片，不要补造颜色或风格。只返回 JSON：summary 为 70-130 字自然中文；keywords 为 4-7 个短词；patterns 为 3-5 条有证据的具体观察；nextQuestion 为一个能帮助用户更了解自己审美的问题。语气克制，不吹捧。",
                },
                {"role": "user", "content": json.dumps(observations, ensure_ascii=False)},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
            "max_tokens": 900,
        }, ensure_ascii=False).encode("utf-8")
        request = Request(
            f"{os.environ.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com').rstrip('/')}/chat/completions",
            data=body,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=35) as response:
                payload = json.loads(response.read().decode("utf-8"))
            content = payload["choices"][0]["message"]["content"].strip()
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.I)
            result = json.loads(content)
            summary = clean_feed_text(result.get("summary"), 320)
            keywords = [clean_feed_text(item, 30) for item in result.get("keywords", []) if clean_feed_text(item, 30)][:7]
            patterns = [clean_feed_text(item, 180) for item in result.get("patterns", []) if clean_feed_text(item, 180)][:5]
            next_question = clean_feed_text(result.get("nextQuestion"), 180)
            if summary and keywords and patterns:
                profile.update({
                    "summary": summary,
                    "keywords": keywords,
                    "patterns": patterns,
                    "nextQuestion": next_question or profile["nextQuestion"],
                    "mode": "ai",
                })
        except Exception:
            profile["warning"] = "AI 暂时没有连接成功，当前显示本地基础画像。"
    profile_json = {key: value for key, value in profile.items() if key not in {"itemCount", "updatedAt"}}
    db.execute(
        """
        INSERT INTO aesthetic_profile(profile_key, profile_json, item_count) VALUES ('default', ?, ?)
        ON CONFLICT(profile_key) DO UPDATE SET profile_json=excluded.profile_json,
            item_count=excluded.item_count, updated_at=CURRENT_TIMESTAMP
        """,
        (json.dumps(profile_json, ensure_ascii=False), len(rows)),
    )
    return aesthetic_profile_payload(db)


def fetch_public_url(url: str, *, timeout: int = 12) -> bytes:
    request = Request(url, headers={"User-Agent": "XU-Workspace/1.0 (+local Vibe Radar)"})
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def clean_feed_text(value: object, limit: int = 280) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    return re.sub(r"\s+", " ", text).strip()[:limit]


def published_on_local_date(value: object, target: date) -> bool:
    raw = str(value or "").strip()
    if not raw:
        return False
    try:
        published = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if published.tzinfo is not None:
            published = published.astimezone()
        return published.date() == target
    except ValueError:
        return raw[:10] == target.isoformat()


def basic_vibe_summary(item: dict) -> str:
    if item.get("kind") == "project":
        language = item.get("language") or "多种技术"
        return f"这是一个使用{language}开发的 Vibe Coding 项目，目前获得 {int(item.get('stars') or 0)} 个 Star。"
    if item.get("kind") == "discussion":
        return f"这是 Hacker News 上的开发者讨论，目前有 {int(item.get('comments') or 0)} 条评论，可以先看观点碰撞。"
    return f"这是一篇来自{item.get('source') or '全球媒体'}的 Vibe Coding 文章，主要讨论相关产品、趋势或实践。"


def enrich_vibe_summaries(items: list[dict]) -> tuple[str, str]:
    for item in items:
        item["chineseSummary"] = basic_vibe_summary(item)
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key or not items:
        return "basic", ""

    compact_items = [
        {
            "index": index,
            "kind": item.get("kind"),
            "source": item.get("source"),
            "title": item.get("title"),
            "description": item.get("description"),
            "language": item.get("language"),
        }
        for index, item in enumerate(items)
    ]
    body = json.dumps({
        "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
        "messages": [
            {
                "role": "system",
                "content": "你是 Vibe Coding 情报编辑。把每条英文信息概括成一句自然中文，明确说明它是什么、解决什么问题或文章在讨论什么。每句 25 到 55 个汉字，不要营销话术，不要重复标题；信息不足时如实说信息有限。只返回 JSON：{\"summaries\":[{\"index\":0,\"summary\":\"...\"}]}，必须覆盖所有 index。",
            },
            {"role": "user", "content": json.dumps(compact_items, ensure_ascii=False)},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
        "max_tokens": 4500,
    }, ensure_ascii=False).encode("utf-8")
    request = Request(
        f"{os.environ.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com').rstrip('/')}/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=40) as response:
            payload = json.loads(response.read().decode("utf-8"))
        content = payload["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.I)
        summaries = json.loads(content).get("summaries", [])
        applied = 0
        for entry in summaries:
            index = int(entry.get("index", -1))
            summary = clean_feed_text(entry.get("summary"), 140)
            if 0 <= index < len(items) and summary:
                items[index]["chineseSummary"] = summary
                applied += 1
        return ("ai", "") if applied == len(items) else ("mixed", "部分内容暂时使用基础中文说明")
    except Exception:
        return "basic", "中文概括暂时使用基础说明"


def vibe_hot_score(item: dict, now: datetime) -> int:
    try:
        published = datetime.fromisoformat(str(item.get("publishedAt") or "").replace("Z", "+00:00"))
        if published.tzinfo is not None:
            published = published.astimezone().replace(tzinfo=None)
        age_hours = max(0, (now - published).total_seconds() / 3600)
    except ValueError:
        age_hours = 168
    recency = max(0, 168 - age_hours) / 6
    popularity = int(item.get("stars") or 0) * 4 + int(item.get("points") or 0) * 2 + int(item.get("comments") or 0) * 3
    return round(popularity + recency + (15 if item.get("isToday") else 0))


def fetch_github_vibe_items(since: date) -> list[dict]:
    query = f'"vibe coding" created:>={since.isoformat()}'
    url = "https://api.github.com/search/repositories?" + urlencode({
        "q": query, "sort": "updated", "order": "desc", "per_page": 20,
    })
    payload = json.loads(fetch_public_url(url).decode("utf-8"))
    return [{
        "source": "GitHub",
        "kind": "project",
        "title": item.get("full_name") or item.get("name") or "Untitled project",
        "url": item.get("html_url", ""),
        "description": clean_feed_text(item.get("description") or "新发布的 Vibe Coding 项目"),
        "author": (item.get("owner") or {}).get("login", ""),
        "publishedAt": item.get("created_at", ""),
        "stars": int(item.get("stargazers_count") or 0),
        "language": item.get("language") or "",
    } for item in payload.get("items", [])]


def fetch_hn_vibe_items(since: date) -> list[dict]:
    since_timestamp = int(datetime.combine(since, datetime.min.time()).timestamp())
    url = "https://hn.algolia.com/api/v1/search_by_date?" + urlencode({
        "query": "vibe coding", "tags": "story", "hitsPerPage": 25,
        "numericFilters": f"created_at_i>{since_timestamp}",
    })
    payload = json.loads(fetch_public_url(url).decode("utf-8"))
    items = []
    for item in payload.get("hits", []):
        object_id = str(item.get("objectID") or "")
        items.append({
            "source": "Hacker News",
            "kind": "discussion",
            "title": clean_feed_text(item.get("title") or item.get("story_title"), 180),
            "url": item.get("url") or f"https://news.ycombinator.com/item?id={object_id}",
            "description": clean_feed_text(item.get("story_text") or "全球开发者正在讨论这项 Vibe Coding 动态。"),
            "author": item.get("author") or "",
            "publishedAt": item.get("created_at") or "",
            "points": int(item.get("points") or 0),
            "comments": int(item.get("num_comments") or 0),
        })
    return items


def fetch_news_vibe_items() -> list[dict]:
    url = "https://news.google.com/rss/search?" + urlencode({
        "q": '"vibe coding" when:7d', "hl": "en-US", "gl": "US", "ceid": "US:en",
    })
    root = ET.fromstring(fetch_public_url(url))
    items = []
    for node in root.findall("./channel/item")[:30]:
        published = node.findtext("pubDate") or ""
        try:
            published = parsedate_to_datetime(published).isoformat()
        except (TypeError, ValueError):
            pass
        source_node = node.find("source")
        items.append({
            "source": clean_feed_text(source_node.text if source_node is not None else "Global News", 60),
            "kind": "article",
            "title": clean_feed_text(node.findtext("title"), 180),
            "url": node.findtext("link") or "",
            "description": "来自全球媒体与创作者的 Vibe Coding 相关文章。",
            "author": "",
            "publishedAt": published,
        })
    return items


def vibe_feed_payload(db: sqlite3.Connection, force: bool = False) -> dict:
    cache = db.execute(
        "SELECT payload_json, fetched_at FROM vibe_feed_cache WHERE cache_key='global-v2'"
    ).fetchone()
    if cache:
        try:
            cached_at = datetime.fromisoformat(cache["fetched_at"])
            age = (datetime.utcnow() - cached_at).total_seconds()
            if age < (60 if force else 1800):
                payload = json.loads(cache["payload_json"])
                payload["cached"] = True
                return payload
        except (ValueError, json.JSONDecodeError):
            pass

    with VIBE_REFRESH_LOCK:
        # A concurrent request may have completed while this request waited for the lock.
        latest = db.execute(
            "SELECT payload_json, fetched_at FROM vibe_feed_cache WHERE cache_key='global-v2'"
        ).fetchone()
        if latest and (not cache or latest["fetched_at"] != cache["fetched_at"]):
            try:
                payload = json.loads(latest["payload_json"])
                payload["cached"] = True
                return payload
            except json.JSONDecodeError:
                pass
        today = date.today()
        since = today - timedelta(days=7)
        fetchers = [
            ("GitHub", lambda: fetch_github_vibe_items(since)),
            ("Hacker News", lambda: fetch_hn_vibe_items(since)),
            ("Global News", fetch_news_vibe_items),
        ]
        collected, errors = [], []
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(fetcher): name for name, fetcher in fetchers}
            for future in as_completed(futures):
                try:
                    collected.extend(future.result())
                except Exception as exc:
                    errors.append(f"{futures[future]} 暂时不可用：{type(exc).__name__}")
        seen, items = set(), []
        for item in collected:
            url = str(item.get("url") or "")
            title = clean_feed_text(item.get("title"), 180)
            if not title or not url.startswith("https://"):
                continue
            dedupe_key = re.sub(r"\W+", "", title.lower())[:100] or url
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            published = str(item.get("publishedAt") or "")
            item["title"] = title
            item["isToday"] = published_on_local_date(published, today)
            item["id"] = hashlib.sha256(f"{item['source']}|{url}".encode()).hexdigest()[:16]
            items.append(item)
        items.sort(key=lambda item: str(item.get("publishedAt") or ""), reverse=True)
        items.sort(key=lambda item: item["isToday"], reverse=True)
        items = items[:60]
        summary_mode, summary_warning = enrich_vibe_summaries(items)
        ranked = sorted(items, key=lambda item: vibe_hot_score(item, datetime.now()), reverse=True)
        for rank, item in enumerate(ranked[:10], 1):
            item["hotRank"] = rank
            item["hotScore"] = vibe_hot_score(item, datetime.now())
        if summary_warning:
            errors.append(summary_warning)
        payload = {
            "date": today.isoformat(),
            "fetchedAt": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "cached": False,
            "items": items,
            "stats": {
                "today": sum(1 for item in items if item["isToday"]),
                "projects": sum(1 for item in items if item["kind"] == "project"),
                "articles": sum(1 for item in items if item["kind"] == "article"),
                "discussions": sum(1 for item in items if item["kind"] == "discussion"),
            },
            "errors": errors,
            "summaryMode": summary_mode,
        }
        if not items and cache:
            fallback = json.loads(cache["payload_json"])
            fallback.update({"cached": True, "errors": errors or ["网络不可用，正在显示上一次结果"]})
            return fallback
        db.execute(
            """
            INSERT INTO vibe_feed_cache(cache_key, payload_json, fetched_at) VALUES ('global-v2', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(cache_key) DO UPDATE SET payload_json=excluded.payload_json, fetched_at=CURRENT_TIMESTAMP
            """,
            (json.dumps(payload, ensure_ascii=False),),
        )
        return payload


def validate_exercise(payload: dict) -> dict:
    exercise_date = str(payload.get("date", "")).strip()
    date.fromisoformat(exercise_date)
    activity = str(payload.get("activity", "")).strip()
    if not activity:
        raise ValueError("请填写今天主要运动了什么")
    raw_duration = payload.get("durationMinutes")
    duration = None if raw_duration in {None, ""} else int(raw_duration)
    if duration is not None and not 0 <= duration <= 1440:
        raise ValueError("运动时长需要在 0 到 1440 分钟之间")
    return {
        "date": exercise_date,
        "activity": activity[:120],
        "durationMinutes": duration,
        "note": str(payload.get("note", "")).strip()[:500],
    }


def transactions_payload(db: sqlite3.Connection, limit: int = 100) -> list[dict]:
    return [
        row_dict(row)
        for row in db.execute(
            """
            SELECT t.id, t.kind, t.amount, t.transaction_date AS date,
                   t.category_id AS categoryId, c.name AS category, c.color,
                   t.account_id AS accountId, a.name AS account,
                   t.project, t.counterparty, t.note
            FROM transactions t
            JOIN categories c ON c.id=t.category_id
            JOIN accounts a ON a.id=t.account_id
            ORDER BY t.transaction_date DESC, t.id DESC LIMIT ?
            """,
            (limit,),
        )
    ]


def read_json(handler: SimpleHTTPRequestHandler) -> dict:
    size = int(handler.headers.get("Content-Length", "0"))
    if size > 5_000_000:
        raise ValueError("请求内容过大")
    raw = handler.rfile.read(size)
    return json.loads(raw or b"{}")


def validate_transaction(payload: dict, db: sqlite3.Connection) -> dict:
    kind = str(payload.get("kind", "")).strip()
    if kind not in {"income", "expense"}:
        raise ValueError("收支类型无效")
    try:
        amount = round(float(payload.get("amount", 0)), 2)
    except (TypeError, ValueError) as exc:
        raise ValueError("金额格式无效") from exc
    if amount <= 0:
        raise ValueError("金额必须大于 0")
    tx_date = str(payload.get("date", "")).strip()
    date.fromisoformat(tx_date)
    category_id = int(payload.get("categoryId", 0))
    account_id = int(payload.get("accountId", 0))
    category = db.execute("SELECT id FROM categories WHERE id=? AND kind=?", (category_id, kind)).fetchone()
    account = db.execute("SELECT id FROM accounts WHERE id=?", (account_id,)).fetchone()
    if not category or not account:
        raise ValueError("账户或分类无效")
    return {
        "kind": kind,
        "amount": amount,
        "date": tx_date,
        "categoryId": category_id,
        "accountId": account_id,
        "project": str(payload.get("project", "")).strip()[:100],
        "counterparty": str(payload.get("counterparty", "")).strip()[:100],
        "note": str(payload.get("note", "")).strip()[:300],
    }


def ensure_named_record(db: sqlite3.Connection, table: str, name: str, kind: str | None = None) -> int:
    if table == "accounts":
        row = db.execute("SELECT id FROM accounts WHERE name=?", (name,)).fetchone()
        if not row:
            db.execute("INSERT INTO accounts(name, type) VALUES (?, 'other')", (name,))
    else:
        row = db.execute("SELECT id FROM categories WHERE name=? AND kind=?", (name, kind)).fetchone()
        if not row:
            color = "#386e5a" if kind == "income" else "#c6cacb"
            db.execute("INSERT INTO categories(name, kind, color) VALUES (?, ?, ?)", (name, kind, color))
    row = db.execute(
        f"SELECT id FROM {table} WHERE name=?" + (" AND kind=?" if table == "categories" else ""),
        (name, kind) if table == "categories" else (name,),
    ).fetchone()
    return int(row["id"])


def import_csv(db: sqlite3.Connection, text: str) -> dict:
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    required = {"日期", "类型", "金额", "分类", "账户"}
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
        raise ValueError("CSV 需要包含：日期、类型、金额、分类、账户")
    imported = 0
    errors = []
    for line_number, row in enumerate(reader, start=2):
        try:
            kind_text = row["类型"].strip().lower()
            kind = "income" if kind_text in {"收入", "income", "入账"} else "expense"
            amount = abs(float(row["金额"].replace(",", "").replace("¥", "").strip()))
            tx_date = date.fromisoformat(row["日期"].strip()).isoformat()
            account_id = ensure_named_record(db, "accounts", row["账户"].strip() or "其他账户")
            category_id = ensure_named_record(db, "categories", row["分类"].strip() or ("其他收入" if kind == "income" else "其他支出"), kind)
            db.execute(
                """
                INSERT INTO transactions(kind, amount, transaction_date, category_id, account_id, project, counterparty, note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (kind, amount, tx_date, category_id, account_id, row.get("项目", "").strip(), row.get("对方", "").strip(), row.get("备注", "").strip()),
            )
            imported += 1
        except Exception as exc:  # Keep valid rows and report invalid ones.
            errors.append(f"第 {line_number} 行：{exc}")
    return {"imported": imported, "errors": errors[:20]}


class XUHandler(SimpleHTTPRequestHandler):
    server_version = "XUWorkspace/0.2"

    def is_local_client(self) -> bool:
        raw_host = self.headers.get("Host", "").lower()
        host = raw_host[1:].split("]", 1)[0] if raw_host.startswith("[") else raw_host.split(":", 1)[0]
        return self.client_address[0] in {"127.0.0.1", "::1"} and host in {"127.0.0.1", "localhost", "::1"}

    def is_authorized(self) -> bool:
        if self.is_local_client():
            return True
        raw_cookie = self.headers.get("Cookie", "")
        try:
            cookie = SimpleCookie(raw_cookie)
            supplied = cookie.get(MOBILE_COOKIE)
            token = supplied.value if supplied else ""
        except Exception:
            token = ""
        expected = str(MOBILE_ACCESS["session_token"])
        return bool(token and expected and hmac.compare_digest(token, expected))

    def require_authorized(self) -> bool:
        if self.is_authorized():
            return True
        self.send_error_json("请先输入 Mac 上显示的手机访问码", HTTPStatus.UNAUTHORIZED, code="mobile_auth_required")
        return False

    def end_headers(self) -> None:
        if not urlparse(self.path).path.startswith("/api/"):
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
        super().end_headers()

    def log_message(self, format: str, *args) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}")

    def send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK, headers: dict[str, str] | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST, code: str = "") -> None:
        payload = {"error": message}
        if code:
            payload["code"] = code
        self.send_json(payload, status)

    def send_text(
        self,
        content: str,
        status: HTTPStatus = HTTPStatus.OK,
        content_type: str = "text/plain; charset=utf-8",
    ) -> None:
        body = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_binary(self, body: bytes, content_type: str, cache_control: str = "private, max-age=31536000") -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache_control)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def handle_aesthetic_upload(self) -> None:
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self.send_error_json("图片大小无效")
        if size <= 0 or size > 8 * 1024 * 1024 + 128 * 1024:
            return self.send_error_json("图片不能超过 8 MB", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        content_type = self.headers.get("Content-Type", "")
        if not content_type.lower().startswith("multipart/form-data;"):
            return self.send_error_json("请选择一张图片上传")
        raw = self.rfile.read(size)
        message = BytesParser(policy=email_policy).parsebytes(
            f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + raw
        )
        image = None
        for part in message.iter_parts():
            if part.get_param("name", header="content-disposition") == "image":
                image = part.get_payload(decode=True)
                break
        if not image:
            return self.send_error_json("没有读取到图片内容")
        if len(image) > 8 * 1024 * 1024:
            return self.send_error_json("图片不能超过 8 MB", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        signatures = [
            (lambda data: data.startswith(b"\xff\xd8\xff"), "jpg", "image/jpeg"),
            (lambda data: data.startswith(b"\x89PNG\r\n\x1a\n"), "png", "image/png"),
            (lambda data: len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP", "webp", "image/webp"),
            (lambda data: data.startswith((b"GIF87a", b"GIF89a")), "gif", "image/gif"),
        ]
        match = next(((extension, mime) for check, extension, mime in signatures if check(image)), None)
        if not match:
            return self.send_error_json("目前支持 JPG、PNG、WebP 和 GIF 图片")
        extension, mime = match
        AESTHETIC_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"{secrets.token_hex(16)}.{extension}"
        path = AESTHETIC_UPLOAD_DIR / filename
        path.write_bytes(image)
        self.send_json({"url": f"/api/aesthetic-images/{filename}", "size": len(image), "type": mime}, HTTPStatus.CREATED)

    def verify_wechat_signature(self, parsed) -> bool:
        token = os.environ.get("WECHAT_TOKEN", "").strip()
        if not token:
            return False
        query = parse_qs(parsed.query)
        signature = query.get("signature", [""])[0]
        timestamp = query.get("timestamp", [""])[0]
        nonce = query.get("nonce", [""])[0]
        if not signature or not timestamp or not nonce:
            return False
        digest = hashlib.sha1("".join(sorted([token, timestamp, nonce])).encode("utf-8")).hexdigest()
        return hmac.compare_digest(digest, signature)

    def handle_wechat_verification(self, parsed) -> None:
        if not os.environ.get("WECHAT_TOKEN", "").strip():
            return self.send_text("微信接入尚未配置", HTTPStatus.SERVICE_UNAVAILABLE)
        if not self.verify_wechat_signature(parsed):
            return self.send_text("签名验证失败", HTTPStatus.FORBIDDEN)
        echo = parse_qs(parsed.query).get("echostr", [""])[0]
        self.send_text(echo)

    def wechat_reply_xml(self, to_user: str, from_user: str, content: str) -> str:
        root = ET.Element("xml")
        ET.SubElement(root, "ToUserName").text = to_user
        ET.SubElement(root, "FromUserName").text = from_user
        ET.SubElement(root, "CreateTime").text = str(int(time.time()))
        ET.SubElement(root, "MsgType").text = "text"
        ET.SubElement(root, "Content").text = content
        return ET.tostring(root, encoding="unicode", short_empty_elements=False)

    def handle_wechat_callback(self, parsed) -> None:
        if not os.environ.get("WECHAT_TOKEN", "").strip():
            return self.send_text("微信接入尚未配置", HTTPStatus.SERVICE_UNAVAILABLE)
        if not self.verify_wechat_signature(parsed):
            return self.send_text("签名验证失败", HTTPStatus.FORBIDDEN)
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self.send_text("无效请求", HTTPStatus.BAD_REQUEST)
        if size <= 0 or size > 65536:
            return self.send_text("消息大小无效", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        try:
            root = ET.fromstring(self.rfile.read(size))
        except ET.ParseError:
            return self.send_text("XML 格式无效", HTTPStatus.BAD_REQUEST)

        to_user = (root.findtext("ToUserName") or "").strip()
        from_user = (root.findtext("FromUserName") or "").strip()
        message_type = (root.findtext("MsgType") or "").strip().lower()
        content = (root.findtext("Content") or "").strip()[:1000]
        if root.find("Encrypt") is not None:
            return self.send_text("当前仅支持公众号明文模式", HTTPStatus.BAD_REQUEST)
        if not to_user or not from_user:
            return self.send_text("消息字段不完整", HTTPStatus.BAD_REQUEST)

        reply = "目前只支持文字消息，请直接发送你想记录的文字。"
        inbox_id = None
        processor = wechat_processor()
        if message_type == "text" and content:
            allowed = wechat_allowed_openids()
            if allowed and from_user not in allowed:
                reply = "这个微信尚未获得工作台记录权限。"
            else:
                create_time = (root.findtext("CreateTime") or "").strip()
                message_id = (root.findtext("MsgId") or "").strip()
                if not message_id:
                    source = f"{from_user}|{create_time}|{content}"
                    message_id = "fallback-" + hashlib.sha256(source.encode("utf-8")).hexdigest()
                with connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    existing = db.execute(
                        "SELECT inbox_id FROM wechat_messages WHERE message_id=?", (message_id,)
                    ).fetchone()
                    if existing:
                        inbox_id = existing["inbox_id"]
                        reply = "这条消息已经收到，不会重复记录。"
                    else:
                        cursor = db.execute("INSERT INTO inbox(raw_text) VALUES (?)", (content,))
                        inbox_id = int(cursor.lastrowid)
                        db.execute(
                            """
                            INSERT INTO wechat_messages(message_id, open_id, message_type, content, inbox_id)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (message_id, from_user, message_type, content, inbox_id),
                        )
                        if env_flag("WECHAT_AUTO_CLASSIFY", True) and wechat_processor_ready(processor):
                            assistant_name = "Codex" if processor == "codex" else "DeepSeek"
                            reply = f"已收到，正在交给 {assistant_name} 整理并放进「序」工作台。"
                        else:
                            reply = "已收到，已经放进「序」的收件箱，稍后可手动整理。"
                if (
                    inbox_id
                    and not existing
                    and env_flag("WECHAT_AUTO_CLASSIFY", True)
                    and wechat_processor_ready(processor)
                ):
                    classify_inbox_async(inbox_id, processor)

        response_xml = self.wechat_reply_xml(from_user, to_user, reply)
        self.send_text(response_xml, content_type="application/xml; charset=utf-8")

    def handle_mobile_login(self, payload: dict) -> None:
        client_ip = self.client_address[0]
        now = time.monotonic()
        recent = [stamp for stamp in LOGIN_ATTEMPTS.get(client_ip, []) if now - stamp < 60]
        if len(recent) >= 5:
            LOGIN_ATTEMPTS[client_ip] = recent
            self.send_error_json("尝试次数过多，请60秒后再试", HTTPStatus.TOO_MANY_REQUESTS)
            return
        supplied = re.sub(r"\D", "", str(payload.get("code", "")))
        expected = str(MOBILE_ACCESS["access_code"])
        if not supplied or not hmac.compare_digest(supplied, expected):
            recent.append(now)
            LOGIN_ATTEMPTS[client_ip] = recent
            self.send_error_json("访问码不正确")
            return
        LOGIN_ATTEMPTS.pop(client_ip, None)
        cookie = f"{MOBILE_COOKIE}={MOBILE_ACCESS['session_token']}; Path=/; HttpOnly; SameSite=Strict; Max-Age=43200"
        self.send_json({"ok": True}, headers={"Set-Cookie": cookie})

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/wechat/callback":
            return self.handle_wechat_verification(parsed)
        if not parsed.path.startswith("/api/"):
            if parsed.path in {"/xu-workspace", "/xu-workspace/"}:
                self.send_response(HTTPStatus.FOUND)
                self.send_header("Location", "/")
                self.end_headers()
                return
            return super().do_GET()
        if parsed.path == "/api/health":
            payload = {"ok": True}
            if self.is_local_client():
                payload.update({"database": str(DB_PATH), "mobileAccess": bool(MOBILE_ACCESS["enabled"])})
            return self.send_json(payload)
        if parsed.path == "/api/session":
            return self.send_json({"authorized": self.is_authorized(), "local": self.is_local_client()})
        if parsed.path == "/api/mobile-access":
            if not self.is_local_client():
                return self.send_error_json("只能在这台 Mac 上查看手机访问码", HTTPStatus.FORBIDDEN)
            lan_ip = str(MOBILE_ACCESS["lan_ip"])
            url = f"http://{lan_ip}:{MOBILE_ACCESS['port']}/" if lan_ip else ""
            return self.send_json({
                "enabled": bool(MOBILE_ACCESS["enabled"] and lan_ip),
                "url": url,
                "accessCode": MOBILE_ACCESS["access_code"],
            })
        if not self.require_authorized():
            return
        image_match = re.fullmatch(r"/api/aesthetic-images/([a-f0-9]{32}\.(jpg|png|webp|gif))", parsed.path)
        if image_match:
            path = AESTHETIC_UPLOAD_DIR / image_match.group(1)
            if not path.is_file():
                return self.send_error_json("图片不存在", HTTPStatus.NOT_FOUND)
            mime = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp", "gif": "image/gif"}[image_match.group(2)]
            return self.send_binary(path.read_bytes(), mime)
        try:
            with connect() as db:
                if parsed.path == "/api/bootstrap":
                    settings = {row["key"]: row["value"] for row in db.execute("SELECT key, value FROM app_settings")}
                    self.send_json({
                        "summary": finance_payload(db),
                        "transactions": transactions_payload(db),
                        "accounts": [row_dict(r) for r in db.execute("SELECT id, name, type, opening_balance AS openingBalance FROM accounts ORDER BY id")],
                        "categories": [row_dict(r) for r in db.execute("SELECT id, name, kind, color FROM categories ORDER BY kind DESC, id")],
                        "inbox": inbox_payload(db),
                        "tasks": [row_dict(r) for r in db.execute("SELECT id, title, due_date AS dueDate, completed_at AS completedAt, created_at AS createdAt FROM tasks ORDER BY due_date DESC, id DESC LIMIT 200")],
                        "projects": [row_dict(r) for r in db.execute("SELECT id, title, description, status, created_at AS createdAt FROM projects ORDER BY id DESC")],
                        "contentItems": [row_dict(r) for r in db.execute("SELECT id, title, description, status, source_inbox_id AS sourceInboxId, created_at AS createdAt FROM content_items ORDER BY id DESC")],
                        "aestheticItems": [row_dict(r) for r in db.execute("SELECT id, title, folder, source_url AS sourceUrl, image_url AS imageUrl, note, created_at AS createdAt, updated_at AS updatedAt FROM aesthetic_items ORDER BY id DESC")],
                        "aestheticProfile": aesthetic_profile_payload(db),
                        "exerciseCheckins": exercise_payload(db),
                        "notes": [row_dict(r) for r in db.execute("SELECT id, title, body, source_inbox_id AS sourceInboxId, created_at AS createdAt FROM notes ORDER BY id DESC")],
                        "profile": {
                            "displayName": settings.get("display_name", "新朋友"),
                            "workspaceName": settings.get("workspace_name", "我的工作空间"),
                        },
                        "wechatStatus": wechat_status_payload(db),
                        "client": {"local": self.is_local_client()},
                    })
                elif parsed.path == "/api/vibe-feed":
                    force = parse_qs(parsed.query).get("refresh", [""])[0] == "1"
                    self.send_json(vibe_feed_payload(db, force=force))
                else:
                    self.send_error_json("接口不存在", HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self.send_error_json(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/wechat/callback":
            try:
                return self.handle_wechat_callback(parsed)
            except Exception as exc:
                print(f"微信回调处理失败：{exc}")
                return self.send_text("消息处理失败", HTTPStatus.INTERNAL_SERVER_ERROR)
        if parsed.path == "/api/aesthetic-upload":
            if not self.require_authorized():
                return
            return self.handle_aesthetic_upload()
        try:
            payload = read_json(self)
            if parsed.path == "/api/mobile-login":
                return self.handle_mobile_login(payload)
            if not self.require_authorized():
                return
            with connect() as db:
                if parsed.path == "/api/aesthetic-profile/refresh":
                    self.send_json(refresh_aesthetic_profile(db))
                elif parsed.path == "/api/transactions":
                    tx = validate_transaction(payload, db)
                    cursor = db.execute(
                        """
                        INSERT INTO transactions(kind, amount, transaction_date, category_id, account_id, project, counterparty, note)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (tx["kind"], tx["amount"], tx["date"], tx["categoryId"], tx["accountId"], tx["project"], tx["counterparty"], tx["note"]),
                    )
                    self.send_json({"id": cursor.lastrowid}, HTTPStatus.CREATED)
                elif parsed.path == "/api/projects":
                    title = str(payload.get("title", "")).strip()
                    description = str(payload.get("description", "")).strip()
                    status = str(payload.get("status", "todo")).strip()
                    if not title:
                        raise ValueError("项目名称不能为空")
                    if status not in {"todo", "doing", "review"}:
                        raise ValueError("项目状态无效")
                    cursor = db.execute(
                        "INSERT INTO projects(title, description, status) VALUES (?, ?, ?)",
                        (title[:160], description[:500], status),
                    )
                    self.send_json({"id": cursor.lastrowid}, HTTPStatus.CREATED)
                elif parsed.path == "/api/content":
                    title = str(payload.get("title", "")).strip()
                    description = str(payload.get("description", "")).strip()
                    status = str(payload.get("status", "idea")).strip()
                    if not title:
                        raise ValueError("内容标题不能为空")
                    if status not in {"idea", "creating", "ready", "published"}:
                        raise ValueError("内容状态无效")
                    cursor = db.execute(
                        "INSERT INTO content_items(title, description, status) VALUES (?, ?, ?)",
                        (title[:200], description[:800], status),
                    )
                    self.send_json({"id": cursor.lastrowid}, HTTPStatus.CREATED)
                elif parsed.path == "/api/aesthetic-items":
                    item = validate_aesthetic_item(payload)
                    cursor = db.execute(
                        "INSERT INTO aesthetic_items(title, folder, source_url, image_url, note) VALUES (?, ?, ?, ?, ?)",
                        (item["title"], item["folder"], item["sourceUrl"], item["imageUrl"], item["note"]),
                    )
                    self.send_json({"id": cursor.lastrowid}, HTTPStatus.CREATED)
                elif parsed.path == "/api/exercise":
                    exercise = validate_exercise(payload)
                    try:
                        cursor = db.execute(
                            """
                            INSERT INTO exercise_checkins(exercise_date, activity, duration_minutes, note)
                            VALUES (?, ?, ?, ?)
                            """,
                            (exercise["date"], exercise["activity"], exercise["durationMinutes"], exercise["note"]),
                        )
                    except sqlite3.IntegrityError as exc:
                        raise ValueError("这一天已经打卡了，可以点击当日记录进行修改") from exc
                    self.send_json({"id": cursor.lastrowid}, HTTPStatus.CREATED)
                elif parsed.path == "/api/tasks":
                    title = str(payload.get("title", "")).strip()
                    due_date = str(payload.get("dueDate", "")).strip()
                    if not title:
                        raise ValueError("任务内容不能为空")
                    date.fromisoformat(due_date)
                    cursor = db.execute("INSERT INTO tasks(title, due_date) VALUES (?, ?)", (title[:240], due_date))
                    self.send_json({"id": cursor.lastrowid}, HTTPStatus.CREATED)
                elif parsed.path == "/api/import":
                    self.send_json(import_csv(db, str(payload.get("csv", ""))))
                elif parsed.path == "/api/inbox":
                    text = str(payload.get("text", "")).strip()
                    if not text:
                        raise ValueError("记录内容不能为空")
                    cursor = db.execute("INSERT INTO inbox(raw_text) VALUES (?)", (text[:1000],))
                    inbox_id = int(cursor.lastrowid)
                    try:
                        analysis = classify_inbox_record(db, inbox_id)
                        self.send_json({"id": inbox_id, "analysis": analysis}, HTTPStatus.CREATED)
                    except RuntimeError as exc:
                        self.send_json({"id": inbox_id, "warning": str(exc)}, HTTPStatus.CREATED)
                elif match := re.fullmatch(r"/api/inbox/(\d+)/classify", parsed.path):
                    analysis = classify_inbox_record(db, int(match.group(1)))
                    self.send_json({"ok": True, "analysis": analysis})
                elif match := re.fullmatch(r"/api/inbox/(\d+)/confirm", parsed.path):
                    inbox_id = int(match.group(1))
                    item = db.execute(
                        "SELECT id, raw_text, inferred_type, status, analysis_json FROM inbox WHERE id=?",
                        (inbox_id,),
                    ).fetchone()
                    if not item:
                        raise ValueError("收件箱记录不存在")
                    if item["status"] == "processed":
                        return self.send_json({"ok": True, "alreadyProcessed": True})
                    analysis = parse_json_object(item["analysis_json"])
                    item_type = str(payload.get("type") or analysis.get("type") or item["inferred_type"])
                    title = str(payload.get("title") or analysis.get("title") or item["raw_text"]).strip()[:240]
                    due_date = str(payload.get("dueDate") or analysis.get("dueDate") or date.today().isoformat())
                    destination_id = None
                    if item_type == "task":
                        date.fromisoformat(due_date)
                        task_cursor = db.execute("INSERT INTO tasks(title, due_date) VALUES (?, ?)", (title, due_date))
                        destination_id = int(task_cursor.lastrowid)
                    elif item_type == "project":
                        project_cursor = db.execute(
                            "INSERT INTO projects(title, description, status) VALUES (?, ?, 'todo')",
                            (title[:160], item["raw_text"][:500]),
                        )
                        destination_id = int(project_cursor.lastrowid)
                    elif item_type == "content":
                        content_cursor = db.execute(
                            "INSERT INTO content_items(title, description, status, source_inbox_id) VALUES (?, ?, 'idea', ?)",
                            (title[:200], item["raw_text"][:800], inbox_id),
                        )
                        destination_id = int(content_cursor.lastrowid)
                    elif item_type == "note":
                        note_cursor = db.execute(
                            "INSERT INTO notes(title, body, source_inbox_id) VALUES (?, ?, ?)",
                            (title[:200], item["raw_text"][:2000], inbox_id),
                        )
                        destination_id = int(note_cursor.lastrowid)
                    elif item_type == "transaction":
                        destination_id = int(payload.get("destinationId") or 0)
                        if not destination_id or not db.execute("SELECT id FROM transactions WHERE id=?", (destination_id,)).fetchone():
                            raise ValueError("请先补充金额、分类和账户，再确认这条财务记录")
                    db.execute(
                        """
                        UPDATE inbox SET inferred_type=?, status='processed', destination_id=?,
                            processed_at=? WHERE id=?
                        """,
                        (item_type, destination_id, datetime.now().isoformat(timespec="seconds"), inbox_id),
                    )
                    self.send_json({"ok": True, "destination": item_type, "destinationId": destination_id})
                else:
                    self.send_error_json("接口不存在", HTTPStatus.NOT_FOUND)
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            self.send_error_json(str(exc))
        except Exception as exc:
            self.send_error_json(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_PUT(self) -> None:
        if not self.require_authorized():
            return
        path = urlparse(self.path).path
        if path == "/api/budget":
            try:
                payload = read_json(self)
                month = str(payload.get("month", "")).strip()
                month_bounds(month)
                amount = round(float(payload.get("amount", 0)), 2)
                if amount < 0:
                    raise ValueError("本月预算不能小于 0")
                with connect() as db:
                    db.execute(
                        """
                        INSERT INTO monthly_budgets(month, amount) VALUES (?, ?)
                        ON CONFLICT(month) DO UPDATE SET amount=excluded.amount, updated_at=CURRENT_TIMESTAMP
                        """,
                        (month, amount),
                    )
                    category_budgets = payload.get("categoryBudgets", [])
                    if not isinstance(category_budgets, list):
                        raise ValueError("分类预算格式无效")
                    for item in category_budgets:
                        category_id = int(item.get("categoryId", 0))
                        category = db.execute(
                            "SELECT id FROM categories WHERE id=? AND kind='expense'", (category_id,)
                        ).fetchone()
                        if not category:
                            raise ValueError("分类预算包含无效分类")
                        raw_limit = item.get("amount")
                        if raw_limit in {None, ""}:
                            db.execute("DELETE FROM budgets WHERE category_id=? AND month=?", (category_id, month))
                            continue
                        limit_amount = round(float(raw_limit), 2)
                        if limit_amount < 0:
                            raise ValueError("分类预算不能小于 0")
                        db.execute(
                            """
                            INSERT INTO budgets(category_id, month, limit_amount) VALUES (?, ?, ?)
                            ON CONFLICT(category_id, month) DO UPDATE SET limit_amount=excluded.limit_amount
                            """,
                            (category_id, month, limit_amount),
                        )
                self.send_json({"ok": True})
            except (ValueError, json.JSONDecodeError) as exc:
                self.send_error_json(str(exc))
            return

        if path == "/api/profile":
            try:
                payload = read_json(self)
                display_name = str(payload.get("displayName", "")).strip()
                workspace_name = str(payload.get("workspaceName", "")).strip()
                if not display_name:
                    raise ValueError("昵称不能为空")
                if not workspace_name:
                    raise ValueError("工作空间名称不能为空")
                with connect() as db:
                    db.executemany(
                        """
                        INSERT INTO app_settings(key, value) VALUES (?, ?)
                        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP
                        """,
                        [("display_name", display_name[:40]), ("workspace_name", workspace_name[:80])],
                    )
                self.send_json({"ok": True})
            except (ValueError, json.JSONDecodeError) as exc:
                self.send_error_json(str(exc))
            return

        aesthetic_match = re.fullmatch(r"/api/aesthetic-items/(\d+)", path)
        if aesthetic_match:
            try:
                payload = read_json(self)
                item_id = int(aesthetic_match.group(1))
                with connect() as db:
                    current = db.execute("SELECT * FROM aesthetic_items WHERE id=?", (item_id,)).fetchone()
                    if not current:
                        return self.send_error_json("审美收藏不存在", HTTPStatus.NOT_FOUND)
                    old_image_url = current["image_url"]
                    item = validate_aesthetic_item(payload, current)
                    db.execute(
                        """
                        UPDATE aesthetic_items SET title=?, folder=?, source_url=?, image_url=?, note=?,
                            updated_at=CURRENT_TIMESTAMP WHERE id=?
                        """,
                        (item["title"], item["folder"], item["sourceUrl"], item["imageUrl"], item["note"], item_id),
                    )
                if old_image_url != item["imageUrl"]:
                    remove_uploaded_aesthetic_image(old_image_url)
                self.send_json({"ok": True})
            except (ValueError, json.JSONDecodeError) as exc:
                self.send_error_json(str(exc))
            return

        exercise_match = re.fullmatch(r"/api/exercise/(\d+)", path)
        if exercise_match:
            try:
                payload = read_json(self)
                exercise = validate_exercise(payload)
                with connect() as db:
                    cursor = db.execute(
                        """
                        UPDATE exercise_checkins SET exercise_date=?, activity=?, duration_minutes=?, note=?,
                            updated_at=CURRENT_TIMESTAMP WHERE id=?
                        """,
                        (exercise["date"], exercise["activity"], exercise["durationMinutes"], exercise["note"], int(exercise_match.group(1))),
                    )
                    if cursor.rowcount == 0:
                        return self.send_error_json("运动记录不存在", HTTPStatus.NOT_FOUND)
                self.send_json({"ok": True})
            except sqlite3.IntegrityError:
                self.send_error_json("这一天已经有另一条运动打卡")
            except (ValueError, json.JSONDecodeError) as exc:
                self.send_error_json(str(exc))
            return

        project_match = re.fullmatch(r"/api/projects/(\d+)", path)
        if project_match:
            try:
                payload = read_json(self)
                with connect() as db:
                    project = db.execute(
                        "SELECT id, title, description, status FROM projects WHERE id=?",
                        (int(project_match.group(1)),),
                    ).fetchone()
                    if not project:
                        return self.send_error_json("项目不存在", HTTPStatus.NOT_FOUND)
                    title = str(payload.get("title", project["title"])).strip()
                    description = str(payload.get("description", project["description"])).strip()
                    status = str(payload.get("status", project["status"])).strip()
                    if not title:
                        raise ValueError("项目名称不能为空")
                    if status not in {"todo", "doing", "review"}:
                        raise ValueError("项目状态无效")
                    db.execute(
                        "UPDATE projects SET title=?, description=?, status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (title[:160], description[:500], status, int(project_match.group(1))),
                    )
                    self.send_json({"ok": True})
            except (ValueError, json.JSONDecodeError) as exc:
                self.send_error_json(str(exc))
            return

        content_match = re.fullmatch(r"/api/content/(\d+)", path)
        if content_match:
            try:
                payload = read_json(self)
                with connect() as db:
                    item = db.execute("SELECT id, title, description, status FROM content_items WHERE id=?", (int(content_match.group(1)),)).fetchone()
                    if not item:
                        return self.send_error_json("内容不存在", HTTPStatus.NOT_FOUND)
                    title = str(payload.get("title", item["title"])).strip()
                    description = str(payload.get("description", item["description"])).strip()
                    status = str(payload.get("status", item["status"])).strip()
                    if not title:
                        raise ValueError("内容标题不能为空")
                    if status not in {"idea", "creating", "ready", "published"}:
                        raise ValueError("内容状态无效")
                    db.execute(
                        "UPDATE content_items SET title=?, description=?, status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (title[:200], description[:800], status, int(content_match.group(1))),
                    )
                    self.send_json({"ok": True})
            except (ValueError, json.JSONDecodeError) as exc:
                self.send_error_json(str(exc))
            return

        task_match = re.fullmatch(r"/api/tasks/(\d+)", path)
        if task_match:
            try:
                payload = read_json(self)
                with connect() as db:
                    task = db.execute("SELECT id, title, due_date, completed_at FROM tasks WHERE id=?", (int(task_match.group(1)),)).fetchone()
                    if not task:
                        return self.send_error_json("任务不存在", HTTPStatus.NOT_FOUND)
                    title = str(payload.get("title", task["title"])).strip()
                    due_date = str(payload.get("dueDate", task["due_date"])).strip()
                    if not title:
                        raise ValueError("任务内容不能为空")
                    date.fromisoformat(due_date)
                    done = bool(payload.get("done", task["completed_at"] is not None))
                    completed_at = task["completed_at"]
                    if done and not completed_at:
                        completed_at = datetime.now().isoformat(timespec="seconds")
                    elif not done:
                        completed_at = None
                    db.execute(
                        "UPDATE tasks SET title=?, due_date=?, completed_at=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (title[:240], due_date, completed_at, int(task_match.group(1))),
                    )
                    self.send_json({"ok": True, "completedAt": completed_at})
            except (ValueError, json.JSONDecodeError) as exc:
                self.send_error_json(str(exc))
            return

        match = re.fullmatch(r"/api/transactions/(\d+)", path)
        if not match:
            return self.send_error_json("接口不存在", HTTPStatus.NOT_FOUND)
        try:
            payload = read_json(self)
            with connect() as db:
                tx = validate_transaction(payload, db)
                cursor = db.execute(
                    """
                    UPDATE transactions SET kind=?, amount=?, transaction_date=?, category_id=?, account_id=?,
                        project=?, counterparty=?, note=?, updated_at=CURRENT_TIMESTAMP WHERE id=?
                    """,
                    (tx["kind"], tx["amount"], tx["date"], tx["categoryId"], tx["accountId"], tx["project"], tx["counterparty"], tx["note"], int(match.group(1))),
                )
                if cursor.rowcount == 0:
                    return self.send_error_json("流水不存在", HTTPStatus.NOT_FOUND)
                self.send_json({"ok": True})
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            self.send_error_json(str(exc))

    def do_DELETE(self) -> None:
        if not self.require_authorized():
            return
        path = urlparse(self.path).path
        image_match = re.fullmatch(r"/api/aesthetic-images/([a-f0-9]{32}\.(?:jpg|png|webp|gif))", path)
        if image_match:
            image_path = AESTHETIC_UPLOAD_DIR / image_match.group(1)
            if image_path.is_file():
                image_path.unlink()
            return self.send_json({"ok": True})

        aesthetic_match = re.fullmatch(r"/api/aesthetic-items/(\d+)", path)
        if aesthetic_match:
            with connect() as db:
                item_id = int(aesthetic_match.group(1))
                item = db.execute("SELECT image_url FROM aesthetic_items WHERE id=?", (item_id,)).fetchone()
                cursor = db.execute("DELETE FROM aesthetic_items WHERE id=?", (item_id,))
                if cursor.rowcount == 0:
                    return self.send_error_json("审美收藏不存在", HTTPStatus.NOT_FOUND)
            remove_uploaded_aesthetic_image(item["image_url"] if item else "")
            return self.send_json({"ok": True})

        exercise_match = re.fullmatch(r"/api/exercise/(\d+)", path)
        if exercise_match:
            with connect() as db:
                cursor = db.execute("DELETE FROM exercise_checkins WHERE id=?", (int(exercise_match.group(1)),))
                if cursor.rowcount == 0:
                    return self.send_error_json("运动记录不存在", HTTPStatus.NOT_FOUND)
            return self.send_json({"ok": True})

        project_match = re.fullmatch(r"/api/projects/(\d+)", path)
        if project_match:
            with connect() as db:
                cursor = db.execute("DELETE FROM projects WHERE id=?", (int(project_match.group(1)),))
                if cursor.rowcount == 0:
                    return self.send_error_json("项目不存在", HTTPStatus.NOT_FOUND)
            return self.send_json({"ok": True})

        content_match = re.fullmatch(r"/api/content/(\d+)", path)
        if content_match:
            with connect() as db:
                cursor = db.execute("DELETE FROM content_items WHERE id=?", (int(content_match.group(1)),))
                if cursor.rowcount == 0:
                    return self.send_error_json("内容不存在", HTTPStatus.NOT_FOUND)
            return self.send_json({"ok": True})

        task_match = re.fullmatch(r"/api/tasks/(\d+)", path)
        if task_match:
            with connect() as db:
                cursor = db.execute("DELETE FROM tasks WHERE id=?", (int(task_match.group(1)),))
                if cursor.rowcount == 0:
                    return self.send_error_json("任务不存在", HTTPStatus.NOT_FOUND)
            return self.send_json({"ok": True})

        match = re.fullmatch(r"/api/transactions/(\d+)", path)
        if not match:
            return self.send_error_json("接口不存在", HTTPStatus.NOT_FOUND)
        with connect() as db:
            cursor = db.execute("DELETE FROM transactions WHERE id=?", (int(match.group(1)),))
            if cursor.rowcount == 0:
                return self.send_error_json("流水不存在", HTTPStatus.NOT_FOUND)
        self.send_json({"ok": True})


def main() -> None:
    parser = argparse.ArgumentParser(description="Run XU Workspace locally")
    parser.add_argument("--port", type=int, default=4173)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    init_database()
    handler = partial(XUHandler, directory=str(STATIC_ROOT))
    server = ThreadingHTTPServer((args.host, args.port), handler)
    actual_port = int(server.server_address[1])
    lan_enabled = args.host not in {"127.0.0.1", "::1", "localhost"}
    MOBILE_ACCESS.update({
        "enabled": lan_enabled,
        "port": actual_port,
        "lan_ip": find_lan_ip() if lan_enabled else "",
        "access_code": f"{secrets.randbelow(1_000_000):06d}",
        "session_token": secrets.token_urlsafe(32),
    })
    server.daemon_threads = True
    print(f"XU Workspace: http://127.0.0.1:{actual_port}/")
    print(f"Local database: {DB_PATH}")
    if MOBILE_ACCESS["enabled"] and MOBILE_ACCESS["lan_ip"]:
        print(f"Mobile access: http://{MOBILE_ACCESS['lan_ip']}:{actual_port}/")
        print(f"Mobile code: {MOBILE_ACCESS['access_code']}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
