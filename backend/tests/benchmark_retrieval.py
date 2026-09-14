"""Retrieval Benchmark 脚本。

比较 4 种 Retrieval Strategy：
  A. RAG Only
  B. Tavily Only (offline fixtures / online)
  C. Hybrid Merge (简单合并去重)
  D. Hybrid RRF + Ingredient Rerank (完整生产 pipeline)

Metrics：
  Hit@1, Hit@3, Hit@5, MRR, Ingredient Coverage
  Avg/P50/P95 Latency, RAG Hit Rate, Tavily Success Rate, Fallback Rate

Sweep 实验：
  - Threshold (0.30 ~ 0.70)
  - RRF Weight (0.2/0.8 ~ 0.8/0.2)
  - Top-K (1, 3, 5)

用法：
  python tests/benchmark_retrieval.py --offline     # 默认，使用 fixtures
  python tests/benchmark_retrieval.py --online      # 调用真实 Tavily
  python tests/benchmark_retrieval.py --skip-tavily # 完全跳过 Tavily

输出：
  backend/data/benchmark/retrieval_benchmark_results.json
  backend/data/benchmark/retrieval_benchmark_results.csv
  backend/data/benchmark/retrieval_benchmark_report.md
"""
import argparse
import json
import os
import sys
import time
import statistics
import logging
from pathlib import Path

# 将 backend 目录加入 sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

logger = logging.getLogger(__name__)

# ===== 路径常量 =====
DATA_DIR = BACKEND_DIR / "data"
BENCHMARK_DIR = DATA_DIR / "benchmark"
DATASET_PATH = BACKEND_DIR / "tests" / "data" / "retrieval_benchmark.json"
TAVILY_FIXTURES_PATH = BACKEND_DIR / "tests" / "data" / "tavily_benchmark_fixtures.json"


# ============================================================
# 数据加载
# ============================================================

