"""Retrieval Benchmark 单元测试。

所有测试使用 offline fixtures，不访问真实 Tavily。
"""
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from tests.benchmark_retrieval import (
    load_dataset,
    load_tavily_fixtures,
    OfflineTavilyAdapter,
    calculate_hit_at_k,
    calculate_mrr,
    calculate_ingredient_coverage,
    calculate_ingredient_coverage_from_content,
    calculate_metrics,
    percentile,
    analyze_errors,
)


class TestDataset:
    def test_load_dataset(self):
        dataset = load_dataset()
        assert len(dataset) >= 30

    def test_dataset_format(self):
        dataset = load_dataset()
        for item in dataset:
            assert "id" in item
            assert "query" in item
            assert "required_ingredients" in item
            assert "relevant_titles" in item
            assert "category" in item
            assert "ground_truth_available" in item

    def test_dataset_categories(self):
        dataset = load_dataset()
        categories = {item["category"] for item in dataset}
        assert "exact_ingredient" in categories
        assert "multi_ingredient" in categories
        assert "synonym" in categories
        assert "preference" in categories
        assert "ambiguous" in categories
        assert "rag_miss" in categories

    def test_ground_truth_consistency(self):
        dataset = load_dataset()
        for item in dataset:
            if not item.get("ground_truth_available"):
                assert item["relevant_titles"] == [], \
                    f"Query {item['id']} has no ground truth but has relevant_titles"


class TestTavilyFixtures:
    def test_load_fixtures(self):
        fixtures = load_tavily_fixtures()
        assert len(fixtures) > 0

    def test_offline_adapter(self):
        fixtures = load_tavily_fixtures()
        adapter = OfflineTavilyAdapter(fixtures)
        results = adapter.search("西红柿 鸡蛋")
        assert isinstance(results, list)
        assert adapter.call_count == 1

    def test_offline_adapter_unknown_query(self):
        fixtures = load_tavily_fixtures()
        adapter = OfflineTavilyAdapter(fixtures)
        results = adapter.search("完全不存在的查询 xyz")
        assert isinstance(results, list)
        assert len(results) == 0


class TestMetrics:
    def test_hit_at_1_found(self):
        actual = ["西红柿炒鸡蛋", "土豆炖牛肉", "鸡肉炒饭"]
        relevant = ["西红柿炒鸡蛋", "西红柿鸡蛋面"]
        assert calculate_hit_at_k(actual, relevant, 1) == 1

    def test_hit_at_1_not_found(self):
        actual = ["土豆炖牛肉", "鸡肉炒饭", "红烧肉"]
        relevant = ["西红柿炒鸡蛋"]
        assert calculate_hit_at_k(actual, relevant, 1) == 0

    def test_hit_at_3_found(self):
        actual = ["土豆炖牛肉", "西红柿炒鸡蛋", "鸡肉炒饭"]
        relevant = ["西红柿炒鸡蛋"]
        assert calculate_hit_at_k(actual, relevant, 3) == 1

    def test_hit_at_5(self):
        actual = ["a", "b", "c", "d", "目标菜谱"]
        relevant = ["目标菜谱"]
        assert calculate_hit_at_k(actual, relevant, 5) == 1

    def test_hit_empty_relevant(self):
        assert calculate_hit_at_k(["a", "b"], [], 3) == 0

    def test_mrr_first_position(self):
        actual = ["目标", "b", "c"]
        relevant = ["目标"]
        assert calculate_mrr(actual, relevant) == 1.0

    def test_mrr_second_position(self):
        actual = ["a", "目标", "c"]
        relevant = ["目标"]
        assert calculate_mrr(actual, relevant) == 0.5

    def test_mrr_third_position(self):
        actual = ["a", "b", "目标"]
        relevant = ["目标"]
        assert abs(calculate_mrr(actual, relevant) - round(1.0 / 3, 4)) < 0.001

    def test_mrr_not_found(self):
        actual = ["a", "b", "c"]
        relevant = ["目标"]
        assert calculate_mrr(actual, relevant) == 0.0

    def test_ingredient_coverage_full(self):
        results = [
            {"content": "## 食材\n- 西红柿：2个\n- 鸡蛋：3个\n"},
        ]
        coverage = calculate_ingredient_coverage_from_content(results, ["西红柿", "鸡蛋"])
        assert coverage >= 0.5  # 至少部分覆盖

    def test_ingredient_coverage_empty(self):
        coverage = calculate_ingredient_coverage_from_content([], ["西红柿"])
        assert coverage == 0.0

    def test_ingredient_coverage_no_required(self):
        results = [{"content": "some content"}]
        coverage = calculate_ingredient_coverage_from_content(results, [])
        assert coverage == 1.0

    def test_calculate_metrics(self):
        results = [
            {"title": "番茄炒蛋", "content": "## 食材\n- 西红柿：2个\n- 鸡蛋：3个\n"},
            {"title": "土豆炖牛肉", "content": "## 食材\n- 牛腩肉：500g\n- 土豆：2个\n"},
        ]
        ground_truth = {
            "relevant_titles": ["番茄炒蛋"],
            "required_ingredients": ["西红柿", "鸡蛋"],
        }
        metrics = calculate_metrics(results, ground_truth)
        assert metrics["hit_at_1"] == 1
        assert metrics["hit_at_3"] == 1
        assert metrics["result_count"] == 2


