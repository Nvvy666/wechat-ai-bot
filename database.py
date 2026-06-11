"""
微信 AI Bot — 数据库层
SQLite: 联系人、聊天记录、配置、风格档案、fewshot、日志
"""
import sqlite3
import json
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional


DB_PATH = Path(__file__).parent / "data" / "wechat_bot.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ====== Schema ======

def init_db():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            type TEXT DEFAULT 'contact',
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_name TEXT NOT NULL,
            sender TEXT NOT NULL,
            content TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_msg_contact ON messages(contact_name, created_at);

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS style_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT DEFAULT '',
            traits TEXT DEFAULT '{}',
            prompt_template TEXT DEFAULT '',
            is_active INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS fewshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id INTEGER REFERENCES style_profiles(id) ON DELETE CASCADE,
            scenario TEXT DEFAULT '',
            user_msg TEXT NOT NULL,
            bot_reply TEXT NOT NULL,
            source TEXT DEFAULT 'manual',
            usage_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level TEXT DEFAULT 'INFO',
            source TEXT DEFAULT 'system',
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_logs_created ON logs(created_at);
        """)
        conn.commit()


# ====== Contacts ======

def add_contact(name: str, ctype: str = "contact") -> bool:
    try:
        with get_conn() as conn:
            conn.execute("INSERT OR IGNORE INTO contacts (name, type) VALUES (?, ?)", (name, ctype))
            return True
    except Exception:
        return False


def remove_contact(name: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM contacts WHERE name = ?", (name,))


def set_contact_active(name: str, active: bool):
    with get_conn() as conn:
        conn.execute("UPDATE contacts SET is_active = ? WHERE name = ?", (int(active), name))


def get_contacts(ctype: str = None, active_only: bool = True) -> list[dict]:
    with get_conn() as conn:
        sql = "SELECT * FROM contacts WHERE 1=1"
        params = []
        if ctype:
            sql += " AND type = ?"
            params.append(ctype)
        if active_only:
            sql += " AND is_active = 1"
        sql += " ORDER BY created_at DESC"
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


# ====== Messages ======

def save_message(contact_name: str, sender: str, content: str, role: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO messages (contact_name, sender, content, role) VALUES (?,?,?,?)",
            (contact_name, sender, content, role),
        )


def get_messages(contact_name: str = None, limit: int = 100, offset: int = 0) -> list[dict]:
    with get_conn() as conn:
        if contact_name:
            rows = conn.execute(
                "SELECT * FROM messages WHERE contact_name = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (contact_name, limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM messages ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [dict(r) for r in reversed(rows)]


def search_messages(keyword: str, limit: int = 100) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE content LIKE ? ORDER BY created_at DESC LIMIT ?",
            (f"%{keyword}%", limit),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]


def get_message_stats() -> dict:
    with get_conn() as conn:
        today = datetime.now().strftime("%Y-%m-%d")
        total = conn.execute("SELECT COUNT(*) as c FROM messages").fetchone()["c"]
        today_in = conn.execute(
            "SELECT COUNT(*) as c FROM messages WHERE role='incoming' AND date(created_at)=?", (today,)
        ).fetchone()["c"]
        today_out = conn.execute(
            "SELECT COUNT(*) as c FROM messages WHERE role='outgoing' AND date(created_at)=?", (today,)
        ).fetchone()["c"]
        active_contacts = conn.execute(
            "SELECT COUNT(DISTINCT contact_name) as c FROM messages WHERE date(created_at)=?", (today,)
        ).fetchone()["c"]
        return {
            "total": total,
            "today_incoming": today_in,
            "today_outgoing": today_out,
            "today_active_contacts": active_contacts,
        }


def is_duplicate(contact_name: str, content: str, within_seconds: int = 60) -> bool:
    """检查消息是否在指定时间内重复"""
    cutoff = (datetime.now() - timedelta(seconds=within_seconds)).isoformat()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as c FROM messages WHERE contact_name=? AND content=? AND created_at > ?",
            (contact_name, content, cutoff),
        ).fetchone()
        return row["c"] > 0


# ====== Settings ======

def get_setting(key: str, default: str = "") -> str:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            (key, value),
        )


def get_all_settings() -> dict:
    with get_conn() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}


# ====== Style Profiles ======

def create_profile(name: str, description: str = "", traits: dict = None, prompt_template: str = "") -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO style_profiles (name, description, traits, prompt_template) VALUES (?,?,?,?)",
            (name, description, json.dumps(traits or {}, ensure_ascii=False), prompt_template),
        )
        return cur.lastrowid


def update_profile(pid: int, **kwargs):
    allowed = {"name", "description", "traits", "prompt_template", "is_active"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return
    if "traits" in updates and isinstance(updates["traits"], dict):
        updates["traits"] = json.dumps(updates["traits"], ensure_ascii=False)
    sets = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [pid]
    with get_conn() as conn:
        conn.execute(f"UPDATE style_profiles SET {sets} WHERE id = ?", vals)


def get_profiles() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM style_profiles ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def get_active_profile() -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM style_profiles WHERE is_active = 1 LIMIT 1").fetchone()
        return dict(row) if row else None


def set_active_profile(pid: int):
    with get_conn() as conn:
        conn.execute("UPDATE style_profiles SET is_active = 0")
        conn.execute("UPDATE style_profiles SET is_active = 1 WHERE id = ?", (pid,))


def delete_profile(pid: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM style_profiles WHERE id = ?", (pid,))


# ====== Few-shots ======

def add_fewshot(profile_id: int, user_msg: str, bot_reply: str, scenario: str = "", source: str = "manual") -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO fewshots (profile_id, scenario, user_msg, bot_reply, source) VALUES (?,?,?,?,?)",
            (profile_id, scenario, user_msg, bot_reply, source),
        )
        return cur.lastrowid


def get_fewshots(profile_id: int = None, limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        if profile_id:
            rows = conn.execute(
                "SELECT * FROM fewshots WHERE profile_id = ? ORDER BY usage_count DESC, created_at DESC LIMIT ?",
                (profile_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM fewshots ORDER BY usage_count DESC, created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


def increment_fewshot_usage(fid: int):
    with get_conn() as conn:
        conn.execute("UPDATE fewshots SET usage_count = usage_count + 1 WHERE id = ?", (fid,))


def delete_fewshot(fid: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM fewshots WHERE id = ?", (fid,))


def clear_fewshots(profile_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM fewshots WHERE profile_id = ?", (profile_id,))


# ====== Logs ======

def add_log(level: str, message: str, source: str = "system"):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO logs (level, source, message) VALUES (?,?,?)",
            (level, source, message),
        )
        # 保留最近 10000 条日志
        conn.execute("DELETE FROM logs WHERE id NOT IN (SELECT id FROM logs ORDER BY created_at DESC LIMIT 10000)")


def get_logs(limit: int = 200, level: str = None) -> list[dict]:
    with get_conn() as conn:
        if level:
            rows = conn.execute(
                "SELECT * FROM logs WHERE level = ? ORDER BY created_at DESC LIMIT ?",
                (level, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM logs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in reversed(rows)]


# ====== Init ======
init_db()
