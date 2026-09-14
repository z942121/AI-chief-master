"""Observability 系统的单元测试。

测试覆盖：
1. request_id 唯一生成
2. Trace START / END
3. duration_ms 正确统计
4. Span START / END / FAILED
5. 多 Span 并行不互相覆盖
6. Retry 正确记录
7. Critic score 正确记录
8. RAG hit / miss 正确统计
9. Tavily success / failure 正确统计
10. MetricsCollector counter 正确
11. Metrics API 返回 JSON
12. 多 request 之间 Trace 不串
13. thread_id 与 request_id 不混淆
"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from app.observability.trace import (
    generate_request_id,
    start_trace,
    set_trace_context,
    get_trace_context,
    start_span,
    end_span,
    finish_trace,
    clear_trace_context,
    record_retry,
    record_critic,
    record_llm_call,
    record_retrieval,
)
from app.observability.metrics import get_metrics_collector


class TestRequestId:
    def test_unique_ids(self):
        id1 = generate_request_id()
        id2 = generate_request_id()
        assert id1 != id2

    def test_format(self):
        rid = generate_request_id()
        assert rid.startswith("req_")

    def test_contains_timestamp(self):
        rid = generate_request_id()
        # req_<timestamp>_<8hex>
        parts = rid.split("_")
        assert len(parts) == 3
        assert len(parts[2]) == 8


class TestTraceLifecycle:
    def test_start_and_finish(self):
        trace = start_trace("thread_test_1")
        assert trace.thread_id == "thread_test_1"
        assert trace.status == "running"
        assert trace.request_id.startswith("req_")

        time.sleep(0.01)
        finish_trace(trace, status="success")
        assert trace.status == "success"
        assert trace.duration_ms > 0

    def test_trace_context_set_get(self):
        trace = start_trace("thread_test_2")
        set_trace_context(trace)
        retrieved = get_trace_context()
        assert retrieved is not None
        assert retrieved.request_id == trace.request_id

        clear_trace_context()
        assert get_trace_context() is None

    def test_trace_duration_correct(self):
        trace = start_trace("thread_test_3")
        time.sleep(0.05)
        finish_trace(trace, status="success")
        assert trace.duration_ms >= 40  # 至少 40ms


class TestSpanLifecycle:
    def test_span_start_end(self):
        trace = start_trace("thread_span_1")
        set_trace_context(trace)

        span = start_span("ingredient_agent", "ingredient")
        time.sleep(0.01)
        end_span(span, status="success")

        assert span.status == "success"
        assert span.duration_ms > 0
        assert len(trace.spans) == 1

        clear_trace_context()
        finish_trace(trace, status="success")

    def test_span_failed(self):
        trace = start_trace("thread_span_2")
        set_trace_context(trace)

        span = start_span("recipe_agent", "recipe")
        time.sleep(0.01)
        end_span(span, status="failed", error="test error")

        assert span.status == "failed"
        assert span.error == "test error"
        assert trace.failed_stage == "recipe_agent"

        clear_trace_context()
        finish_trace(trace, status="failed")

    def test_multiple_spans_parallel(self):
        """测试并行 Span 不互相覆盖。"""
        trace = start_trace("thread_parallel")
        set_trace_context(trace)

        span1 = start_span("ingredient_agent", "ingredient")
        span2 = start_span("preference_agent", "preference")

        assert len(trace.spans) == 2

        end_span(span2, status="success")
        end_span(span1, status="success")

        assert trace.spans[0].name == "ingredient_agent"
        assert trace.spans[1].name == "preference_agent"

        clear_trace_context()
        finish_trace(trace, status="success")


class TestRetryObservability:
    def test_record_retry(self):
        trace = start_trace("thread_retry_1")
        set_trace_context(trace)

        record_retry(target="recipe", reason="食材不匹配")
        assert trace.retry_count == 1

        record_retry(target="nutrition", reason="营养数据缺失")
        assert trace.retry_count == 2

        clear_trace_context()
        finish_trace(trace, status="success")

        mc = get_metrics_collector()
        # MetricsCollector 应该记录了 2 次 retry
        assert mc.to_dict()["retry"]["total"] >= 2

    def test_record_critic(self):
        trace = start_trace("thread_critic_1")
        set_trace_context(trace)

        record_critic(
            score=61,
            passed=False,
            retry_target="recipe",
            issues=["食材不匹配"],
            retry_count=1,
        )

        clear_trace_context()
        finish_trace(trace, status="success")


class TestRetrievalObservability:
    def test_rag_hit(self):
        mc = get_metrics_collector()
        mc.reset()

        record_retrieval("rag", query="牛肉 土豆", candidates=5,
                         passed=3, filtered=2, latency_ms=210, status="success")
        mc.record_rag(hit=True)

        metrics = mc.to_dict()
        assert metrics["retrieval"]["rag_calls"] == 1
        assert metrics["retrieval"]["rag_hits"] == 1
        assert metrics["retrieval"]["rag_hit_rate"] == 1.0

    def test_rag_miss(self):
        mc = get_metrics_collector()
        mc.reset()

        record_retrieval("rag", query="未知食材", candidates=5,
                         passed=0, filtered=5, latency_ms=210, status="success")
        mc.record_rag(hit=False)

        metrics = mc.to_dict()
        assert metrics["retrieval"]["rag_calls"] == 1
        assert metrics["retrieval"]["rag_hits"] == 0
        assert metrics["retrieval"]["rag_hit_rate"] == 0.0

    def test_tavily_success(self):
        mc = get_metrics_collector()
        mc.reset()

        record_retrieval("tavily", query="牛肉 土豆 菜谱",
                         results=5, latency_ms=2830, status="success")
        mc.record_tavily(success=True)

        metrics = mc.to_dict()
        assert metrics["retrieval"]["tavily_calls"] == 1
        assert metrics["retrieval"]["tavily_success"] == 1
        assert metrics["retrieval"]["tavily_failed"] == 0

    def test_tavily_failure(self):
        mc = get_metrics_collector()
        mc.reset()

        record_retrieval("tavily", query="牛肉 土豆 菜谱",
                         results=0, latency_ms=5000, status="failed",
                         error="timeout")
        mc.record_tavily(success=False)

        metrics = mc.to_dict()
        assert metrics["retrieval"]["tavily_calls"] == 1
        assert metrics["retrieval"]["tavily_failed"] == 1
        assert metrics["retrieval"]["tavily_success"] == 0

    def test_dedup_metrics(self):
        record_retrieval("dedup", before=8, after=7, removed=1)
        # 只要不报错就行

    def test_rrf_metrics(self):
        record_retrieval("rrf", candidate="土豆炖牛肉",
                        rag_rank=1, tavily_rank=3, rrf_score=0.01639)

    def test_rerank_metrics(self):
        record_retrieval("rerank", title="土豆炖牛肉",
                        ingredient_match=1.0, rrf_score=0.01639,
                        final_score=0.87)


class TestMetricsCollector:
    def test_request_counter(self):
        mc = get_metrics_collector()
        mc.reset()

        mc.record_request("success", {"ingredient_agent": 3000})
        mc.record_request("success", {"ingredient_agent": 4000})
        mc.record_request("failed", {})

        metrics = mc.to_dict()
        assert metrics["requests"]["total"] == 3
        assert metrics["requests"]["success"] == 2
        assert metrics["requests"]["failed"] == 1

    def test_agent_latency(self):
        mc = get_metrics_collector()
        mc.reset()

        mc.record_request("success", {"recipe_agent": 8000})
        mc.record_request("success", {"recipe_agent": 9000})

        metrics = mc.to_dict()
        assert metrics["agents"]["recipe_agent"]["count"] == 2
        assert metrics["agents"]["recipe_agent"]["avg_latency_ms"] == 8500.0

    def test_retry_metrics(self):
        mc = get_metrics_collector()
        mc.reset()

        mc.record_retry("recipe")
        mc.record_retry("nutrition")
        mc.record_retry("recipe")

        metrics = mc.to_dict()
        assert metrics["retry"]["total"] == 3
        assert metrics["retry"]["recipe"] == 2
        assert metrics["retry"]["nutrition"] == 1

    def test_llm_metrics(self):
        mc = get_metrics_collector()
        mc.reset()

        mc.record_llm_call("RecipeAgent", 5000, "success")
        mc.record_llm_call("RecipeAgent", 3000, "success")
        mc.record_llm_call("RecipeAgent", 1000, "failed")

        metrics = mc.to_dict()
        assert metrics["llm"]["call_count"] == 3
        assert metrics["llm"]["avg_latency_ms"] == 3000.0

    def test_metrics_json_serializable(self):
        mc = get_metrics_collector()
        mc.reset()

        mc.record_request("success", {"ingredient_agent": 3000})
        mc.record_rag(hit=True)
        mc.record_tavily(success=True)
        mc.record_retry("recipe")

        import json
        metrics = mc.to_dict()
        # 确保可以序列化为 JSON
        json_str = json.dumps(metrics)
        assert isinstance(json_str, str)

        # 确保结构正确
        parsed = json.loads(json_str)
        assert "requests" in parsed
        assert "agents" in parsed
        assert "retrieval" in parsed
        assert "retry" in parsed
        assert "llm" in parsed


class TestMultiRequestIsolation:
    def test_traces_not_cross_contaminated(self):
        """多个 request 之间 Trace 不串。"""
        mc = get_metrics_collector()
        mc.reset()

        # Request 1
        trace1 = start_trace("thread_001")
        set_trace_context(trace1)
        span1 = start_span("ingredient_agent", "ingredient")
        end_span(span1, status="success")
        finish_trace(trace1, status="success")
        clear_trace_context()

        # Request 2
        trace2 = start_trace("thread_002")
        set_trace_context(trace2)
        span2 = start_span("ingredient_agent", "ingredient")
        end_span(span2, status="success")
        finish_trace(trace2, status="success")
        clear_trace_context()

        # 验证不串
        assert trace1.request_id != trace2.request_id
        assert trace1.thread_id != trace2.thread_id
        assert len(trace1.spans) == 1
        assert len(trace2.spans) == 1
        assert trace1.spans[0].name == "ingredient_agent"
        assert trace2.spans[0].name == "ingredient_agent"

        # Metrics 应该有 2 个请求
        metrics = mc.to_dict()
        assert metrics["requests"]["total"] == 2

    def test_thread_vs_request(self):
        """thread_id 和 request_id 不混淆。"""
        # 同一个 thread 可以有多个 request
        trace1 = start_trace("thread_same")
        trace2 = start_trace("thread_same")

        assert trace1.thread_id == trace2.thread_id
        assert trace1.request_id != trace2.request_id

    def test_no_trace_context_outside_request(self):
        """没有 Trace 上下文时 start_span 不报错。"""
        clear_trace_context()
        span = start_span("test_agent", "test")
        end_span(span, status="success")
        # 不报错即可


class TestEffectiveIngredientsNotAffected:
    """验证 Observability 不影响 effective_ingredients。"""

    def test_ingredient_context_still_works(self):
        from app.agents.ingredient_context import detect_operation, merge_ingredients

        # Observability 存在后，增量合并仍然正常
        last = [{"name": "牛肉", "amount": "500g", "freshness": "新鲜"}]
        current = [{"name": "土豆", "amount": "2个", "freshness": "新鲜"}]
        op = detect_operation("再加两个土豆")
        effective = merge_ingredients(current, op, last)

        names = [i["name"] for i in effective]
        assert "牛肉" in names
        assert "土豆" in names