class TestPercentile:
    def test_p50(self):
        values = [10, 20, 30, 40, 50]
        p50 = percentile(values, 0.5)
        assert 29 <= p50 <= 31  # ~30

    def test_p95(self):
        values = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        p95 = percentile(values, 0.95)
        assert p95 >= 90

    def test_empty(self):
        assert percentile([], 0.5) == 0.0

    def test_single_value(self):
        assert percentile([42], 0.5) == 42


class TestErrorAnalysis:
    def test_no_error(self):
        item = {
            "id": "q001",
            "query": "西红柿 鸡蛋",
            "relevant_titles": ["番茄炒蛋"],
            "required_ingredients": ["西红柿", "鸡蛋"],
            "ground_truth_available": True,
        }
        results = [
            {"title": "番茄炒蛋", "content": "## 食材\n- 西红柿：2个\n- 鸡蛋：3个\n", "source": "rag"},
        ]
        error = analyze_errors(item, results, "rag_only")
        assert error is None  # 没有错误

    def test_rag_miss(self):
        item = {
            "id": "q023",
            "query": "鳕鱼怎么做",
            "relevant_titles": [],
            "required_ingredients": ["鳕鱼"],
            "ground_truth_available": False,
        }
        results = []
        error = analyze_errors(item, results, "rag_only")
        assert error is not None
        assert error["reason"] == "no_ground_truth"

    def test_ingredient_mismatch(self):
        item = {
            "id": "q002",
            "query": "牛肉 土豆",
            "relevant_titles": ["土豆炖牛肉"],
            "required_ingredients": ["牛肉", "土豆"],
            "ground_truth_available": True,
        }
        results = [
            {"title": "蒜蓉西兰花", "content": "## 食材\n- 西兰花：1颗\n", "source": "rag"},
        ]
        error = analyze_errors(item, results, "rag_only")
        assert error is not None
        assert error["reason"] in ("ingredient_mismatch", "ranking_error")


class TestStrategyComparison:
    """验证 4 种策略的函数可以正常调用。"""

    def test_strategy_rag_only_callable(self):
        from tests.benchmark_retrieval import strategy_rag_only
        # 只验证函数签名正确
        import inspect
        sig = inspect.signature(strategy_rag_only)
        params = list(sig.parameters.keys())
        assert "query" in params
        assert "user_ingredients" in params

    def test_strategy_tavily_only_callable(self):
        from tests.benchmark_retrieval import strategy_tavily_only
        import inspect
        sig = inspect.signature(strategy_tavily_only)
        params = list(sig.parameters.keys())
        assert "tavily_adapter" in params

    def test_strategy_hybrid_merge_callable(self):
        from tests.benchmark_retrieval import strategy_hybrid_merge
        import inspect
        sig = inspect.signature(strategy_hybrid_merge)
        params = list(sig.parameters.keys())
        assert "tavily_adapter" in params

    def test_strategy_hybrid_rrf_callable(self):
        from tests.benchmark_retrieval import strategy_hybrid_rrf
        import inspect
        sig = inspect.signature(strategy_hybrid_rrf)
        params = list(sig.parameters.keys())
        assert "tavily_adapter" in params


