"""内存 MetricsCollector。

只使用 Python 内存，不写入数据库、不引入 Redis。

统计：
- 请求总数 / 成功 / 失败
- 各 Agent 调用次数 + 平均延迟
- RAG 调用 / 命中
- Tavily 调用 / 成功 / 失败
- Retry 总数 / 分类
- LLM 调用
"""
import threading
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


class MetricsCollector:
    """线程安全的内存指标收集器。"""

    def __init__(self):
        self._lock = threading.Lock()

        # 请求统计
        self._total_requests = 0
        self._success_requests = 0
        self._failed_requests = 0
        self._requests_with_retry = 0

        # Agent 统计
        self._agent_count: dict[str, int] = defaultdict(int)
        self._agent_latency_sum: dict[str, int] = defaultdict(int)

        # RAG 统计
        self._rag_call_count = 0
        self._rag_hit_count = 0

        # Tavily 统计
        self._tavily_call_count = 0
        self._tavily_success_count = 0
        self._tavily_failed_count = 0

        # Retry 统计
        self._total_retry = 0
        self._recipe_retry = 0
        self._nutrition_retry = 0
        self._planning_retry = 0

        # LLM 统计
        self._llm_call_count = 0
        self._llm_latency_sum = 0

        # Retrieval 统计
        self._retrieval_latency_sum = 0
        self._retrieval_count = 0

    def record_request(self, status: str, agent_latencies: dict[str, int]) -> None:
        """记录一次请求完成。"""
        with self._lock:
            self._total_requests += 1
            if status == "success":
                self._success_requests += 1
            else:
                self._failed_requests += 1

            for agent_name, latency_ms in agent_latencies.items():
                self._agent_count[agent_name] += 1
                self._agent_latency_sum[agent_name] += latency_ms

    def record_retry(self, target: str) -> None:
        """记录一次 Retry。"""
        with self._lock:
            self._total_retry += 1
            if target == "recipe":
                self._recipe_retry += 1
            elif target == "nutrition":
                self._nutrition_retry += 1
            elif target == "planning":
                self._planning_retry += 1

    def record_rag(self, hit: bool) -> None:
        """记录一次 RAG 调用。"""
        with self._lock:
            self._rag_call_count += 1
            if hit:
                self._rag_hit_count += 1

    def record_tavily(self, success: bool) -> None:
        """记录一次 Tavily 调用。"""
        with self._lock:
            self._tavily_call_count += 1
            if success:
                self._tavily_success_count += 1
            else:
                self._tavily_failed_count += 1

    def record_llm_call(self, agent: str, latency_ms: int, status: str) -> None:
        """记录一次 LLM 调用。"""
        with self._lock:
            self._llm_call_count += 1
            self._llm_latency_sum += latency_ms

    def record_retrieval_latency(self, latency_ms: int) -> None:
        """记录检索延迟。"""
        with self._lock:
            self._retrieval_count += 1
            self._retrieval_latency_sum += latency_ms

    def to_dict(self) -> dict:
        """输出 JSON serializable 的指标快照。"""
        with self._lock:
            total_req = self._total_requests
            total_retry = self._total_retry

            agents = {}
            for name in self._agent_count:
                count = self._agent_count[name]
                avg_ms = self._agent_latency_sum[name] / count if count > 0 else 0
                agents[name] = {
                    "count": count,
                    "avg_latency_ms": round(avg_ms, 1),
                }

            rag_hit_rate = (
                self._rag_hit_count / self._rag_call_count
                if self._rag_call_count > 0
                else 0.0
            )

            retry_rate = (
                self._requests_with_retry / total_req
                if total_req > 0
                else 0.0
            )

            tavily_success_rate = (
                self._tavily_success_count / self._tavily_call_count
                if self._tavily_call_count > 0
                else 0.0
            )

            avg_llm_latency = (
                self._llm_latency_sum / self._llm_call_count
                if self._llm_call_count > 0
                else 0.0
            )

            avg_retrieval_latency = (
                self._retrieval_latency_sum / self._retrieval_count
                if self._retrieval_count > 0
                else 0.0
            )

            return {
                "requests": {
                    "total": total_req,
                    "success": self._success_requests,
                    "failed": self._failed_requests,
                },
                "retry": {
                    "total": total_retry,
                    "recipe": self._recipe_retry,
                    "nutrition": self._nutrition_retry,
                    "planning": self._planning_retry,
                    "rate": round(retry_rate, 4),
                },
                "agents": agents,
                "retrieval": {
                    "rag_calls": self._rag_call_count,
                    "rag_hits": self._rag_hit_count,
                    "rag_hit_rate": round(rag_hit_rate, 4),
                    "tavily_calls": self._tavily_call_count,
                    "tavily_success": self._tavily_success_count,
                    "tavily_failed": self._tavily_failed_count,
                    "tavily_success_rate": round(tavily_success_rate, 4),
                    "avg_retrieval_latency_ms": round(avg_retrieval_latency, 1),
                },
                "llm": {
                    "call_count": self._llm_call_count,
                    "avg_latency_ms": round(avg_llm_latency, 1),
                },
            }

    def reset(self) -> None:
        """重置所有指标（用于测试）。"""
        with self._lock:
            self._total_requests = 0
            self._success_requests = 0
            self._failed_requests = 0
            self._requests_with_retry = 0
            self._agent_count.clear()
            self._agent_latency_sum.clear()
            self._rag_call_count = 0
            self._rag_hit_count = 0
            self._tavily_call_count = 0
            self._tavily_success_count = 0
            self._tavily_failed_count = 0
            self._total_retry = 0
            self._recipe_retry = 0
            self._nutrition_retry = 0
            self._planning_retry = 0
            self._llm_call_count = 0
            self._llm_latency_sum = 0
            self._retrieval_latency_sum = 0
            self._retrieval_count = 0


# 全局单例
_metrics_collector: MetricsCollector | None = None


def get_metrics_collector() -> MetricsCollector:
    """获取全局 MetricsCollector 单例。"""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector
