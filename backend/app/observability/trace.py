"""轻量级 Trace / Span 系统。

使用 contextvars 传播 request_id，不污染 LangGraph State。
支持多 Span 并行（Ingredient + Preference 并行时不互相覆盖）。

使用方式：
    # 在请求入口处
    trace = start_trace(thread_id)
    set_trace_context(trace)

    # 在 Agent 中
    span = start_span("ingredient_agent", "ingredient")
    ...
    end_span(span, status="success")

    # 在请求结束时
    finish_trace(trace, status="success")
"""
import time
import uuid
import logging
import contextvars
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# contextvars: 请求级别传播，不污染 LangGraph State
_current_trace: contextvars.ContextVar[Optional["TraceContext"]] = contextvars.ContextVar(
    "_current_trace", default=None
)


@dataclass
class Span:
    """一个执行阶段的追踪记录。"""
    name: str
    stage: str
    start_time: float = 0.0
    end_time: float = 0.0
    duration_ms: int = 0
    status: str = "running"  # running | success | failed
    metadata: dict = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class TraceContext:
    """一次完整请求的追踪上下文。"""
    request_id: str
    thread_id: str
    start_time: float = 0.0
    end_time: float = 0.0
    duration_ms: int = 0
    status: str = "running"  # running | success | failed
    spans: list[Span] = field(default_factory=list)
    retry_count: int = 0
    failed_stage: Optional[str] = None
    metadata: dict = field(default_factory=dict)


def generate_request_id() -> str:
    """生成唯一 request_id。"""
    ts = int(time.time())
    short_uuid = uuid.uuid4().hex[:8]
    return f"req_{ts}_{short_uuid}"


def start_trace(thread_id: str) -> TraceContext:
    """开始一次请求 Trace。"""
    trace = TraceContext(
        request_id=generate_request_id(),
        thread_id=thread_id,
        start_time=time.time(),
    )
    logger.info(
        f"[TRACE] request={trace.request_id} thread={trace.thread_id} START"
    )
    return trace


def set_trace_context(trace: TraceContext) -> None:
    """设置当前请求的 Trace 上下文到 contextvars。"""
    _current_trace.set(trace)


def get_trace_context() -> Optional[TraceContext]:
    """获取当前请求的 Trace 上下文。"""
    return _current_trace.get()


def start_span(name: str, stage: str, metadata: Optional[dict] = None) -> Span:
    """开始一个 Span。

    支持多 Span 同时 running（并行 Agent 不会互相覆盖）。
    """
    span = Span(
        name=name,
        stage=stage,
        start_time=time.time(),
        metadata=metadata or {},
    )

    trace = _current_trace.get()
    if trace:
        trace.spans.append(span)

    logger.info(
        f"[AGENT] {name} START "
        f"stage={stage} "
        f"request_id={trace.request_id if trace else 'N/A'} "
        f"thread_id={trace.thread_id if trace else 'N/A'}"
    )
    return span


def end_span(span: Span, status: str = "success", error: Optional[str] = None) -> None:
    """结束一个 Span。"""
    span.end_time = time.time()
    span.duration_ms = int((span.end_time - span.start_time) * 1000)
    span.status = status
    span.error = error

    trace = _current_trace.get()

    if status == "failed":
        logger.info(
            f"[AGENT] {span.name} FAILED "
            f"stage={span.stage} "
            f"duration_ms={span.duration_ms} "
            f"error={error or 'unknown'}"
        )
        if trace and not trace.failed_stage:
            trace.failed_stage = span.name
    else:
        logger.info(
            f"[AGENT] {span.name} END "
            f"stage={span.stage} "
            f"duration_ms={span.duration_ms} "
            f"status={status}"
        )


def record_retry(target: str, reason: Optional[str] = None) -> None:
    """记录一次 Retry。"""
    trace = _current_trace.get()
    if trace:
        trace.retry_count += 1

    logger.info(
        f"[RETRY] "
        f"count={trace.retry_count if trace else 1} "
        f"target={target} "
        f"reason={reason or 'N/A'}"
    )

    # 更新 MetricsCollector
    from app.observability.metrics import get_metrics_collector
    mc = get_metrics_collector()
    mc.record_retry(target)


def record_critic(score: int, passed: bool, retry_target: str,
                  issues: list, retry_count: int) -> None:
    """记录 Critic 审核结果。"""
    logger.info(
        f"[CRITIC] "
        f"score={score} "
        f"passed={passed} "
        f"retry_target={retry_target} "
        f"retry_count={retry_count} "
        f"issues={issues}"
    )

    if not passed and retry_count >= 2:
        logger.info(f"[MAX_RETRY] count={retry_count} action=final")


def record_llm_call(agent: str, latency_ms: int, status: str = "success",
                    model: Optional[str] = None) -> None:
    """记录一次 LLM 调用。"""
    logger.info(
        f"[LLM] "
        f"agent={agent} "
        f"model={model or 'qwen'} "
        f"latency_ms={latency_ms} "
        f"status={status}"
    )

    from app.observability.metrics import get_metrics_collector
    mc = get_metrics_collector()
    mc.record_llm_call(agent, latency_ms, status)


def record_retrieval(stage: str, **kwargs) -> None:
    """记录检索阶段指标。

    Args:
        stage: "rag" | "tavily" | "dedup" | "rrf" | "rerank"
        **kwargs: 各阶段特定字段
    """
    parts = [f"[RETRIEVAL][{stage.upper()}]"]
    for k, v in kwargs.items():
        if k == "query" and isinstance(v, str) and len(v) > 80:
            v = v[:80] + "..."
        parts.append(f"{k}={v}")
    logger.info(" ".join(parts))


def finish_trace(trace: TraceContext, status: str = "success") -> None:
    """结束一次请求 Trace，输出 Summary。"""
    trace.end_time = time.time()
    trace.duration_ms = int((trace.end_time - trace.start_time) * 1000)
    trace.status = status

    logger.info(
        f"[TRACE_SUMMARY] "
        f"request_id={trace.request_id} "
        f"thread_id={trace.thread_id} "
        f"status={trace.status} "
        f"total_duration_ms={trace.duration_ms} "
        f"retry_count={trace.retry_count} "
        f"failed_stage={trace.failed_stage or 'none'}"
    )

    # 更新 MetricsCollector
    from app.observability.metrics import get_metrics_collector
    mc = get_metrics_collector()
    mc.record_request(
        status=status,
        agent_latencies={
            s.name: s.duration_ms
            for s in trace.spans
            if s.status == "success"
        },
    )


def clear_trace_context() -> None:
    """清除当前请求的 Trace 上下文。"""
    _current_trace.set(None)
