"""SQLite 기반 유저 관계 그래프 + 닉네임 장부.

"A —친구→ B" 같은 관계는 벡터 검색보다 정형 데이터로 정확히 조회하는 게 낫다.
"""
import os
import sqlite3

import config

os.makedirs(config.DATA_DIR, exist_ok=True)
_DB = os.path.join(config.DATA_DIR, "relations.db")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB)
    conn.row_factory = sqlite3.Row
    return conn


def init() -> None:
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS relations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_a_id TEXT NOT NULL,
                user_a_name TEXT NOT NULL,
                relation TEXT NOT NULL,
                user_b_id TEXT NOT NULL,
                user_b_name TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                name TEXT NOT NULL
            )
        """)
        # 기존 관계에 등장한 유저(unknown: 포함)를 장부에 백필
        c.execute("""
            INSERT OR IGNORE INTO users(user_id, name)
            SELECT user_a_id, user_a_name FROM relations
            UNION
            SELECT user_b_id, user_b_name FROM relations
        """)


def remember_user(user_id, name: str) -> None:
    """메시지를 볼 때마다 유저ID-닉네임 매핑을 최신으로 유지한다."""
    with _conn() as c:
        c.execute(
            "INSERT INTO users(user_id, name) VALUES(?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET name = excluded.name",
            (str(user_id), name),
        )


def find_users(name: str) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT user_id, name FROM users WHERE name LIKE ?", (f"%{name}%",)
        ).fetchall()
    return [dict(r) for r in rows]


def add(a_id, a_name: str, relation: str, b_id, b_name: str) -> int:
    with _conn() as c:
        dup = c.execute(
            "SELECT id FROM relations WHERE user_a_id = ? AND user_b_id = ? AND relation = ?",
            (str(a_id), str(b_id), relation),
        ).fetchone()
        if dup:
            return dup["id"]
        cur = c.execute(
            "INSERT INTO relations(user_a_id, user_a_name, relation, user_b_id, user_b_name) "
            "VALUES(?, ?, ?, ?, ?)",
            (str(a_id), a_name, relation, str(b_id), b_name),
        )
        return cur.lastrowid


def get(user_ref: str) -> list[dict]:
    """유저 ID 또는 닉네임으로, 그 유저가 포함된 모든 관계를 양방향 조회한다."""
    like = f"%{user_ref}%"
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM relations "
            "WHERE user_a_id = ? OR user_b_id = ? OR user_a_name LIKE ? OR user_b_name LIKE ?",
            (str(user_ref), str(user_ref), like, like),
        ).fetchall()
    return [dict(r) for r in rows]


def remove_for_user(user_id: str) -> int:
    with _conn() as c:
        cur = c.execute(
            "DELETE FROM relations WHERE user_a_id = ? OR user_b_id = ?",
            (str(user_id), str(user_id)),
        )
        return cur.rowcount
