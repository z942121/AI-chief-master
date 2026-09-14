import os
import re
import json
import time
import logging
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_tavily import TavilySearch

_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env")
load_dotenv(_env_path)

logger = logging.getLogger(__name__)

MAX_RETRY = 2
MODEL_MAX_RETRY = 1  # 模型调用最多重试 1 次

model = init_chat_model(
    model="qwen3.6-flash-2026-04-16",
    model_provider="openai",
    base_url=os.getenv("DASHSCOPE_BASE_URL"),
    api_key=os.getenv("DASHSCOPE_API_KEY"),
)

web_search = TavilySearch(
    max_results=5,
    topic="general",
)

# MySQL Checkpointer（主）
_mysql_saver = None
_mysql_cm = None  # context manager 引用，用于生命周期管理

# SQLite Checkpointer（保留作为备份，不删除文件）
_sqlite_saver = None
_sqlite_connection = None


def _build_mysql_conn_string() -> str:
    """从环境变量构建 MySQL 连接字符串。"""
    host = os.getenv("MYSQL_HOST", "localhost")
    port = int(os.getenv("MYSQL_PORT", "3306"))
    user = os.getenv("MYSQL_USER", "root")
    password = os.getenv("MYSQL_PASSWORD", "")
    database = os.getenv("MYSQL_DATABASE", "ai_chief")
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"


def get_checkpointer():
    """获取 Checkpointer 实例（懒加载，优先 MySQL，失败回退 SQLite）。

    MySQL 配置可用时使用 PyMySQLSaver；
    配置缺失或连接失败时回退到 SqliteSaver。
    SQLite 文件保留不删除。
    """
    global _mysql_saver, _mysql_cm, _sqlite_saver, _sqlite_connection

    # 优先使用 MySQL
    mysql_host = os.getenv("MYSQL_HOST")
    mysql_user = os.getenv("MYSQL_USER")
    mysql_db = os.getenv("MYSQL_DATABASE")

    if mysql_host and mysql_user and mysql_db and _mysql_saver is None:
        try:
            from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver
            conn_string = _build_mysql_conn_string()
            _mysql_cm = PyMySQLSaver.from_conn_string(conn_string)
            _mysql_saver = _mysql_cm.__enter__()
            _mysql_saver.setup()
            logger.info("[Checkpointer] MySQL Checkpointer 初始化成功")
            return _mysql_saver
        except Exception as e:
            logger.error(f"[Checkpointer] MySQL 初始化失败: {e}")
            logger.warning("[Checkpointer] 回退到 SQLite Checkpointer")
            _mysql_saver = None
            _mysql_cm = None

    # MySQL 已初始化，直接返回
    if _mysql_saver is not None:
        return _mysql_saver

    # MySQL 不可用时使用 SQLite
    if _sqlite_saver is None:
        import sqlite3
        from langgraph.checkpoint.sqlite import SqliteSaver
        db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "..", "data", "personal_chief.db",
        )
        _sqlite_connection = sqlite3.connect(db_path, check_same_thread=False)
        _sqlite_saver = SqliteSaver(_sqlite_connection)
        _sqlite_saver.setup()
        logger.info("[Checkpointer] SQLite Checkpointer 初始化成功")

    return _sqlite_saver


def parse_json_response(text: str):
    """从模型响应中提取 JSON，容忍 markdown 代码块和前后多余文本。"""
    if not text:
        return None

    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        text = match.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    for pattern in [r"\{[\s\S]*\}", r"\[[\s\S]*\]"]:
        m = re.search(pattern, text)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                continue

    return None


def _is_retryable_error(e: Exception) -> bool:
    """判断是否为可重试的网络/连接类异常。"""
    error_str = str(e).lower()
    retryable_keywords = [
        "remoteprotocolerror",
        "incomplete chunked read",
        "peer closed connection",
        "connection reset",
        "connection aborted",
        "broken pipe",
        "timeout",
        "timed out",
        "server disconnected",
        "temporary failure",
    ]
    return any(kw in error_str for kw in retryable_keywords)


def safe_model_invoke(agent_name: str, messages: list, fallback=None):
    """安全的模型调用：针对网络类异常最多重试 MODEL_MAX_RETRY 次。

    Args:
        agent_name: Agent 名称（用于日志）
        messages: 传给模型的消息列表
        fallback: 失败时的返回值，默认为 None

    Returns:
        模型响应对象，或 fallback（全部失败时）
    """
    max_attempts = MODEL_MAX_RETRY + 1
    last_error = None
    _llm_t0 = time.time()

    for attempt in range(1, max_attempts + 1):
        try:
            response = model.invoke(messages)
            _llm_latency = int((time.time() - _llm_t0) * 1000)
            if attempt > 1:
                logger.info(
                    f"[ModelRetry] agent = {agent_name}, attempt = {attempt}/{max_attempts}, success"
                )
            # ===== LLM Observability =====
            try:
                from app.observability.trace import record_llm_call
                record_llm_call(agent=agent_name, latency_ms=_llm_latency,
                                status="success", model="qwen")
            except Exception:
                pass
            return response
        except Exception as e:
            last_error = e
            if _is_retryable_error(e) and attempt < max_attempts:
                logger.warning(
                    f"[ModelRetry] agent = {agent_name}, attempt = {attempt}/{max_attempts}, "
                    f"reason = {type(e).__name__}, retrying..."
                )
                time.sleep(1)  # 等 1 秒再重试
            else:
                break

    # 所有尝试都失败
    _llm_latency = int((time.time() - _llm_t0) * 1000)
    logger.error(
        f"[ModelRetry] agent = {agent_name}, attempt = {max_attempts}/{max_attempts}, "
        f"failed, using fallback. error = {type(last_error).__name__}: {str(last_error)[:200]}"
    )
    # ===== LLM Observability =====
    try:
        from app.observability.trace import record_llm_call
        record_llm_call(agent=agent_name, latency_ms=_llm_latency,
                        status="failed", model="qwen")
    except Exception:
        pass
    return fallback