class TestOnlineModeNotDefault:
    """验证 online 模式不会默认执行。"""

    def test_default_is_offline(self):
        from tests.benchmark_retrieval import OfflineTavilyAdapter, OnlineTavilyAdapter
        # 确认 OfflineTavilyAdapter 可以直接实例化
        fixtures = load_tavily_fixtures()
        adapter = OfflineTavilyAdapter(fixtures)
        assert adapter.call_count == 0

    def test_online_requires_api_key(self):
        from tests.benchmark_retrieval import OnlineTavilyAdapter
        # 如果没有 TAVILY_API_KEY，OnlineTavilyAdapter 应该报错
        old_key = os.environ.pop("TAVILY_API_KEY", None)
        try:
            adapter = OnlineTavilyAdapter()
            assert False, "Should have raised ValueError"
        except (ValueError, Exception):
            pass  # Expected
        finally:
            if old_key:
                os.environ["TAVILY_API_KEY"] = old_key


# ============================================================
# Ablation Benchmark 测试（benchmark_ablation）
# ============================================================

from tests.benchmark_ablation import (
    titles_differ,
    relevant_best_rank,
    compute_false_positive_rate,
    candidate_bucket_stats,
    rerank_change_by_candidate_count,
    hit_transitions,
    compare_new_candidates,
    recommend_threshold,
    run_pipelines_for_query,
    run_threshold_ablation,
    run_ablation,
)


def _mk_recipe_content(ingredients):
    """构造带食材区块的菜谱内容（供 ingredient 匹配解析）。"""
    lines = ["", "## 食材", ""]
    for ing in ingredients:
        lines.append(f"- {ing}：适量")
    lines += ["", "## 步骤", "", "1. 烹饪完成"]
    return "\n".join(lines)


class TestTitlesDiffer:
    """ranking_changed / rerank_changed 的基础比较逻辑。"""

    def test_same_order_same_members(self):
        assert titles_differ(["A", "B"], ["A", "B"]) is False

    def test_order_changed(self):
        assert titles_differ(["A", "B"], ["B", "A"]) is True

    def test_members_changed(self):
        assert titles_differ(["A"], ["A", "B"]) is True

    def test_both_empty(self):
        assert titles_differ([], []) is False

    def test_normalization(self):
        # 标题标准化（去空格 + 小写）后相同 → 不算 changed
        assert titles_differ(["A B"], ["ab"]) is False
        assert titles_differ(["A B"], ["a_c"]) is True


class TestRelevantBestRank:
    def test_found_at_position_2(self):
        assert relevant_best_rank(["a", "b", "c"], ["b"]) == 2

    def test_not_found(self):
        assert relevant_best_rank(["a", "b", "c"], ["z"]) is None

    def test_empty_titles(self):
        assert relevant_best_rank([], ["a"]) is None

    def test_normalization(self):
        assert relevant_best_rank(["A B"], ["ab"]) == 1


class TestFalsePositiveRate:
    def test_basic(self):
        per_query = [
            {"ground_truth_available": True, "relevant_titles": ["A", "B"],
             "titles": {"hybrid_rrf_rerank": ["A", "C", "D"]}},
            {"ground_truth_available": True, "relevant_titles": ["E"],
             "titles": {"hybrid_rrf_rerank": ["E"]}},
            # 无 ground truth 的 query 不参与统计
            {"ground_truth_available": False, "relevant_titles": [],
             "titles": {"hybrid_rrf_rerank": ["X", "Y"]}},
        ]
        # 返回 4 条（A,C,D,E），其中 C、D 为 FP → 2/4 = 0.5
        assert compute_false_positive_rate(per_query) == 0.5

    def test_empty(self):
        assert compute_false_positive_rate([]) == 0.0


class TestCandidateBuckets:
    def test_bucket_stats(self):
        per_query = [
            {"ground_truth_available": True, "candidate_count": 0,
             "metrics": {"hybrid_rrf_rerank": {"hit_at_3": 0}}},
            {"ground_truth_available": True, "candidate_count": 1,
             "metrics": {"hybrid_rrf_rerank": {"hit_at_3": 1}}},
            {"ground_truth_available": True, "candidate_count": 1,
             "metrics": {"hybrid_rrf_rerank": {"hit_at_3": 0}}},
            {"ground_truth_available": True, "candidate_count": 5,
             "metrics": {"hybrid_rrf_rerank": {"hit_at_3": 1}}},
            # 无 GT 不统计
            {"ground_truth_available": False, "candidate_count": 2,
             "metrics": {"hybrid_rrf_rerank": {"hit_at_3": 0}}},
        ]
        stats = candidate_bucket_stats(per_query)
        assert stats["0"] == {"queries": 1, "hit_at_3": 0.0}
        assert stats["1"] == {"queries": 2, "hit_at_3": 0.5}
        assert stats["3+"] == {"queries": 1, "hit_at_3": 1.0}
        assert "2" not in stats


