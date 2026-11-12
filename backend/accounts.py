"""手机号、次数和兑换码。熟人试用先由安装包的人转告验证码，短信通道以后再接。"""

from __future__ import annotations

import hashlib
import logging
import re
import secrets
from datetime import datetime, timedelta

log = logging.getLogger("tutor.accounts")

FREE_CREDITS = 5
DAILY_CAP = 40
CODE_MINUTES = 10
_FOLLOW = ("再讲", "再细", "讲细", "没听懂", "听不懂", "不懂", "为什么", "这一步", "什么意思", "再解释")


def normalize_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("86") and len(digits) == 13:
        digits = digits[2:]
    if re.fullmatch(r"1\d{10}", digits):
        return digits
    return None


def consumes_turn(text: str, image_count: int) -> bool:
    if image_count > 0:
        return True
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    if len(cleaned) <= 24 and any(word in cleaned for word in _FOLLOW):
        return False
    return True


def ensure_schema(store) -> None:
    with store._conn() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS app_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT NOT NULL UNIQUE,
                credits INTEGER NOT NULL,
                day TEXT DEFAULT '',
                day_used INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS auth_tokens (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                device_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sms_codes (
                phone TEXT PRIMARY KEY,
                code_hash TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                sent_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS redeem_codes (
                code TEXT PRIMARY KEY,
                credits INTEGER NOT NULL,
                used_by INTEGER,
                used_at TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS legacy_devices (
                device_id TEXT PRIMARY KEY
            );
            """
        )
        row = con.execute("SELECT value FROM app_meta WHERE key = 'legacy_snap'").fetchone()
        if row is None:
            con.execute("INSERT OR IGNORE INTO legacy_devices (device_id) SELECT DISTINCT device_id FROM sessions")
            con.execute("INSERT INTO app_meta (key, value) VALUES ('legacy_snap', '1')")


def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


def _hash_code(phone: str, code: str) -> str:
    return hashlib.sha256(f"{phone}:{code}".encode()).hexdigest()


def is_legacy(store, device_id: str) -> bool:
    with store._conn() as con:
        row = con.execute("SELECT 1 FROM legacy_devices WHERE device_id = ?", (device_id,)).fetchone()
    return row is not None


def user_by_token(store, token: str) -> dict | None:
    if not token:
        return None
    with store._conn() as con:
        row = con.execute(
            """
            SELECT u.id, u.phone, u.credits, u.day, u.day_used
            FROM auth_tokens t JOIN users u ON u.id = t.user_id
            WHERE t.token = ?
            """,
            (token,),
        ).fetchone()
    return dict(row) if row else None


def issue_login_code(store, phone: str, replace: bool = True) -> str:
    if not replace:
        now = _now().isoformat(timespec="seconds")
        with store._conn() as con:
            row = con.execute("SELECT expires_at FROM sms_codes WHERE phone = ?", (phone,)).fetchone()
        if row is not None and row["expires_at"] >= now:
            return ""
    code = f"{secrets.randbelow(1_000_000):06d}"
    expires = (_now() + timedelta(minutes=CODE_MINUTES)).isoformat(timespec="seconds")
    with store._conn() as con:
        con.execute(
            """
            INSERT INTO sms_codes (phone, code_hash, expires_at, sent_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(phone) DO UPDATE SET
                code_hash = excluded.code_hash,
                expires_at = excluded.expires_at,
                sent_at = excluded.sent_at
            """,
            (phone, _hash_code(phone, code), expires, _now().isoformat(timespec="seconds")),
        )
    log.warning("login code phone=%s code=%s", phone, code)
    return code


def verify_login(store, phone: str, code: str, device_id: str) -> dict | None:
    now = _now().isoformat(timespec="seconds")
    with store._conn() as con:
        row = con.execute("SELECT code_hash, expires_at FROM sms_codes WHERE phone = ?", (phone,)).fetchone()
        if row is None or row["expires_at"] < now:
            return None
        if not secrets.compare_digest(row["code_hash"], _hash_code(phone, code.strip())):
            return None
        con.execute("DELETE FROM sms_codes WHERE phone = ?", (phone,))
        existing = con.execute("SELECT id, credits FROM users WHERE phone = ?", (phone,)).fetchone()
        if existing is None:
            cur = con.execute(
                "INSERT INTO users (phone, credits, created_at) VALUES (?, ?, ?)",
                (phone, FREE_CREDITS, now),
            )
            user_id = cur.lastrowid
            credits = FREE_CREDITS
        else:
            user_id = existing["id"]
            credits = existing["credits"]
        token = secrets.token_hex(24)
        con.execute(
            "INSERT INTO auth_tokens (token, user_id, device_id, created_at) VALUES (?, ?, ?, ?)",
            (token, user_id, device_id, now),
        )
    return {"token": token, "credits": credits, "phone": phone}


def issue_redeem(store, credits: int) -> str:
    code = "M" + secrets.token_hex(4).upper()
    with store._conn() as con:
        con.execute(
            "INSERT INTO redeem_codes (code, credits, created_at) VALUES (?, ?, ?)",
            (code, credits, _now().isoformat(timespec="seconds")),
        )
    return code


def redeem(store, token: str, code: str) -> dict | None:
    user = user_by_token(store, token)
    if user is None:
        return None
    cleaned = (code or "").strip().upper()
    with store._conn() as con:
        row = con.execute("SELECT credits, used_by FROM redeem_codes WHERE code = ?", (cleaned,)).fetchone()
        if row is None or row["used_by"] is not None:
            return None
        con.execute(
            "UPDATE redeem_codes SET used_by = ?, used_at = ? WHERE code = ?",
            (user["id"], _now().isoformat(timespec="seconds"), cleaned),
        )
        con.execute("UPDATE users SET credits = credits + ? WHERE id = ?", (row["credits"], user["id"]))
        credits = con.execute("SELECT credits FROM users WHERE id = ?", (user["id"],)).fetchone()["credits"]
    return {"credits": credits, "added": row["credits"]}


def hold_credit(store, user_id: int) -> str | None:
    today = _now().date().isoformat()
    with store._conn() as con:
        row = con.execute("SELECT credits, day, day_used FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            return "请先用手机号登录。"
        used = row["day_used"] if row["day"] == today else 0
        if used >= DAILY_CAP:
            return "今天的讲解次数已经用完。明天再来，或等这一天过去。"
        if row["credits"] <= 0:
            return "免费次数用完了。让给你安装包的人发一组兑换码，兑换后可以继续。"
        con.execute(
            "UPDATE users SET credits = credits - 1, day = ?, day_used = ? WHERE id = ?",
            (today, used + 1, user_id),
        )
    return None


def admin_desk(store) -> dict:
    today = _now().date().isoformat()
    with store._conn() as con:
        users = con.execute(
            "SELECT phone, credits, day, day_used, created_at FROM users ORDER BY id DESC LIMIT 40"
        ).fetchall()
        redeems = con.execute(
            """
            SELECT code, credits, created_at FROM redeem_codes
            WHERE used_by IS NULL
            ORDER BY created_at DESC LIMIT 20
            """
        ).fetchall()
    return {
        "users": [
            {
                "phone": row["phone"],
                "credits": row["credits"],
                "day_used": row["day_used"] if row["day"] == today else 0,
                "created_at": row["created_at"],
            }
            for row in users
        ],
        "redeems": [
            {"code": row["code"], "credits": row["credits"], "created_at": row["created_at"]}
            for row in redeems
        ],
    }


def refund_credit(store, user_id: int) -> None:
    today = _now().date().isoformat()
    with store._conn() as con:
        row = con.execute("SELECT day, day_used FROM users WHERE id = ?", (user_id,)).fetchone()
        used = max(0, (row["day_used"] if row and row["day"] == today else 1) - 1)
        con.execute(
            "UPDATE users SET credits = credits + 1, day = ?, day_used = ? WHERE id = ?",
            (today, used, user_id),
        )
