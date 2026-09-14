"""生产验证：运行中 backend 的 threshold、Chroma、MySQL Checkpointer、RecipeAgent 检索链路。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

print("=== 1. RAG_SCORE_THRESHOLD ===")
import os
print("env value:", os.getenv("RAG_SCORE_THRESHOLD"))

from app.rag.retriever import get_score_threshold
th = get_score_threshold()
print("get_score_threshold() =", th)
assert abs(th - 0.35) < 1e-9, f"threshold 不等于 0.35: {th}"

print("\n=== 2. Chroma ===")
from app.rag.retriever import get_vector_store
vs = get_vector_store()
col = vs._collection
print("collection:", col.name, "count:", col.count())
assert col.count() > 0

print("\n=== 3. MySQL Checkpointer ===")
from app.agents.shared import get_checkpointer
cp = get_checkpointer()
print("checkpointer type:", type(cp).__name__)
assert type(cp).__name__ == "PyMySQLSaver", "未使用 MySQL Checkpointer"

import pymysql
conn = pymysql.connect(
    host=os.getenv("MYSQL_HOST", "mysql"),
    port=int(os.getenv("MYSQL_PORT", "3306")),
    user=os.getenv("MYSQL_USER"),
    password=os.getenv("MYSQL_PASSWORD"),
    database=os.getenv("MYSQL_DATABASE"),
)
with conn.cursor() as cur:
    cur.execute("SHOW TABLES")
    names = [r[0] for r in cur.fetchall()]
conn.close()
print("tables:", names)
assert any("checkpoints" in n for n in names), "MySQL checkpoints 表不存在"

print("\n=== ALL BASE CHECKS PASSED ===")