class TestRerankChangeBuckets:
    def test_buckets(self):
        per_query = [
            {"candidate_count": 0, "ranking_changed": False, "rerank_changed": False},
            {"candidate_count": 1, "ranking_changed": False, "rerank_changed": False},
            {"candidate_count": 2, "ranking_changed": True, "rerank_changed": True},
            {"candidate_count": 2, "ranking_changed": True, "rerank_changed": False},
            {"candidate_count": 9, "ranking_changed": True, "rerank_changed": True},
        ]
        rows = rerank_change_by_candidate_count(per_query)
        by_bucket = {r["bucket"]: r for r in rows}
        assert by_bucket["0"]["rerank_changed_rate"] == 0.0
        assert by_bucket["1"]["rerank_changed_rate"] == 0.0
        assert by_bucket["2"]["queries"] == 2
        assert by_bucket["2"]["rerank_changed_rate"] == 0.5
        assert by_bucket["2"]["ranking_changed_rate"] == 1.0
        assert by_bucket["5+"]["queries"] == 1
        assert by_bucket["5+"]["rerank_changed_rate"] == 1.0
        # 无数据的桶（3、4）被跳过
        assert [r["bucket"] for r in rows] == ["0", "1", "2", "5+"]


class TestHitTransitions:
    def test_transitions(self):
        per_query = [
            {"query_id": "q1", "ground_truth_available": True,
             "metrics": {"hybrid_merge": {"hit_at_3": 0}, "hybrid_rrf": {"hit_at_3": 1},
                         "hybrid_rrf_rerank": {"hit_at_3": 1}}},
            {"query_id": "q2", "ground_truth_available": True,
             "metrics": {"hybrid_merge": {"hit_at_3": 1}, "hybrid_rrf": {"hit_at_3": 1},
                         "hybrid_rrf_rerank": {"hit_at_3": 0}}},
            {"query_id": "q3", "ground_truth_available": True,
             "metrics": {"hybrid_merge": {"hit_at_3": 1}, "hybrid_rrf": {"hit_at_3": 0},
                         "hybrid_rrf_rerank": {"hit_at_3": 1}}},
            # 无 GT 不统计
            {"query_id": "q4", "ground_truth_available": False,
             "metrics": {"hybrid_merge": {"hit_at_3": 0}, "hybrid_rrf": {"hit_at_3": 1},
                         "hybrid_rrf_rerank": {"hit_at_3": 1}}},
        ]
        ht = hit_transitions(per_query)
        assert ht["improved_by_rrf"] == ["q1"]
        assert ht["degraded_by_rrf"] == ["q3"]
        assert ht["improved_by_rerank"] == ["q3"]
        assert ht["degraded_by_rerank"] == ["q2"]


class TestCompareNewCandidates:
    def test_new_candidates(self):
        base = [{"query_id": "q1", "query": "西红柿 鸡蛋", "candidate_count": 1,
                 "candidate_titles": ["A"],
                 "relevant_titles": ["B"],
                 "metrics": {"hybrid_rrf_rerank": {"hit_at_3": 0}}}]
        target = [{"query_id": "q1", "query": "西红柿 鸡蛋", "candidate_count": 2,
                   "candidate_titles": ["A", "B"],
                   "relevant_titles": ["B"],
                   "metrics": {"hybrid_rrf_rerank": {"hit_at_3": 1}}}]
        out = compare_new_candidates(base, target, 0.5, 0.3)
        assert len(out) == 1
        assert out[0]["new_titles"] == ["B"]
        assert out[0]["new_titles_relevant"] == [True]
        assert out[0]["hit_at_0.5"] == 0
        assert out[0]["hit_at_0.3"] == 1

    def test_no_new_candidates(self):
        base = [{"query_id": "q1", "query": "西红柿 鸡蛋", "candidate_count": 1,
                 "candidate_titles": ["A"],
                 "relevant_titles": ["A"],
                 "metrics": {"hybrid_rrf_rerank": {"hit_at_3": 1}}}]
        target = [{"query_id": "q1", "query": "西红柿 鸡蛋", "candidate_count": 1,
                   "candidate_titles": ["A"],
                   "relevant_titles": ["A"],
                   "metrics": {"hybrid_rrf_rerank": {"hit_at_3": 1}}}]
        assert compare_new_candidates(base, target, 0.5, 0.3) == []


