import time
from app.db.database import get_cursor
from app.models.session import Session


def get_all_sessions() -> list[dict]:
    """获取所有会话，按更新时间倒序"""
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT id, thread_id, title, created_at, updated_at FROM sessions ORDER BY updated_at DESC"
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def save_session(thread_id: str, title: str = "新对话") -> dict:
    """保存或更新会话"""
    now = int(time.time() * 1000)  # 毫秒时间戳

    with get_cursor() as cursor:
        # 检查是否已存在
        cursor.execute("SELECT id, thread_id, title, created_at, updated_at FROM sessions WHERE thread_id = ?", (thread_id,))
        existing = cursor.fetchone()

        if existing:
            # 更新
            cursor.execute(
                "UPDATE sessions SET title = ?, updated_at = ? WHERE thread_id = ?",
                (title, now, thread_id)
            )
            return {
                "id": existing["id"],
                "thread_id": thread_id,
                "title": title,
                "created_at": existing["created_at"],
                "updated_at": now
            }
        else:
            # 新增
            cursor.execute(
                "INSERT INTO sessions (thread_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (thread_id, title, now, now)
            )
            return {
                "id": cursor.lastrowid,
                "thread_id": thread_id,
                "title": title,
                "created_at": now,
                "updated_at": now
            }


def update_session_title(thread_id: str, title: str) -> dict | None:
    """更新会话标题"""
    now = int(time.time() * 1000)

    with get_cursor() as cursor:
        cursor.execute(
            "UPDATE sessions SET title = ?, updated_at = ? WHERE thread_id = ?",
            (title, now, thread_id)
        )

        if cursor.rowcount > 0:
            cursor.execute(
                "SELECT id, thread_id, title, created_at, updated_at FROM sessions WHERE thread_id = ?",
                (thread_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

        return None


def delete_session(thread_id: str) -> bool:
    """删除会话"""
    with get_cursor() as cursor:
        cursor.execute("DELETE FROM sessions WHERE thread_id = ?", (thread_id,))
        return cursor.rowcount > 0


def get_session(thread_id: str) -> dict | None:
    """获取单个会话"""
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT id, thread_id, title, created_at, updated_at FROM sessions WHERE thread_id = ?",
            (thread_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None