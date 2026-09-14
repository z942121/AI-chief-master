import sqlite3
import os
from contextlib import contextmanager
from app.models.session import Base


_db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "personal_chief.db")
_connection = None


def get_connection():
    global _connection
    if _connection is None:
        _connection = sqlite3.connect(_db_path, check_same_thread=False)
        _connection.row_factory = sqlite3.Row
    return _connection


def init_db():
    """初始化数据库，创建表"""
    conn = get_connection()
    cursor = conn.cursor()

    # 创建 sessions 表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id VARCHAR(255) UNIQUE NOT NULL,
            title VARCHAR(255) NOT NULL DEFAULT '新对话',
            created_at BIGINT NOT NULL,
            updated_at BIGINT NOT NULL
        )
    """)

    # 创建索引
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_thread_id ON sessions(thread_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_updated_at ON sessions(updated_at)")

    conn.commit()
    print("数据库初始化完成")


@contextmanager
def get_cursor():
    """获取数据库游标的上下文管理器"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        yield cursor
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()


# 初始化数据库
init_db()