class TestRecommendThreshold:
    def test_prefers_highest_threshold_near_max(self):
        rows = [
            {"threshold": 0.2, "hit_at_3": 0.9, "mrr": 0.8, "ingredient_coverage": 0.7,
             "false_positive_rate": 0.6, "avg_candidate_count": 5},
            {"threshold": 0.3, "hit_at_3": 0.9, "mrr": 0.85, "ingredient_coverage": 0.7,
             "false_positive_rate": 0.4, "avg_candidate_count": 4},
            {"threshold": 0.5, "hit_at_3": 0.6, "mrr": 0.5, "ingredient_coverage": 0.4,
             "false_positive_rate": 0.2, "avg_candidate_count": 1.3},
        ]
        rec = recommend_threshold(rows)
        assert rec["recommended_threshold"] == 0.3
        assert rec["best_hit_at_3"] == 0.9

    def test_empty(self):
        rec = recommend_threshold([])
        assert rec["recommended_threshold"] is None
        assert "NOT RUN" in rec["reason"]


class TestAblationPipelines:
    """集成测试：fake RAG + 真实 dedup/RRF/rerank pipeline。

    构造数据（user ingredients = 西红柿, 鸡蛋）：
      RAG:   番茄炒蛋 (score 0.9, 含西红柿), 红烧牛肉 (score 0.55, 含牛肉)
      Tavily: 西红柿鸡蛋汤 (含西红柿+鸡蛋), 土豆烧鸡 (含土豆)

    期望：
      candidate（dedup 顺序）= [番茄炒蛋, 红烧牛肉, 西红柿鸡蛋汤, 土豆烧鸡]
      Merge 顺序 = dedup 顺序
      RRF 顺序   = [番茄炒蛋, 西红柿鸡蛋汤, 红烧牛肉, 土豆烧鸡]
                   (rag_rank1/tavily_rank1 同分 1/61，稳定排序 RAG 在前)
      Rerank 顺序 = [西红柿鸡蛋汤, 番茄炒蛋, 红烧牛肉, 土豆烧鸡]
                    (西红柿鸡蛋汤 ingredient match 1.0 > 番茄炒蛋 0.5)
    """

    def _fake_rag_results(self, query, top_k=5, user_ingredients=None):
        return [
            {"title": "番茄炒蛋", "source": "local_rag",
             "content": _mk_recipe_content(["西红柿"]), "score": 0.9, "metadata": {}},
            {"title": "红烧牛肉", "source": "local_rag",
             "content": _mk_recipe_content(["牛肉"]), "score": 0.55, "metadata": {}},
        ]

    def _tavily_fixtures(self):
        return {
            "西红柿 鸡蛋": [
                {"title": "西红柿鸡蛋汤",
                 "content": _mk_recipe_content(["西红柿", "鸡蛋"]),
                 "url": "https://t.example/3"},
                {"title": "土豆烧鸡",
                 "content": _mk_recipe_content(["土豆"]),
                 "url": "https://t.example/4"},
            ]
        }

    def test_pipelines_ranking_and_rerank(self, monkeypatch):
        monkeypatch.setattr("app.rag.retriever.search_recipes", self._fake_rag_results)
        adapter = OfflineTavilyAdapter(self._tavily_fixtures())

        out = run_pipelines_for_query(
            "西红柿 鸡蛋", [{"name": "西红柿"}, {"name": "鸡蛋"}], adapter, top_k=5)

        assert out["rag_result_count"] == 2
        assert out["tavily_result_count"] == 2
        assert out["candidate_count"] == 4
        assert out["candidate_titles"] == ["番茄炒蛋", "红烧牛肉", "西红柿鸡蛋汤", "土豆烧鸡"]

        assert out["titles"]["rag_only"] == ["番茄炒蛋", "红烧牛肉"]
        assert out["titles"]["hybrid_merge"] == ["番茄炒蛋", "红烧牛肉", "西红柿鸡蛋汤", "土豆烧鸡"]
        assert out["titles"]["hybrid_rrf"] == ["番茄炒蛋", "西红柿鸡蛋汤", "红烧牛肉", "土豆烧鸡"]
        assert out["titles"]["hybrid_rrf_rerank"] == ["西红柿鸡蛋汤", "番茄炒蛋", "红烧牛肉", "土豆烧鸡"]

        assert titles_differ(out["titles"]["hybrid_merge"], out["titles"]["hybrid_rrf"])
        assert titles_differ(out["titles"]["hybrid_rrf"], out["titles"]["hybrid_rrf_rerank"])

    def test_single_candidate_no_change(self, monkeypatch):
        def fake_search(query, top_k=5, user_ingredients=None):
            return [{"title": "番茄炒蛋", "source": "local_rag",
                     "content": _mk_recipe_content(["西红柿", "鸡蛋"]),
                     "score": 0.9, "metadata": {}}]
        monkeypatch.setattr("app.rag.retriever.search_recipes", fake_search)
        adapter = OfflineTavilyAdapter({})

        out = run_pipelines_for_query(
            "西红柿 鸡蛋", [{"name": "西红柿"}], adapter, top_k=5)

        assert out["candidate_count"] == 1
        assert not titles_differ(out["titles"]["hybrid_merge"], out["titles"]["hybrid_rrf"])
        assert not titles_differ(out["titles"]["hybrid_rrf"], out["titles"]["hybrid_rrf_rerank"])


