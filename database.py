import sqlite3
import threading
from datetime import datetime

import config

_lock = threading.Lock()


def _conn():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _lock:
        conn = _conn()
        cur = conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS guilds (
                guild_id INTEGER PRIMARY KEY,
                prefix TEXT NOT NULL DEFAULT '!',
                welcome_channel INTEGER,
                welcome_message TEXT,
                auto_role INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS levels (
                user_id INTEGER,
                guild_id INTEGER,
                xp INTEGER NOT NULL DEFAULT 0,
                level INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (user_id, guild_id)
            );

            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                reason TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS mod_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                target_name TEXT DEFAULT '',
                moderator_id INTEGER NOT NULL,
                moderator_name TEXT DEFAULT '',
                reason TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );

                        CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER UNIQUE NOT NULL,
                guild_id INTEGER NOT NULL,
                author_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                claimer_id INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                ticket_id INTEGER NOT NULL,
                reviewer_id INTEGER NOT NULL,
                stars INTEGER NOT NULL,
                comment TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS custom_commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                response_text TEXT DEFAULT '',
                embed_title TEXT DEFAULT '',
                embed_description TEXT DEFAULT '',
                embed_color TEXT DEFAULT '#5865F2',
                action_type TEXT DEFAULT 'reply',
                action_value TEXT DEFAULT '',
                target_value TEXT DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                UNIQUE (guild_id, name)
            );
            """
        )
        conn.commit()
        # Mevcut tablolara eksik kolon ekleme (migrasyon)
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(tickets)").fetchall()]
        if cols and "claimer_id" not in cols:
            conn.execute("ALTER TABLE tickets ADD COLUMN claimer_id INTEGER DEFAULT 0")
        log_cols = [r["name"] for r in conn.execute("PRAGMA table_info(mod_log)").fetchall()]
        if log_cols and "message_id" not in log_cols:
            conn.execute("ALTER TABLE mod_log ADD COLUMN message_id INTEGER DEFAULT 0")
            conn.commit()
        conn.close()


# ---------- Guild ayarları ----------

def get_prefix(guild_id: int) -> str:
    with _lock:
        conn = _conn()
        row = conn.execute(
            "SELECT prefix FROM guilds WHERE guild_id = ?", (guild_id,)
        ).fetchone()
        if row is None:
            conn.execute("INSERT OR IGNORE INTO guilds (guild_id) VALUES (?)", (guild_id,))
            conn.commit()
            conn.close()
            return "!"
        conn.close()
        return row["prefix"]


def set_prefix(guild_id: int, prefix: str) -> None:
    with _lock:
        conn = _conn()
        conn.execute(
            """INSERT INTO guilds (guild_id, prefix) VALUES (?, ?)
               ON CONFLICT(guild_id) DO UPDATE SET prefix = excluded.prefix""",
            (guild_id, prefix),
        )
        conn.commit()
        conn.close()


def get_guild_settings(guild_id: int):
    with _lock:
        conn = _conn()
        conn.execute("INSERT OR IGNORE INTO guilds (guild_id) VALUES (?)", (guild_id,))
        conn.commit()
        row = conn.execute(
            "SELECT prefix, welcome_channel, welcome_message, auto_role FROM guilds WHERE guild_id = ?",
            (guild_id,),
        ).fetchone()
        conn.close()
        return dict(row) if row else {}


def set_welcome(guild_id: int, channel_id: int, message: str) -> None:
    with _lock:
        conn = _conn()
        conn.execute(
            """INSERT INTO guilds (guild_id, welcome_channel, welcome_message) VALUES (?, ?, ?)
               ON CONFLICT(guild_id) DO UPDATE SET
                   welcome_channel = excluded.welcome_channel,
                   welcome_message = excluded.welcome_message""",
            (guild_id, channel_id, message),
        )
        conn.commit()
        conn.close()


def set_auto_role(guild_id: int, role_id: int) -> None:
    with _lock:
        conn = _conn()
        conn.execute(
            """INSERT INTO guilds (guild_id, auto_role) VALUES (?, ?)
               ON CONFLICT(guild_id) DO UPDATE SET auto_role = excluded.auto_role""",
            (guild_id, role_id),
        )
        conn.commit()
        conn.close()


# ---------- Seviye / XP ----------

def add_xp(guild_id: int, user_id: int, amount: int = 10):
    with _lock:
        conn = _conn()
        row = conn.execute(
            "SELECT xp, level FROM levels WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ).fetchone()
        if row is None:
            xp, level = amount, 1
        else:
            xp, level = row["xp"] + amount, row["level"]
        new_level = level
        threshold = new_level * 100
        while xp >= threshold:
            xp -= threshold
            new_level += 1
            threshold = new_level * 100
        leveled_up = new_level > level
        conn.execute(
            """INSERT INTO levels (guild_id, user_id, xp, level) VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id, guild_id) DO UPDATE SET
                   xp = excluded.xp, level = excluded.level""",
            (guild_id, user_id, xp, new_level),
        )
        conn.commit()
        conn.close()
        return new_level, leveled_up


def get_level(guild_id: int, user_id: int):
    with _lock:
        conn = _conn()
        row = conn.execute(
            "SELECT xp, level FROM levels WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ).fetchone()
        conn.close()
        if row is None:
            return 0, 1
        return row["xp"], row["level"]


def get_leaderboard(guild_id: int, limit: int = 10):
    with _lock:
        conn = _conn()
        rows = conn.execute(
            "SELECT user_id, xp, level FROM levels WHERE guild_id = ? ORDER BY level DESC, xp DESC LIMIT ?",
            (guild_id, limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


def reset_levels(guild_id: int) -> int:
    with _lock:
        conn = _conn()
        cur = conn.execute("DELETE FROM levels WHERE guild_id = ?", (guild_id,))
        conn.commit()
        conn.close()
        return cur.rowcount


# ---------- Uyarılar ----------

def add_warning(guild_id: int, user_id: int, moderator_id: int, reason: str):
    with _lock:
        conn = _conn()
        cur = conn.execute(
            "INSERT INTO warnings (guild_id, user_id, moderator_id, reason, created_at) VALUES (?, ?, ?, ?, ?)",
            (guild_id, user_id, moderator_id, reason, datetime.utcnow().isoformat()),
        )
        conn.commit()
        conn.close()
        return cur.lastrowid


def get_warnings(guild_id: int, user_id: int):
    with _lock:
        conn = _conn()
        rows = conn.execute(
            "SELECT id, reason, created_at, moderator_id FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY id DESC",
            (guild_id, user_id),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


def get_all_warnings(guild_id: int, limit: int = 100):
    with _lock:
        conn = _conn()
        rows = conn.execute(
            "SELECT * FROM warnings WHERE guild_id = ? ORDER BY id DESC LIMIT ?",
            (guild_id, limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


# ---------- Moderasyon kayıtları ----------

def add_mod_log(guild_id: int, action: str, user_id: int, target_name: str, moderator: tuple, reason: str = "") -> int:
    mod_id, mod_name = moderator if moderator else (0, "Bilinmeyen")
    with _lock:
        conn = _conn()
        cur = conn.execute(
            "INSERT INTO mod_log (guild_id, action, user_id, target_name, moderator_id, moderator_name, reason, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (guild_id, action, user_id, target_name, mod_id, mod_name, reason, datetime.utcnow().isoformat()),
        )
        conn.commit()
        log_id = cur.lastrowid
        conn.close()
        return log_id


def update_mod_log_message(log_id: int, message_id: int) -> None:
    with _lock:
        conn = _conn()
        conn.execute("UPDATE mod_log SET message_id = ? WHERE id = ?", (message_id, log_id))
        conn.commit()
        conn.close()


def get_mod_log(guild_id: int, log_id: int):
    with _lock:
        conn = _conn()
        row = conn.execute(
            "SELECT * FROM mod_log WHERE id = ? AND guild_id = ?",
            (log_id, guild_id),
        ).fetchone()
        conn.close()
        return dict(row) if row else None


def get_mod_logs(guild_id: int, limit: int = 100):
    with _lock:
        conn = _conn()
        rows = conn.execute(
            "SELECT * FROM mod_log WHERE guild_id = ? ORDER BY id DESC LIMIT ?",
            (guild_id, limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


def delete_mod_log(guild_id: int, log_id: int) -> dict:
    with _lock:
        conn = _conn()
        row = conn.execute(
            "SELECT message_id FROM mod_log WHERE id = ? AND guild_id = ?",
            (log_id, guild_id),
        ).fetchone()
        message_id = row["message_id"] if row else 0
        cur = conn.execute(
            "DELETE FROM mod_log WHERE id = ? AND guild_id = ?",
            (log_id, guild_id),
        )
        conn.commit()
        conn.close()
        return {"deleted": cur.rowcount > 0, "message_id": message_id}


def delete_warning(warning_id: int) -> bool:
    with _lock:
        conn = _conn()
        cur = conn.execute("DELETE FROM warnings WHERE id = ?", (warning_id,))
        conn.commit()
        conn.close()
        return cur.rowcount > 0


# ---------- Ticketler ----------

def create_ticket(guild_id: int, channel_id: int, author_id: int) -> int:
    with _lock:
        conn = _conn()
        cur = conn.execute(
            "INSERT INTO tickets (guild_id, channel_id, author_id, created_at) VALUES (?, ?, ?, ?)",
            (guild_id, channel_id, author_id, datetime.utcnow().isoformat()),
        )
        conn.commit()
        conn.close()
        return cur.lastrowid


def close_ticket(channel_id: int) -> None:
    with _lock:
        conn = _conn()
        conn.execute(
            "UPDATE tickets SET status = 'closed' WHERE channel_id = ?",
            (channel_id,),
        )
        conn.commit()
        conn.close()


def claim_ticket(channel_id: int, claimer_id: int) -> None:
    with _lock:
        conn = _conn()
        conn.execute(
            "UPDATE tickets SET claimer_id = ? WHERE channel_id = ?",
            (claimer_id, channel_id),
        )
        conn.commit()
        conn.close()


def get_ticket(channel_id: int):
    with _lock:
        conn = _conn()
        row = conn.execute(
            "SELECT * FROM tickets WHERE channel_id = ?", (channel_id,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None


def delete_ticket_by_id(guild_id: int, ticket_id: int) -> bool:
    with _lock:
        conn = _conn()
        cur = conn.execute(
            "DELETE FROM tickets WHERE id = ? AND guild_id = ?",
            (ticket_id, guild_id),
        )
        conn.commit()
        conn.close()
        return cur.rowcount > 0


def get_ticket_by_id(guild_id: int, ticket_id: int):
    with _lock:
        conn = _conn()
        row = conn.execute(
            "SELECT * FROM tickets WHERE id = ? AND guild_id = ?",
            (ticket_id, guild_id),
        ).fetchone()
        conn.close()
        return dict(row) if row else None


def get_open_ticket(guild_id: int, author_id: int):
    with _lock:
        conn = _conn()
        row = conn.execute(
            "SELECT * FROM tickets WHERE guild_id = ? AND author_id = ? AND status = 'open'",
            (guild_id, author_id),
        ).fetchone()
        conn.close()
        return dict(row) if row else None


def get_tickets(guild_id: int, limit: int = 100):
    with _lock:
        conn = _conn()
        rows = conn.execute(
            "SELECT * FROM tickets WHERE guild_id = ? ORDER BY id DESC LIMIT ?",
            (guild_id, limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


def add_review(guild_id: int, ticket_id: int, reviewer_id: int, stars: int, comment: str) -> int:
    with _lock:
        conn = _conn()
        cur = conn.execute(
            "INSERT INTO reviews (guild_id, ticket_id, reviewer_id, stars, comment, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (guild_id, ticket_id, reviewer_id, stars, comment, datetime.utcnow().isoformat()),
        )
        conn.commit()
        conn.close()
        return cur.lastrowid


def has_reviewed(ticket_id: int, reviewer_id: int) -> bool:
    with _lock:
        conn = _conn()
        row = conn.execute(
            "SELECT 1 FROM reviews WHERE ticket_id = ? AND reviewer_id = ?",
            (ticket_id, reviewer_id),
        ).fetchone()
        conn.close()
        return row is not None


def get_reviews_for_ticket(guild_id: int, ticket_id: int):
    with _lock:
        conn = _conn()
        rows = conn.execute(
            "SELECT * FROM reviews WHERE guild_id = ? AND ticket_id = ? ORDER BY id ASC",
            (guild_id, ticket_id),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


# ---------- Özel komutlar ----------

def add_custom_command(guild_id: int, name: str, data: dict) -> None:
    data.setdefault("created_at", datetime.utcnow().isoformat())
    with _lock:
        conn = _conn()
        conn.execute(
            """INSERT INTO custom_commands
                   (guild_id, name, response_text, embed_title, embed_description,
                    embed_color, action_type, action_value, target_value, enabled, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(guild_id, name) DO UPDATE SET
                   response_text = excluded.response_text,
                   embed_title = excluded.embed_title,
                   embed_description = excluded.embed_description,
                   embed_color = excluded.embed_color,
                   action_type = excluded.action_type,
                   action_value = excluded.action_value,
                   target_value = excluded.target_value,
                   enabled = excluded.enabled""",
            (
                guild_id,
                name,
                data.get("response_text", ""),
                data.get("embed_title", ""),
                data.get("embed_description", ""),
                data.get("embed_color", "#5865F2"),
                data.get("action_type", "reply"),
                data.get("action_value", ""),
                data.get("target_value", ""),
                1 if data.get("enabled", True) else 0,
                data["created_at"],
            ),
        )
        conn.commit()
        conn.close()


def get_custom_command(guild_id: int, name: str):
    with _lock:
        conn = _conn()
        row = conn.execute(
            "SELECT * FROM custom_commands WHERE guild_id = ? AND name = ?",
            (guild_id, name),
        ).fetchone()
        conn.close()
        return dict(row) if row else None


def get_all_custom_commands(guild_id: int):
    with _lock:
        conn = _conn()
        rows = conn.execute(
            "SELECT * FROM custom_commands WHERE guild_id = ? ORDER BY name",
            (guild_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


def get_command_guild_ids():
    with _lock:
        conn = _conn()
        rows = conn.execute(
            "SELECT DISTINCT guild_id FROM custom_commands WHERE guild_id != 0"
        ).fetchall()
        conn.close()
        return [r["guild_id"] for r in rows]


def delete_custom_command(guild_id: int, name: str) -> bool:
    with _lock:
        conn = _conn()
        cur = conn.execute(
            "DELETE FROM custom_commands WHERE guild_id = ? AND name = ?",
            (guild_id, name),
        )
        conn.commit()
        conn.close()
        return cur.rowcount > 0


def set_custom_command_enabled(guild_id: int, name: str, enabled: bool) -> None:
    with _lock:
        conn = _conn()
        conn.execute(
            "UPDATE custom_commands SET enabled = ? WHERE guild_id = ? AND name = ?",
            (1 if enabled else 0, guild_id, name),
        )
        conn.commit()
        conn.close()