def load_dataset() -> list[dict]:
    """加载 Benchmark Dataset。"""
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_tavily_fixtures() -> dict:
    """加载 Tavily Offline Fixtures。"""
    with open(TAVILY_FIXTURES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    # 构建 query → results 映射
    fixtures = {}
    for item in data.get("fixtures", []):
        fixtures[item["query"]] = item.get("results", [])
    return fixtures


# ============================================================
# Offline Tavily Adapter
# ============================================================

class OfflineTavilyAdapter:
    """用 fixture 模拟 Tavily 搜索结果。"""

    def __init__(self, fixtures: dict):
        self._fixtures = fixtures
        self._call_count = 0
        self._success_count = 0

    def search(self, query: str) -> list[dict]:
        self._call_count += 1
        results = self._fixtures.get(query, [])
        if results:
            self._success_count += 1
        # 模拟网络延迟
        time.sleep(0.002)
        return results

    @property
    def call_count(self):
        return self._call_count

    @property
    def success_rate(self):
        return self._success_count / self._call_count if self._call_count > 0 else 0.0


# ============================================================
# Online Tavily Adapter
# ============================================================

class OnlineTavilyAdapter:
    """调用真实 Tavily API。"""

    def __init__(self):
        from langchain_tavily import TavilySearch
        from app.agents.shared import get_env
        api_key = get_env("TAVILY_API_KEY", "")
        if not api_key:
            raise ValueError("TAVILY_API_KEY not set")
        self._tool = TavilySearch(
            api_key=api_key,
            max_results=5,
            topic="general",
        )
        self._call_count = 0
        self._success_count = 0

    def search(self, query: str) -> list[dict]:
        self._call_count += 1
        try:
            results = self._tool.invoke({"query": query})
            raw = results.get("results", [])
            self._success_count += 1
            return [
                {
                    "title": r.get("title", ""),
                    "content": r.get("content", ""),
                    "source": "tavily",
                    "url": r.get("url", ""),
                }
                for r in raw
            ]
        except Exception as e:
            logger.error(f"[Tavily] online search failed: {e}")
            return []

    @property
    def call_count(self):
        return self._call_count

    @property
    def success_rate(self):
        return self._success_count / self._call_count if self._call_count > 0 else 0.0


# ============================================================
# 4 种 Retrieval Strategy
# ============================================================

def strategy_rag_only(query: str, user_ingredients: list[dict],
                      top_k: int = 5) -> tuple[list[dict], dict]:
    """Strategy A: RAG Only (Chroma)。"""
    from app.rag.retriever import search_recipes as rag_search

    t0 = time.perf_counter()
    results = rag_search(query, top_k=top_k, user_ingredients=user_ingredients)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    latency = {"rag_latency_ms": elapsed_ms, "total_latency_ms": elapsed_ms}
    return results, latency


def strategy_tavily_only(query: str, user_ingredients: list[dict],
                         tavily_adapter, top_k: int = 5) -> tuple[list[dict], dict]:
    """Strategy B: Tavily Only。"""
    t0 = time.perf_counter()
    raw_results = tavily_adapter.search(query)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    results = [
        {
            "title": r.get("title", ""),
            "content": r.get("content", ""),
            "source": "tavily",
            "url": r.get("url", ""),
            "score": 1.0 / (i + 1),  # 简单按顺序赋分
        }
        for i, r in enumerate(raw_results[:top_k])
    ]
    latency = {"tavily_latency_ms": elapsed_ms, "total_latency_ms": elapsed_ms}
    return results, latency


def strategy_hybrid_merge(query: str, user_ingredients: list[dict],
                          tavily_adapter, top_k: int = 5,
                          rag_threshold: float = None) -> tuple[list[dict], dict]:
    """Strategy C: Hybrid Merge (简单去重合并，不做 RRF/Rerank)。"""
    from app.rag.retriever import search_recipes as rag_search
    from app.rag.retrieval_pipeline import deduplicate

    latencies = {}

    # RAG
    t0 = time.perf_counter()
    rag_results = rag_search(query, top_k=top_k, user_ingredients=user_ingredients)
    latencies["rag_latency_ms"] = (time.perf_counter() - t0) * 1000

    # Tavily
    t0 = time.perf_counter()
    tavily_results = tavily_adapter.search(query)
    latencies["tavily_latency_ms"] = (time.perf_counter() - t0) * 1000

    # Dedup
    t0 = time.perf_counter()
    candidates = deduplicate(rag_results, tavily_results)
    latencies["dedup_latency_ms"] = (time.perf_counter() - t0) * 1000

    # 简单合并：按来源分配 rank，取 final_score = 1/(rank+1)
    for c in candidates:
        rank = c.rag_rank or c.tavily_rank or 99
        c.final_score = 1.0 / (rank + 1)

    candidates.sort(key=lambda c: c.final_score, reverse=True)
    final = candidates[:top_k]

    t_total = sum(latencies.values())
    latencies["total_latency_ms"] = t_total

    return [c.to_dict() for c in final], latencies


def strategy_hybrid_rrf(query: str, user_ingredients: list[dict],
                        tavily_adapter, top_k: int = 5,
                        rrf_final_weight: float = None,
                        rrf_ingredient_weight: float = None) -> tuple[list[dict], dict]:
    """Strategy D: Hybrid RRF + Ingredient Rerank (完整生产 pipeline)。"""
    from app.rag.retriever import search_recipes as rag_search
    from app.rag.retrieval_pipeline import (
        deduplicate, assign_ranks, rrf_fusion,
        ingredient_rerank, _get_final_weights
    )

    latencies = {}

    # 如果提供了自定义权重，设置环境变量
    if rrf_final_weight is not None:
        os.environ["RRF_FINAL_WEIGHT"] = str(rrf_final_weight)
    if rrf_ingredient_weight is not None:
        os.environ["RRF_INGREDIENT_WEIGHT"] = str(rrf_ingredient_weight)

    # RAG
    t0 = time.perf_counter()
    rag_results = rag_search(query, top_k=top_k, user_ingredients=user_ingredients)
    latencies["rag_latency_ms"] = (time.perf_counter() - t0) * 1000

    # Tavily
    t0 = time.perf_counter()
    tavily_results = tavily_adapter.search(query)
    latencies["tavily_latency_ms"] = (time.perf_counter() - t0) * 1000

    # Dedup
    t0 = time.perf_counter()
    candidates = deduplicate(rag_results, tavily_results)
    latencies["dedup_latency_ms"] = (time.perf_counter() - t0) * 1000

    # RRF
    t0 = time.perf_counter()
    assign_ranks(candidates)
    rrf_fusion(candidates)
    latencies["rrf_latency_ms"] = (time.perf_counter() - t0) * 1000

    # Rerank
    t0 = time.perf_counter()
    ingredient_rerank(candidates, user_ingredients)
    latencies["rerank_latency_ms"] = (time.perf_counter() - t0) * 1000

    # Sort + Top-K
    candidates.sort(key=lambda c: c.final_score, reverse=True)
    final = candidates[:top_k]

    latencies["total_latency_ms"] = sum(latencies.values())

    return [c.to_dict() for c in final], latencies


# ============================================================
# Metrics 计算
# ============================================================

def _normalize_title(title: str) -> str:
    import re
    return re.sub(r"\s+", "", title).lower()


def calculate_hit_at_k(actual_titles: list[str], relevant_titles: list[str], k: int) -> int:
    """Hit@K: relevant_titles 中任意一个出现在 actual_titles Top-K 中则为 1。"""
    if not relevant_titles:
        return 0
    top_k_titles = actual_titles[:k]
    actual_normalized = {_normalize_title(t) for t in top_k_titles}
    relevant_normalized = {_normalize_title(t) for t in relevant_titles}
    return 1 if actual_normalized & relevant_normalized else 0


def calculate_mrr(actual_titles: list[str], relevant_titles: list[str]) -> float:
    """MRR: 第一个 relevant recipe 排名的倒数。"""
    if not relevant_titles:
        return 0.0
    relevant_normalized = {_normalize_title(t) for t in relevant_titles}
    for i, title in enumerate(actual_titles):
        if _normalize_title(title) in relevant_normalized:
            return 1.0 / (i + 1)
    return 0.0


def calculate_ingredient_coverage(actual_titles: list[str], required_ingredients: list[str]) -> float:
    """Ingredient Coverage: Top-K 结果中能覆盖多少 required ingredients。"""
    if not required_ingredients:
        return 1.0  # 没有要求则视为全覆盖

    from app.rag.retriever import _extract_recipe_ingredients, _normalize_ingredient
    from app.rag.retrieval_pipeline import RetrievalCandidate

    # 从实际结果中提取所有食材
    all_recipe_ingredients = set()
    for title_str in actual_titles:
        # 我们无法从 title 恢复 content，所以这里用 normalize 匹配
        norm = _normalize_ingredient(title_str)
        all_recipe_ingredients.add(norm)

    # 直接匹配 required ingredients
    matched = 0
    for ing in required_ingredients:
        norm_ing = _normalize_ingredient(ing)
        for recipe_ing in all_recipe_ingredients:
            if norm_ing in recipe_ing or recipe_ing in norm_ing:
                matched += 1
                break

    return matched / len(required_ingredients)


def calculate_ingredient_coverage_from_content(results: list[dict], required_ingredients: list[str]) -> float:
    """从检索结果的 content 中提取食材计算覆盖率。"""
    if not required_ingredients:
        return 1.0

    from app.rag.retriever import _extract_recipe_ingredients, _normalize_ingredient

    all_recipe_ingredients = set()
    for r in results:
        content = r.get("content", "")
        ings = _extract_recipe_ingredients(content)
        for ing in ings:
            all_recipe_ingredients.add(_normalize_ingredient(ing))

    matched = 0
    for ing in required_ingredients:
        norm_ing = _normalize_ingredient(ing)
        if norm_ing in all_recipe_ingredients:
            matched += 1

    return matched / len(required_ingredients)


def calculate_metrics(results: list[dict], ground_truth: dict) -> dict:
    """计算一条 query 的所有 metrics。"""
    actual_titles = [r.get("title", "") for r in results]
    relevant_titles = ground_truth.get("relevant_titles", [])
    required_ingredients = ground_truth.get("required_ingredients", [])

    return {
        "hit_at_1": calculate_hit_at_k(actual_titles, relevant_titles, 1),
        "hit_at_3": calculate_hit_at_k(actual_titles, relevant_titles, 3),
        "hit_at_5": calculate_hit_at_k(actual_titles, relevant_titles, 5),
        "mrr": round(calculate_mrr(actual_titles, relevant_titles), 4),
        "ingredient_coverage": round(
            calculate_ingredient_coverage_from_content(results, required_ingredients), 4
        ),
        "result_count": len(results),
    }


def percentile(values: list[float], p: float) -> float:
    """计算百分位数。"""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * p
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


# ============================================================
# Error Analysis
# ============================================================

def analyze_errors(query_item: dict, results: list[dict], strategy: str) -> dict | None:
    """分析失败 Query 的错误原因。"""
    relevant_titles = query_item.get("relevant_titles", [])
    required_ingredients = query_item.get("required_ingredients", [])
    actual_titles = [r.get("title", "") for r in results]

    has_ground_truth = query_item.get("ground_truth_available", False)
    if not has_ground_truth:
        return {
            "query_id": query_item["id"],
            "query": query_item["query"],
            "strategy": strategy,
            "expected": relevant_titles,
            "actual": actual_titles[:3],
            "missing_ingredients": [],
            "reason": "no_ground_truth",
        }

    hit = calculate_hit_at_k(actual_titles, relevant_titles, 3)
    coverage = calculate_ingredient_coverage_from_content(results, required_ingredients)

    if hit and coverage >= 0.5:
        return None  # 没有错误

    # 分析错误原因
    if not results:
        # 检查 RAG 和 Tavily 是否都有结果
        rag_results = [r for r in results if r.get("source") == "rag"]
        tavily_results = [r for r in results if r.get("source") == "tavily"]
        if not rag_results and not tavily_results:
            reason = "rag_miss"
        elif not tavily_results:
            reason = "tavily_miss"
        else:
            reason = "external_error"
    elif coverage < 0.5:
        reason = "ingredient_mismatch"
    else:
        reason = "ranking_error"

    missing = []
    from app.rag.retriever import _normalize_ingredient
    actual_normalized = {_normalize_ingredient(t) for t in actual_titles}
    for ing in required_ingredients:
        norm_ing = _normalize_ingredient(ing)
        found = any(norm_ing in a or a in norm_ing for a in actual_normalized)
        if not found:
            missing.append(ing)

    return {
        "query_id": query_item["id"],
        "query": query_item["query"],
        "strategy": strategy,
        "expected": relevant_titles,
        "actual": actual_titles[:3],
        "missing_ingredients": missing,
        "reason": reason,
    }


# ============================================================
# Benchmark Runner
# ============================================================

def run_strategy_benchmark(
    dataset: list[dict],
    strategy_fn,
    strategy_name: str,
    tavily_adapter=None,
    top_k: int = 5,
    **strategy_kwargs,
) -> dict:
    """运行单种策略的 benchmark。"""
    per_query = []
    all_latencies = []
    rag_hits = 0
    tavily_successes = 0
    fallback_count = 0
    errors = []

    for item in dataset:
        query = item["query"]
        user_ingredients = [{"name": ing} for ing in item.get("required_ingredients", [])]

        try:
            if strategy_name == "rag_only":
                results, latencies = strategy_fn(query, user_ingredients, top_k=top_k)
            elif strategy_name == "tavily_only":
                results, latencies = strategy_fn(query, user_ingredients, tavily_adapter, top_k=top_k)
            else:
                results, latencies = strategy_fn(query, user_ingredients, tavily_adapter, top_k=top_k, **strategy_kwargs)
        except Exception as e:
            results, latencies = [], {"total_latency_ms": 0, "error": str(e)[:100]}
            errors.append({
                "query_id": item["id"],
                "query": query,
                "strategy": strategy_name,
                "reason": "external_error",
                "error": str(e)[:100],
            })
            per_query.append({
                "query_id": item["id"],
                "metrics": {"hit_at_1": 0, "hit_at_3": 0, "hit_at_5": 0,
                            "mrr": 0.0, "ingredient_coverage": 0.0, "result_count": 0},
                "latency": latencies,
            })
            continue

        metrics = calculate_metrics(results, item)
        total_ms = latencies.get("total_latency_ms", 0)
        all_latencies.append(total_ms)

        if latencies.get("rag_latency_ms", 0) > 0:
            rag_hits += 1 if results else 0
        if tavily_adapter and latencies.get("tavily_latency_ms", 0) > 0:
            tavily_successes += 1

        # fallback: 如果主策略无结果
        if not results:
            fallback_count += 1

        error = analyze_errors(item, results, strategy_name)
        if error:
            errors.append(error)

        per_query.append({
            "query_id": item["id"],
            "query": query,
            "metrics": metrics,
            "latency": latencies,
            "actual_titles": [r.get("title", "") for r in results[:5]],
        })

    # 汇总
    total_queries = len(dataset)
    has_gt_queries = [q for q in dataset if q.get("ground_truth_available")]
    gt_count = len(has_gt_queries)

    sum_hit1 = sum(pq["metrics"]["hit_at_1"] for pq in per_query if any(pq["query_id"] == q["id"] for q in has_gt_queries))
    sum_hit3 = sum(pq["metrics"]["hit_at_3"] for pq in per_query if any(pq["query_id"] == q["id"] for q in has_gt_queries))
    sum_hit5 = sum(pq["metrics"]["hit_at_5"] for pq in per_query if any(pq["query_id"] == q["id"] for q in has_gt_queries))
    sum_mrr = sum(pq["metrics"]["mrr"] for pq in per_query if any(pq["query_id"] == q["id"] for q in has_gt_queries))
    sum_cov = sum(pq["metrics"]["ingredient_coverage"] for pq in per_query if any(pq["query_id"] == q["id"] for q in has_gt_queries))

    return {
        "strategy": strategy_name,
        "total_queries": total_queries,
        "ground_truth_queries": gt_count,
        "hit_at_1": round(sum_hit1 / gt_count, 4) if gt_count > 0 else 0,
        "hit_at_3": round(sum_hit3 / gt_count, 4) if gt_count > 0 else 0,
        "hit_at_5": round(sum_hit5 / gt_count, 4) if gt_count > 0 else 0,
        "mrr": round(sum_mrr / gt_count, 4) if gt_count > 0 else 0,
        "ingredient_coverage": round(sum_cov / gt_count, 4) if gt_count > 0 else 0,
        "avg_latency_ms": round(statistics.mean(all_latencies), 2) if all_latencies else 0,
        "p50_latency_ms": round(percentile(all_latencies, 0.5), 2) if all_latencies else 0,
        "p95_latency_ms": round(percentile(all_latencies, 0.95), 2) if all_latencies else 0,
        "rag_hit_rate": round(rag_hits / total_queries, 4),
        "tavily_success_rate": round(tavily_successes / total_queries, 4) if tavily_adapter else 0,
        "fallback_rate": round(fallback_count / total_queries, 4),
        "avg_result_count": round(
            statistics.mean([pq["metrics"]["result_count"] for pq in per_query]), 2
        ) if per_query else 0,
        "per_query": per_query,
        "errors": errors,
    }


# ============================================================
# Sweep 实验
# ============================================================

def run_threshold_sweep(dataset, tavily_adapter, thresholds=None) -> list[dict]:
    """Threshold sweep 实验。"""
    if thresholds is None:
        thresholds = [0.30, 0.40, 0.50, 0.60, 0.70]

    results = []
    for threshold in thresholds:
        os.environ["RAG_SCORE_THRESHOLD"] = str(threshold)
        # 重新加载 retriever 的 threshold（它读 env）
        from app.rag.retriever import get_score_threshold
        actual_threshold = get_score_threshold()

        bench = run_strategy_benchmark(
            dataset, strategy_hybrid_rrf, "hybrid_rrf",
            tavily_adapter=tavily_adapter, top_k=5,
        )
        results.append({
            "threshold": threshold,
            "actual_threshold": actual_threshold,
            "hit_at_3": bench["hit_at_3"],
            "ingredient_coverage": bench["ingredient_coverage"],
            "avg_latency_ms": bench["avg_latency_ms"],
            "rag_hit_rate": bench["rag_hit_rate"],
            "avg_result_count": bench["avg_result_count"],
        })
        logger.info(f"[Threshold Sweep] threshold={threshold} hit@3={bench['hit_at_3']:.4f} "
                    f"coverage={bench['ingredient_coverage']:.4f} latency={bench['avg_latency_ms']:.1f}ms")

    # 恢复默认
    os.environ.pop("RAG_SCORE_THRESHOLD", None)
    return results


def run_rrf_weight_sweep(dataset, tavily_adapter, weights=None) -> list[dict]:
    """RRF weight sweep 实验。"""
    if weights is None:
        weights = [(0.2, 0.8), (0.3, 0.7), (0.4, 0.6), (0.5, 0.5), (0.6, 0.4), (0.7, 0.3), (0.8, 0.2)]

    results = []
    for final_w, ing_w in weights:
        bench = run_strategy_benchmark(
            dataset, strategy_hybrid_rrf, "hybrid_rrf",
            tavily_adapter=tavily_adapter, top_k=5,
            rrf_final_weight=final_w,
            rrf_ingredient_weight=ing_w,
        )
        results.append({
            "final_weight": final_w,
            "ingredient_weight": ing_w,
            "hit_at_3": bench["hit_at_3"],
            "mrr": bench["mrr"],
            "ingredient_coverage": bench["ingredient_coverage"],
        })
        logger.info(f"[RRF Weight Sweep] final={final_w} ing={ing_w} "
                    f"hit@3={bench['hit_at_3']:.4f} mrr={bench['mrr']:.4f}")

    # 恢复默认
    os.environ.pop("RRF_FINAL_WEIGHT", None)
    os.environ.pop("RRF_INGREDIENT_WEIGHT", None)
    return results


def run_topk_sweep(dataset, tavily_adapter, topks=None) -> list[dict]:
    """Top-K sweep 实验。"""
    if topks is None:
        topks = [1, 3, 5]

    results = []
    for k in topks:
        bench = run_strategy_benchmark(
            dataset, strategy_hybrid_rrf, "hybrid_rrf",
            tavily_adapter=tavily_adapter, top_k=k,
        )
        results.append({
            "top_k": k,
            "hit_at_k": bench["hit_at_3"] if k >= 3 else bench["hit_at_1"],
            "ingredient_coverage": bench["ingredient_coverage"],
            "avg_latency_ms": bench["avg_latency_ms"],
            "avg_result_count": bench["avg_result_count"],
        })
        logger.info(f"[Top-K Sweep] k={k} hit={bench['hit_at_3'] if k >= 3 else bench['hit_at_1']:.4f} "
                    f"coverage={bench['ingredient_coverage']:.4f} latency={bench['avg_latency_ms']:.1f}ms")

    return results


# ============================================================
# 输出
# ============================================================

def ensure_output_dir():
    BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)