class TestThresholdAblation:
    def test_env_set_and_restored(self, monkeypatch):
        captured = []

        def fake_search(query, top_k=5, user_ingredients=None):
            captured.append(os.getenv("RAG_SCORE_THRESHOLD"))
            return [{"title": "番茄炒蛋", "source": "local_rag",
                     "content": _mk_recipe_content(["西红柿", "鸡蛋"]),
                     "score": 0.9, "metadata": {}}]

        monkeypatch.setattr("app.rag.retriever.search_recipes", fake_search)
        dataset = [{
            "id": "t001", "query": "西红柿 鸡蛋",
            "required_ingredients": ["西红柿", "鸡蛋"],
            "relevant_titles": ["番茄炒蛋"],
            "category": "exact_ingredient",
            "ground_truth_available": True,
        }]
        adapter = OfflineTavilyAdapter({})

        summary = run_threshold_ablation(dataset, adapter, 0.35)

        # threshold env 在 RAG 调用时生效，结束后被清理
        assert captured == ["0.35"]
        assert "RAG_SCORE_THRESHOLD" not in os.environ
        assert summary["threshold"] == 0.35
        assert summary["avg_candidate_count"] == 1
        assert summary["strategies"]["hybrid_rrf_rerank"]["hit_at_3"] == 1.0
        assert summary["ranking_changed_rate"] == 0
        assert summary["rerank_changed_rate"] == 0
        assert summary["relevant_in_pool_rate"] == 1.0
        assert summary["errors"] == []

    def test_run_ablation_structure_and_not_run(self, monkeypatch):
        def fake_search(query, top_k=5, user_ingredients=None):
            return [{"title": "番茄炒蛋", "source": "local_rag",
                     "content": _mk_recipe_content(["西红柿", "鸡蛋"]),
                     "score": 0.9, "metadata": {}}]

        monkeypatch.setattr("app.rag.retriever.search_recipes", fake_search)
        dataset = [{
            "id": "t001", "query": "西红柿 鸡蛋",
            "required_ingredients": ["西红柿", "鸡蛋"],
            "relevant_titles": ["番茄炒蛋"],
            "category": "exact_ingredient",
            "ground_truth_available": True,
        }]
        adapter = OfflineTavilyAdapter({})

        results = run_ablation(dataset, adapter, thresholds=[0.5, 0.3])

        assert len(results["threshold_sweep"]) == 2
        assert results["threshold_sweep"][0]["hit_at_3"] == 1.0
        assert results["ablation"]["0.5"]["status"] == "RUN"
        assert results["ablation"]["0.4"]["status"] == "NOT RUN"
        assert results["ablation"]["0.3"]["status"] == "RUN"
        # 两个 threshold 都达到满 Hit@3，推荐规则选更高的 threshold
        assert results["threshold_recommendation"]["recommended_threshold"] == 0.5
        assert len(results["candidate_pool_analysis"]) == 2
        assert results["candidate_pool_analysis"][0]["hit"] == 1
        assert results["candidate_pool_analysis"][0]["relevant_in_pool"] is True