def save_json(data, filename):
    ensure_output_dir()
    path = BENCHMARK_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"[Output] Saved {path}")


def save_csv(strategy_results, filename):
    ensure_output_dir()
    path = BENCHMARK_DIR / filename
    lines = ["strategy,total_queries,hit_at_1,hit_at_3,hit_at_5,mrr,ingredient_coverage,avg_latency_ms,p50_latency_ms,p95_latency_ms,rag_hit_rate,tavily_success_rate,fallback_rate,avg_result_count"]
    for s in strategy_results:
        lines.append(
            f"{s['strategy']},{s['total_queries']},{s['hit_at_1']},{s['hit_at_3']},"
            f"{s['hit_at_5']},{s['mrr']},{s['ingredient_coverage']},"
            f"{s['avg_latency_ms']},{s['p50_latency_ms']},{s['p95_latency_ms']},"
            f"{s['rag_hit_rate']},{s['tavily_success_rate']},{s['fallback_rate']},"
            f"{s['avg_result_count']}"
        )
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    logger.info(f"[Output] Saved {path}")


def generate_markdown_report(dataset, strategy_results, threshold_results,
                             rrf_weight_results, topk_results, mode="offline"):
    """生成 Markdown 报告。"""
    # Category 统计
    categories = {}
    for q in dataset:
        cat = q.get("category", "unknown")
        categories[cat] = categories.get(cat, 0) + 1

    cat_lines = "\n".join(f"- {k}: {v}" for k, v in sorted(categories.items()))

    # Strategy comparison table
    strat_lines = []
    for s in strategy_results:
        strat_lines.append(
            f"| {s['strategy']} | {s['hit_at_1']:.4f} | {s['hit_at_3']:.4f} | "
            f"{s['hit_at_5']:.4f} | {s['mrr']:.4f} | {s['ingredient_coverage']:.4f} | "
            f"{s['avg_latency_ms']:.1f} | {s['p50_latency_ms']:.1f} | {s['p95_latency_ms']:.1f} |"
        )

    # Threshold table
    thresh_lines = []
    for t in threshold_results:
        thresh_lines.append(
            f"| {t['threshold']:.2f} | {t['hit_at_3']:.4f} | {t['ingredient_coverage']:.4f} | "
            f"{t['avg_latency_ms']:.1f} | {t['rag_hit_rate']:.4f} |"
        )

    # RRF weight table
    rrf_lines = []
    for r in rrf_weight_results:
        rrf_lines.append(
            f"| {r['final_weight']:.1f} | {r['ingredient_weight']:.1f} | "
            f"{r['hit_at_3']:.4f} | {r['mrr']:.4f} | {r['ingredient_coverage']:.4f} |"
        )

    # Top-K table
    topk_lines = []
    for t in topk_results:
        topk_lines.append(
            f"| {t['top_k']} | {t['hit_at_k']:.4f} | {t['ingredient_coverage']:.4f} | "
            f"{t['avg_latency_ms']:.1f} |"
        )

    # Error analysis
    all_errors = []
    for s in strategy_results:
        for e in s.get("errors", []):
            all_errors.append(e)

    error_reasons = {}
    for e in all_errors:
        reason = e.get("reason", "unknown")
        error_reasons[reason] = error_reasons.get(reason, 0) + 1

    error_lines = []
    for reason, count in sorted(error_reasons.items()):
        error_lines.append(f"- {reason}: {count}")

    report = f"""# Retrieval Benchmark Report

## Dataset

- Total Queries: {len(dataset)}
- Mode: {mode}
- Categories:
{cat_lines}

## Strategy Comparison

| Strategy | Hit@1 | Hit@3 | Hit@5 | MRR | Ingredient Coverage | Avg Latency (ms) | P50 (ms) | P95 (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(strat_lines)}

## Threshold Experiment

| Threshold | Hit@3 | Ingredient Coverage | Avg Latency (ms) | RAG Hit Rate |
|---:|---:|---:|---:|---:|
{chr(10).join(thresh_lines)}

## RRF Weight Experiment

| Final Weight | Ingredient Weight | Hit@3 | MRR | Ingredient Coverage |
|---:|---:|---:|---:|---:|
{chr(10).join(rrf_lines)}

## Top-K Experiment

| Top-K | Hit | Ingredient Coverage | Avg Latency (ms) |
|---:|---:|---:|---:|
{chr(10).join(topk_lines)}

## Error Analysis

Error count by reason:
{chr(10).join(error_lines) if error_lines else "- No errors"}

Total errors: {len(all_errors)}

## Notes

- Benchmark uses manually annotated Ground Truth based on `backend/data/recipes/`.
- Offline mode uses Tavily fixtures for CI; Online mode calls real Tavily API.
- Latency measured with `time.perf_counter()`.
- P50/P95 computed with standard library `statistics` module.
- Results are from a single run; for production decisions, run multiple times and average.
"""
    ensure_output_dir()
    path = BENCHMARK_DIR / "retrieval_benchmark_report.md"
    with open(path, "w", encoding="utf-8") as f:
        f.write(report)
    logger.info(f"[Output] Saved {path}")


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Retrieval Benchmark")
    parser.add_argument("--offline", action="store_true", default=True,
                        help="Use offline Tavily fixtures (default)")
    parser.add_argument("--online", action="store_true",
                        help="Use real Tavily API")
    parser.add_argument("--skip-tavily", action="store_true",
                        help="Skip Tavily entirely (only RAG strategies)")
    parser.add_argument("--skip-sweep", action="store_true",
                        help="Skip sweep experiments")
    args = parser.parse_args()

    mode = "online" if args.online else "offline"

    # 加载数据
    dataset = load_dataset()
    logger.info(f"Loaded {len(dataset)} queries from dataset")

    # 创建 Tavily adapter
    tavily_adapter = None
    if not args.skip_tavily:
        if args.online:
            try:
                tavily_adapter = OnlineTavilyAdapter()
                logger.info("Using Online Tavily")
            except Exception as e:
                logger.warning(f"Online Tavily init failed: {e}, falling back to offline")
                fixtures = load_tavily_fixtures()
                tavily_adapter = OfflineTavilyAdapter(fixtures)
                mode = "offline"
        else:
            fixtures = load_tavily_fixtures()
            tavily_adapter = OfflineTavilyAdapter(fixtures)
            logger.info(f"Using Offline Tavily fixtures ({len(fixtures)} queries)")
    else:
        logger.info("Skipping Tavily entirely")

    # 运行 4 种策略
    strategy_results = []

    # Strategy A: RAG Only
    logger.info("=" * 60)
    logger.info("Running Strategy A: RAG Only")
    rag_bench = run_strategy_benchmark(dataset, strategy_rag_only, "rag_only", top_k=5)
    strategy_results.append(rag_bench)

    # Strategy B: Tavily Only
    if tavily_adapter:
        logger.info("=" * 60)
        logger.info("Running Strategy B: Tavily Only")
        tav_bench = run_strategy_benchmark(
            dataset, strategy_tavily_only, "tavily_only",
            tavily_adapter=tavily_adapter, top_k=5,
        )
        strategy_results.append(tav_bench)

        # Strategy C: Hybrid Merge
        logger.info("=" * 60)
        logger.info("Running Strategy C: Hybrid Merge")
        merge_bench = run_strategy_benchmark(
            dataset, strategy_hybrid_merge, "hybrid_merge",
            tavily_adapter=tavily_adapter, top_k=5,
        )
        strategy_results.append(merge_bench)

        # Strategy D: Hybrid RRF + Rerank
        logger.info("=" * 60)
        logger.info("Running Strategy D: Hybrid RRF + Ingredient Rerank")
        rrf_bench = run_strategy_benchmark(
            dataset, strategy_hybrid_rrf, "hybrid_rrf",
            tavily_adapter=tavily_adapter, top_k=5,
        )
        strategy_results.append(rrf_bench)

    # Sweep 实验
    threshold_results = []
    rrf_weight_results = []
    topk_results = []

    if not args.skip_sweep and tavily_adapter:
        logger.info("=" * 60)
        logger.info("Running Threshold Sweep")
        threshold_results = run_threshold_sweep(dataset, tavily_adapter)

        logger.info("=" * 60)
        logger.info("Running RRF Weight Sweep")
        rrf_weight_results = run_rrf_weight_sweep(dataset, tavily_adapter)

        logger.info("=" * 60)
        logger.info("Running Top-K Sweep")
        topk_results = run_topk_sweep(dataset, tavily_adapter)

    # 输出
    full_results = {
        "mode": mode,
        "dataset_size": len(dataset),
        "strategy_results": [
            {k: v for k, v in s.items() if k != "per_query"} for s in strategy_results
        ],
        "threshold_sweep": threshold_results,
        "rrf_weight_sweep": rrf_weight_results,
        "topk_sweep": topk_results,
        "per_query_detail": {
            s["strategy"]: s.get("per_query", []) for s in strategy_results
        },
        "errors": {
            s["strategy"]: s.get("errors", []) for s in strategy_results
        },
    }

    save_json(full_results, "retrieval_benchmark_results.json")
    save_csv(strategy_results, "retrieval_benchmark_results.csv")
    generate_markdown_report(
        dataset, strategy_results,
        threshold_results, rrf_weight_results, topk_results,
        mode=mode,
    )

    # 打印摘要
    print("\n" + "=" * 60)
    print("Retrieval Benchmark Summary")
    print(f"Mode: {mode}, Queries: {len(dataset)}")
    print("=" * 60)
    for s in strategy_results:
        print(f"\n{s['strategy']}:")
        print(f"  Hit@1={s['hit_at_1']:.4f} Hit@3={s['hit_at_3']:.4f} Hit@5={s['hit_at_5']:.4f}")
        print(f"  MRR={s['mrr']:.4f} Coverage={s['ingredient_coverage']:.4f}")
        print(f"  Avg Latency={s['avg_latency_ms']:.1f}ms P50={s['p50_latency_ms']:.1f}ms P95={s['p95_latency_ms']:.1f}ms")
        print(f"  RAG Hit Rate={s['rag_hit_rate']:.4f} Tavily Success={s['tavily_success_rate']:.4f}")
        print(f"  Errors: {len(s.get('errors', []))}")

    if threshold_results:
        print("\nThreshold Sweep:")
        for t in threshold_results:
            print(f"  threshold={t['threshold']:.2f} Hit@3={t['hit_at_3']:.4f} "
                  f"Cov={t['ingredient_coverage']:.4f} Latency={t['avg_latency_ms']:.1f}ms")

    if rrf_weight_results:
        print("\nRRF Weight Sweep:")
        for r in rrf_weight_results:
            print(f"  final={r['final_weight']:.1f}/{r['ingredient_weight']:.1f} "
                  f"Hit@3={r['hit_at_3']:.4f} MRR={r['mrr']:.4f}")

    if topk_results:
        print("\nTop-K Sweep:")
        for t in topk_results:
            print(f"  k={t['top_k']} Hit={t['hit_at_k']:.4f} "
                  f"Cov={t['ingredient_coverage']:.4f} Latency={t['avg_latency_ms']:.1f}ms")

    print(f"\nResults saved to: {BENCHMARK_DIR}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    main()
