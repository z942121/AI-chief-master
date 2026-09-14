"""Retrieval Ablation Benchmark。

验证假设：Candidate Pool 过小导致 RRF 与 Ingredient Rerank 无法发挥作用。

四个 Pipeline：
  A. rag_only           仅 Chroma RAG（受 threshold 过滤）
  B. hybrid_merge       Dedup 后简单合并（RAG 优先，保持原序，与 benchmark_retrieval 一致）
  C. hybrid_rrf         Dedup → Rank → RRF Fusion（无 rerank，按 rrf_score 排序）
  D. hybrid_rrf_rerank  Dedup → Rank → RRF → Ingredient Rerank（按 final_score 排序，生产 pipeline）

关键设计：每条 query 的 RAG + Tavily 原始结果只获取一次，
B/C/D 共享同一份原始结果，因此 ranking_changed / rerank_changed 是精确对比。

实验矩阵：
  1. Threshold Sweep: 0.20 / 0.25 / 0.30 / 0.35 / 0.40 / 0.45 / 0.50
  2. Candidate Pool 分析: per-query candidate_count / titles / hit + 分桶统计
  3. Ablation: threshold 0.50 / 0.40 / 0.30 下 A/B/C/D 全量对比
  4. ranking_changed: C 的 Top-K 与 B 的 Top-K 不完全相同
     rerank_changed: D 的 Top-K 与 C 的 Top-K 不完全相同
  5. candidate_count 分桶 vs rerank_changed rate
  6. False Positive: 返回的 Top-5 标题不在 relevant_titles 中的比例
  7. Threshold 推荐与 Error Analysis

用法（在 backend 目录 / 容器 /app 下）：
  python tests/run_ablation_inline.py

输出：
  backend/data/benchmark/retrieval_ablation_results.json
  backend/data/benchmark/retrieval_ablation_results.csv
  backend/data/benchmark/retrieval_ablation_report.md
"""
import json
import os
import statistics
import time
import logging
from pathlib import Path

from tests.benchmark_retrieval import (
    load_dataset,
    load_tavily_fixtures,
    OfflineTavilyAdapter,
    calculate_metrics,
    analyze_errors,
    _normalize_title,
)

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent
BENCHMARK_DIR = BACKEND_DIR / "data" / "benchmark"

PIPELINES = ["rag_only", "hybrid_merge", "hybrid_rrf", "hybrid_rrf_rerank"]
ABLATION_THRESHOLDS = [0.50, 0.40, 0.30]
SWEEP_THRESHOLDS = [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]


# ============================================================
# 排序对比工具
# ============================================================

def titles_differ(titles_a: list[str], titles_b: list[str]) -> bool:
    """两个有序标题列表是否不完全相同（顺序或成员不同即 True）。"""
    return [_normalize_title(t) for t in titles_a] != [_normalize_title(t) for t in titles_b]


def relevant_best_rank(ordered_titles: list[str], relevant_titles: list[str]):
    """第一个 relevant 标题在有序列表中的 1-based 位置，不存在返回 None。"""
    rel = {_normalize_title(t) for t in relevant_titles}
    for i, t in enumerate(ordered_titles):
        if _normalize_title(t) in rel:
            return i + 1
    return None


# ============================================================
# 单 Query 四 Pipeline 执行
# ============================================================

def run_pipelines_for_query(query: str, user_ingredients: list[dict],
                            tavily_adapter, top_k: int = 5) -> dict:
    """对单条 query 运行 A/B/C/D 四条 pipeline，共享同一份 RAG+Tavily 原始结果。"""
    from app.rag.retriever import search_recipes as rag_search
    from app.rag.retrieval_pipeline import (
        deduplicate, assign_ranks, rrf_fusion, ingredient_rerank,
    )

    latencies = {}

    # ---- 共享原始结果：RAG + Tavily 各取一次 ----
    t0 = time.perf_counter()
    rag_results = rag_search(query, top_k=top_k, user_ingredients=user_ingredients)
    latencies["rag_latency_ms"] = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    tavily_results = tavily_adapter.search(query)
    latencies["tavily_latency_ms"] = (time.perf_counter() - t0) * 1000

    # ---- Pipeline B: Hybrid Merge ----
    # 与 benchmark_retrieval.strategy_hybrid_merge 完全一致：
    # dedup 后 rag_rank/tavily_rank 均为 None → final_score 相同 → 稳定排序保持 dedup 顺序
    t0 = time.perf_counter()
    cands_b = deduplicate(rag_results, tavily_results)
    candidate_count = len(cands_b)
    candidate_titles = [c.title for c in cands_b]
    for c in cands_b:
        rank = c.rag_rank or c.tavily_rank or 99
        c.final_score = 1.0 / (rank + 1)
    cands_b.sort(key=lambda c: c.final_score, reverse=True)
    final_b = cands_b[:top_k]
    latencies["merge_latency_ms"] = (time.perf_counter() - t0) * 1000

    # ---- Pipeline C: Hybrid RRF (无 rerank) ----
    t0 = time.perf_counter()
    cands_c = deduplicate(rag_results, tavily_results)
    assign_ranks(cands_c)
    rrf_fusion(cands_c)
    cands_c.sort(key=lambda c: c.rrf_score, reverse=True)
    final_c = cands_c[:top_k]
    latencies["rrf_latency_ms"] = (time.perf_counter() - t0) * 1000

    # ---- Pipeline D: Hybrid RRF + Ingredient Rerank ----
    t0 = time.perf_counter()
    cands_d = deduplicate(rag_results, tavily_results)
    assign_ranks(cands_d)
    rrf_fusion(cands_d)
    ingredient_rerank(cands_d, user_ingredients)
    cands_d.sort(key=lambda c: c.final_score, reverse=True)
    final_d = cands_d[:top_k]
    latencies["rerank_latency_ms"] = (time.perf_counter() - t0) * 1000

    rag_titles = [r.get("title", "") for r in rag_results]
    merge_all = [c.title for c in cands_b]
    rrf_all = [c.title for c in cands_c]
    rerank_all = [c.title for c in cands_d]

    return {
        "rag_results": rag_results,
        "results": {
            "rag_only": rag_results,
            "hybrid_merge": [c.to_dict() for c in final_b],
            "hybrid_rrf": [c.to_dict() for c in final_c],
            "hybrid_rrf_rerank": [c.to_dict() for c in final_d],
        },
        "titles": {
            "rag_only": rag_titles,
            "hybrid_merge": [c.title for c in final_b],
            "hybrid_rrf": [c.title for c in final_c],
            "hybrid_rrf_rerank": [c.title for c in final_d],
        },
        "full_ranked_titles": {
            "hybrid_merge": merge_all,
            "hybrid_rrf": rrf_all,
            "hybrid_rrf_rerank": rerank_all,
        },
        "candidate_count": candidate_count,
        "candidate_titles": candidate_titles,
        "rag_result_count": len(rag_results),
        "tavily_result_count": len(tavily_results),
        "latencies": latencies,
    }


# ============================================================
# 聚合与统计
# ============================================================

def aggregate_pipeline(per_query: list[dict], pipeline: str) -> dict:
    """按 pipeline 聚合 Hit@K / MRR / Coverage（仅在 ground truth query 上计算）。"""
    rows = [pq for pq in per_query if pq.get("ground_truth_available") and "metrics" in pq]
    n = len(rows)
    if n == 0:
        return {k: 0 for k in ["hit_at_1", "hit_at_3", "hit_at_5", "mrr", "ingredient_coverage"]}

    def avg(field):
        return round(sum(r["metrics"][pipeline][field] for r in rows) / n, 4)

    return {
        "hit_at_1": avg("hit_at_1"),
        "hit_at_3": avg("hit_at_3"),
        "hit_at_5": avg("hit_at_5"),
        "mrr": avg("mrr"),
        "ingredient_coverage": avg("ingredient_coverage"),
    }


def compute_false_positive_rate(per_query: list[dict], pipeline: str = "hybrid_rrf_rerank") -> float:
    """False Positive Rate。

    定义：对有 ground truth 的 query，pipeline 返回的 Top-5 标题中
    不在 relevant_titles 里的数量 / 全部返回标题数量。
    """
    total_returned = 0
    total_fp = 0
    for pq in per_query:
        if not pq.get("ground_truth_available") or "titles" not in pq:
            continue
        rel = {_normalize_title(t) for t in pq.get("relevant_titles", [])}
        for t in pq["titles"][pipeline][:5]:
            total_returned += 1
            if _normalize_title(t) not in rel:
                total_fp += 1
    return round(total_fp / total_returned, 4) if total_returned else 0.0


def candidate_bucket_stats(per_query: list[dict]) -> dict:
    """按 candidate_count 分桶（0 / 1 / 2 / 3+），统计各桶 Hit@3（pipeline D）。"""
    def group_of(n):
        if n >= 3:
            return "3+"
        return str(n)

    groups: dict[str, dict] = {}
    for pq in per_query:
        if not pq.get("ground_truth_available") or "metrics" not in pq:
            continue
        g = group_of(pq["candidate_count"])
        groups.setdefault(g, {"queries": 0, "hits": 0})
        groups[g]["queries"] += 1
        groups[g]["hits"] += pq["metrics"]["hybrid_rrf_rerank"]["hit_at_3"]

    return {
        g: {
            "queries": v["queries"],
            "hit_at_3": round(v["hits"] / v["queries"], 4) if v["queries"] else 0.0,
        }
        for g, v in sorted(groups.items())
    }


def rerank_change_by_candidate_count(per_query: list[dict]) -> list[dict]:
    """按 candidate_count 分桶（0/1/2/3/4/5+），统计 rerank_changed / ranking_changed rate。

    ranking / rerank 变化与 ground truth 无关，因此统计所有 query。
    """
    def bucket_of(n):
        return "5+" if n >= 5 else str(n)

    buckets: dict[str, dict] = {}
    for pq in per_query:
        if "candidate_count" not in pq:
            continue
        b = bucket_of(pq["candidate_count"])
        buckets.setdefault(b, {
            "bucket": b, "queries": 0,
            "ranking_changed": 0, "rerank_changed": 0,
        })
        buckets[b]["queries"] += 1
        if pq.get("ranking_changed"):
            buckets[b]["ranking_changed"] += 1
        if pq.get("rerank_changed"):
            buckets[b]["rerank_changed"] += 1

    out = []
    for b in ["0", "1", "2", "3", "4", "5+"]:
        if b not in buckets:
            continue
        v = buckets[b]
        out.append({
            "bucket": b,
            "queries": v["queries"],
            "ranking_changed": v["ranking_changed"],
            "ranking_changed_rate": round(v["ranking_changed"] / v["queries"], 4) if v["queries"] else 0.0,
            "rerank_changed": v["rerank_changed"],
            "rerank_changed_rate": round(v["rerank_changed"] / v["queries"], 4) if v["queries"] else 0.0,
        })
    return out


def hit_transitions(per_query: list[dict]) -> dict:
    """统计 RRF / Rerank 带来的 Hit@3 提升与退化（ground truth query）。"""
    improved_by_rrf, degraded_by_rrf = [], []
    improved_by_rerank, degraded_by_rerank = [], []
    for pq in per_query:
        if not pq.get("ground_truth_available") or "metrics" not in pq:
            continue
        b = pq["metrics"]["hybrid_merge"]["hit_at_3"]
        c = pq["metrics"]["hybrid_rrf"]["hit_at_3"]
        d = pq["metrics"]["hybrid_rrf_rerank"]["hit_at_3"]
        if c > b:
            improved_by_rrf.append(pq["query_id"])
        elif c < b:
            degraded_by_rrf.append(pq["query_id"])
        if d > c:
            improved_by_rerank.append(pq["query_id"])
        elif d < c:
            degraded_by_rerank.append(pq["query_id"])
    return {
        "improved_by_rrf": improved_by_rrf,
        "degraded_by_rrf": degraded_by_rrf,
        "improved_by_rerank": improved_by_rerank,
        "degraded_by_rerank": degraded_by_rerank,
    }


def compare_new_candidates(per_query_base: list[dict], per_query_target: list[dict],
                           base_threshold: float, target_threshold: float) -> list[dict]:
    """对比两个 threshold 下的 candidate pool，找出 target 新增的候选及其是否 relevant。"""
    by_id = {pq["query_id"]: pq for pq in per_query_base}
    out = []
    for pq_t in per_query_target:
        pq_b = by_id.get(pq_t["query_id"])
        if pq_b is None or "candidate_titles" not in pq_t or "candidate_titles" not in pq_b:
            continue
        old = {_normalize_title(t) for t in pq_b["candidate_titles"]}
        rel = {_normalize_title(t) for t in pq_t.get("relevant_titles", [])}
        new_titles = [t for t in pq_t["candidate_titles"] if _normalize_title(t) not in old]
        if not new_titles:
            continue
        out.append({
            "query_id": pq_t["query_id"],
            "query": pq_t["query"],
            f"candidates_at_{base_threshold}": pq_b["candidate_count"],
            f"candidates_at_{target_threshold}": pq_t["candidate_count"],
            "new_titles": new_titles,
            "new_titles_relevant": [_normalize_title(t) in rel for t in new_titles],
            f"hit_at_{base_threshold}": pq_b["metrics"]["hybrid_rrf_rerank"]["hit_at_3"] if "metrics" in pq_b else None,
            f"hit_at_{target_threshold}": pq_t["metrics"]["hybrid_rrf_rerank"]["hit_at_3"] if "metrics" in pq_t else None,
        })
    return out


def recommend_threshold(sweep_rows: list[dict], tolerance: float = 0.02) -> dict:
    """Threshold 推荐：只输出建议，不修改任何生产配置。

    规则（可解释、确定性）：
      1. 找到 Hit@3 最高的 threshold；
      2. 在 Hit@3 落后最优值 tolerance 以内的候选中，选 threshold 最高的
         （candidate pool 更小、FP 更可控、延迟更低）；
      3. 并列时选 false_positive_rate 更低的。
    """
    if not sweep_rows:
        return {"recommended_threshold": None, "reason": "NOT RUN: no sweep rows"}

    best_hit = max(r["hit_at_3"] for r in sweep_rows)
    near = [r for r in sweep_rows if r["hit_at_3"] >= best_hit - tolerance]
    rec = max(near, key=lambda r: (r["threshold"], -r["false_positive_rate"]))
    return {
        "recommended_threshold": rec["threshold"],
        "rule": (
            f"highest threshold whose hit_at_3 >= max({best_hit}) - {tolerance}; "
            f"tie-break on lower false_positive_rate"
        ),
        "recommended_hit_at_3": rec["hit_at_3"],
        "recommended_mrr": rec["mrr"],
        "recommended_ingredient_coverage": rec["ingredient_coverage"],
        "recommended_false_positive_rate": rec["false_positive_rate"],
        "recommended_avg_candidate_count": rec["avg_candidate_count"],
        "best_hit_at_3": best_hit,
    }


# ============================================================
# 单 Threshold 全量执行
# ============================================================

def run_threshold_ablation(dataset: list[dict], tavily_adapter, threshold: float,
                           top_k: int = 5) -> dict:
    """在指定 threshold 下运行全部 query 的 A/B/C/D 四条 pipeline。"""
    os.environ["RAG_SCORE_THRESHOLD"] = str(threshold)
    try:
        per_query = []
        for item in dataset:
            query = item["query"]
            user_ingredients = [{"name": ing} for ing in item.get("required_ingredients", [])]
            try:
                out = run_pipelines_for_query(query, user_ingredients, tavily_adapter, top_k)
            except Exception as e:
                per_query.append({
                    "query_id": item["id"],
                    "query": query,
                    "category": item.get("category"),
                    "ground_truth_available": item.get("ground_truth_available", False),
                    "error": str(e)[:100],
                })
                continue

            metrics = {p: calculate_metrics(out["results"][p], item) for p in PIPELINES}
            ranking_changed = titles_differ(
                out["titles"]["hybrid_merge"], out["titles"]["hybrid_rrf"])
            rerank_changed = titles_differ(
                out["titles"]["hybrid_rrf"], out["titles"]["hybrid_rrf_rerank"])

            relevant = item.get("relevant_titles", [])
            # 与上一轮 benchmark 一致：用带真实 content 的 D 结果做 error analysis
            error = analyze_errors(item, out["results"]["hybrid_rrf_rerank"], "hybrid_rrf_rerank")
            per_query.append({
                "query_id": item["id"],
                "query": query,
                "category": item.get("category"),
                "ground_truth_available": item.get("ground_truth_available", False),
                "rag_result_count": out["rag_result_count"],
                "tavily_result_count": out["tavily_result_count"],
                "candidate_count": out["candidate_count"],
                "candidate_titles": out["candidate_titles"],
                "relevant_titles": relevant,
                "titles": out["titles"],
                "relevant_in_pool": relevant_best_rank(out["candidate_titles"], relevant) is not None,
                "relevant_best_rank": {
                    "hybrid_merge": relevant_best_rank(out["full_ranked_titles"]["hybrid_merge"], relevant),
                    "hybrid_rrf": relevant_best_rank(out["full_ranked_titles"]["hybrid_rrf"], relevant),
                    "hybrid_rrf_rerank": relevant_best_rank(out["full_ranked_titles"]["hybrid_rrf_rerank"], relevant),
                },
                "metrics": metrics,
                "ranking_changed": ranking_changed,
                "rerank_changed": rerank_changed,
                "error": error,
                "latencies": {k: round(v, 2) for k, v in out["latencies"].items()},
            })

        # ---- 汇总 ----
        strategies = {p: aggregate_pipeline(per_query, p) for p in PIPELINES}
        n_all = len([pq for pq in per_query if "candidate_count" in pq])
        gt_rows = [pq for pq in per_query if pq.get("ground_truth_available") and "candidate_count" in pq]
        n_gt = len(gt_rows)
        n_changed = sum(1 for pq in per_query if pq.get("ranking_changed"))
        n_rerank_changed = sum(1 for pq in per_query if pq.get("rerank_changed"))

        summary = {
            "threshold": threshold,
            "total_queries": len(dataset),
            "ground_truth_queries": n_gt,
            "strategies": strategies,
            "avg_candidate_count": round(
                statistics.mean([pq["candidate_count"] for pq in per_query if "candidate_count" in pq]), 2
            ) if n_all else 0,
            "median_candidate_count": round(
                statistics.median([pq["candidate_count"] for pq in per_query if "candidate_count" in pq]), 2
            ) if n_all else 0,
            "avg_rag_result_count": round(
                statistics.mean([pq["rag_result_count"] for pq in per_query if "rag_result_count" in pq]), 2
            ) if n_all else 0,
            "candidate_pool_zero_queries": sum(
                1 for pq in per_query if pq.get("candidate_count") == 0),
            "relevant_in_pool_rate": round(
                sum(1 for pq in gt_rows if pq.get("relevant_in_pool")) / n_gt, 4
            ) if n_gt else 0,
            "false_positive_rate": compute_false_positive_rate(per_query),
            "ranking_changed_count": n_changed,
            "ranking_changed_rate": round(n_changed / len(per_query), 4) if per_query else 0,
            "rerank_changed_count": n_rerank_changed,
            "rerank_changed_rate": round(n_rerank_changed / len(per_query), 4) if per_query else 0,
            "hit_transitions": hit_transitions(per_query),
            "candidate_buckets": candidate_bucket_stats(per_query),
            "rerank_change_by_candidate_count": rerank_change_by_candidate_count(per_query),
            "avg_rag_latency_ms": round(
                statistics.mean([pq["latencies"]["rag_latency_ms"] for pq in per_query if "latencies" in pq]), 2
            ) if n_all else 0,
            "avg_merge_latency_ms": round(
                statistics.mean([pq["latencies"]["merge_latency_ms"] for pq in per_query if "latencies" in pq]), 2
            ) if n_all else 0,
            "avg_rrf_latency_ms": round(
                statistics.mean([pq["latencies"]["rrf_latency_ms"] for pq in per_query if "latencies" in pq]), 2
            ) if n_all else 0,
            "avg_rerank_latency_ms": round(
                statistics.mean([pq["latencies"]["rerank_latency_ms"] for pq in per_query if "latencies" in pq]), 2
            ) if n_all else 0,
            "per_query": per_query,
        }

        # pipeline D 的 error analysis（沿用上一轮规则，per-query 已在循环内计算）
        summary["errors"] = [pq["error"] for pq in per_query if pq.get("error")]
        return summary
    finally:
        os.environ.pop("RAG_SCORE_THRESHOLD", None)


# ============================================================
# 全量 Ablation 主流程
# ============================================================

def run_ablation(dataset: list[dict], tavily_adapter,
                 thresholds: list[float] = None, top_k: int = 5) -> dict:
    """运行完整 ablation 实验：threshold sweep + candidate pool + ranking change 分析。"""
    if thresholds is None:
        thresholds = SWEEP_THRESHOLDS

    per_threshold = {}
    for th in thresholds:
        print(f"[Ablation] running threshold={th:.2f} ...", flush=True)
        per_threshold[th] = run_threshold_ablation(dataset, tavily_adapter, th, top_k)
        s = per_threshold[th]
        print(
            f"[Ablation] threshold={th:.2f} avg_cand={s['avg_candidate_count']} "
            f"hit@3(D)={s['strategies']['hybrid_rrf_rerank']['hit_at_3']:.4f} "
            f"mrr(D)={s['strategies']['hybrid_rrf_rerank']['mrr']:.4f} "
            f"FP={s['false_positive_rate']:.4f} "
            f"rrf_changed={s['ranking_changed_rate']:.2%} rerank_changed={s['rerank_changed_rate']:.2%}",
            flush=True,
        )

    # ---- Threshold Sweep 汇总 ----
    sweep_rows = []
    for th in thresholds:
        s = per_threshold[th]
        sweep_rows.append({
            "threshold": th,
            "avg_candidate_count": s["avg_candidate_count"],
            "median_candidate_count": s["median_candidate_count"],
            "avg_rag_result_count": s["avg_rag_result_count"],
            "candidate_pool_zero_queries": s["candidate_pool_zero_queries"],
            "relevant_in_pool_rate": s["relevant_in_pool_rate"],
            "hit_at_1": s["strategies"]["hybrid_rrf_rerank"]["hit_at_1"],
            "hit_at_3": s["strategies"]["hybrid_rrf_rerank"]["hit_at_3"],
            "hit_at_5": s["strategies"]["hybrid_rrf_rerank"]["hit_at_5"],
            "mrr": s["strategies"]["hybrid_rrf_rerank"]["mrr"],
            "ingredient_coverage": s["strategies"]["hybrid_rrf_rerank"]["ingredient_coverage"],
            "false_positive_rate": s["false_positive_rate"],
            "avg_rag_latency_ms": s["avg_rag_latency_ms"],
        })

    # ---- 重点 threshold ablation 提取（0.50 / 0.40 / 0.30）----
    ablation = {}
    for th in ABLATION_THRESHOLDS:
        if th not in per_threshold:
            ablation[str(th)] = {"status": "NOT RUN"}
            continue
        s = per_threshold[th]
        ablation[str(th)] = {
            "status": "RUN",
            "avg_candidate_count": s["avg_candidate_count"],
            "median_candidate_count": s["median_candidate_count"],
            "strategies": s["strategies"],
            "ranking_changed_count": s["ranking_changed_count"],
            "ranking_changed_rate": s["ranking_changed_rate"],
            "rerank_changed_count": s["rerank_changed_count"],
            "rerank_changed_rate": s["rerank_changed_rate"],
            "hit_transitions": s["hit_transitions"],
            "candidate_buckets": s["candidate_buckets"],
            "rerank_change_by_candidate_count": s["rerank_change_by_candidate_count"],
            "changed_queries": {
                "ranking_changed": [pq["query_id"] for pq in s["per_query"] if pq.get("ranking_changed")],
                "rerank_changed": [pq["query_id"] for pq in s["per_query"] if pq.get("rerank_changed")],
            },
        }

    # ---- Candidate Pool 分析（per-query 明细，全 threshold）----
    candidate_pool_analysis = []
    for th in thresholds:
        for pq in per_threshold[th]["per_query"]:
            candidate_pool_analysis.append({
                "threshold": th,
                "query_id": pq["query_id"],
                "query": pq["query"],
                "candidate_count": pq.get("candidate_count"),
                "candidate_titles": pq.get("candidate_titles", []),
                "relevant_titles": pq.get("relevant_titles", []),
                "relevant_in_pool": pq.get("relevant_in_pool"),
                "hit": pq.get("metrics", {}).get("hybrid_rrf_rerank", {}).get("hit_at_3") if pq.get("ground_truth_available") else None,
            })

    # ---- 0.50 → 0.30 新增候选分析 ----
    new_candidates = []
    if 0.50 in per_threshold and 0.30 in per_threshold:
        new_candidates = compare_new_candidates(
            per_threshold[0.50]["per_query"], per_threshold[0.30]["per_query"], 0.50, 0.30)

    # ---- False Positive 明细（D 的 Top-5 不在 relevant_titles 中）----
    fp_details = {}
    for th in thresholds:
        details = []
        for pq in per_threshold[th]["per_query"]:
            if not pq.get("ground_truth_available") or "titles" not in pq:
                continue
            rel = {_normalize_title(t) for t in pq.get("relevant_titles", [])}
            top5 = pq["titles"]["hybrid_rrf_rerank"][:5]
            fp = [t for t in top5 if _normalize_title(t) not in rel]
            if fp:
                details.append({
                    "query_id": pq["query_id"],
                    "query": pq["query"],
                    "returned_top5": top5,
                    "false_positives": fp,
                    "relevant_titles": pq.get("relevant_titles", []),
                })
        fp_details[str(th)] = details

    # ---- Threshold 推荐 ----
    recommendation = recommend_threshold(sweep_rows)

    # ---- Error Analysis 汇总 ----
    error_analysis = {}
    for th in thresholds:
        s = per_threshold[th]
        reasons = {}
        for e in s["errors"]:
            reasons[e["reason"]] = reasons.get(e["reason"], 0) + 1
        still_failing = [
            {"query_id": pq["query_id"], "query": pq["query"],
             "candidate_count": pq.get("candidate_count"),
             "relevant_in_pool": pq.get("relevant_in_pool"),
             "relevant_titles": pq.get("relevant_titles", []),
             "actual_titles": pq.get("titles", {}).get("hybrid_rrf_rerank", [])[:3]}
            for pq in s["per_query"]
            if pq.get("ground_truth_available") and "metrics" in pq
            and pq["metrics"]["hybrid_rrf_rerank"]["hit_at_3"] == 0
        ]
        error_analysis[str(th)] = {
            "error_reasons": reasons,
            "total_errors": len(s["errors"]),
            "still_failing_queries": still_failing,
        }

    return {
        "mode": "offline",
        "dataset_size": len(dataset),
        "pipeline_definitions": {
            "A_rag_only": "Chroma RAG only (threshold filtered)",
            "B_hybrid_merge": "dedup, keep insertion order (RAG first)",
            "C_hybrid_rrf": "dedup -> assign_ranks -> rrf_fusion, sort by rrf_score",
            "D_hybrid_rrf_rerank": "dedup -> rrf -> ingredient_rerank, sort by final_score",
            "ranking_changed": "C top-k differs from B top-k (ordered)",
            "rerank_changed": "D top-k differs from C top-k (ordered)",
            "false_positive_rate": "top-5 titles not in relevant_titles / all returned (GT queries)",
        },
        "threshold_sweep": sweep_rows,
        "ablation": ablation,
        "candidate_pool_analysis": candidate_pool_analysis,
        "candidate_buckets_by_threshold": {
            str(th): per_threshold[th]["candidate_buckets"] for th in thresholds
        },
        "rerank_change_by_candidate_count_by_threshold": {
            str(th): per_threshold[th]["rerank_change_by_candidate_count"] for th in thresholds
        },
        "new_candidates_050_to_030": new_candidates,
        "false_positive_details": fp_details,
        "threshold_recommendation": recommendation,
        "error_analysis": error_analysis,
        "latency_by_threshold": {
            str(th): {
                "avg_rag_latency_ms": per_threshold[th]["avg_rag_latency_ms"],
                "avg_merge_latency_ms": per_threshold[th]["avg_merge_latency_ms"],
                "avg_rrf_latency_ms": per_threshold[th]["avg_rrf_latency_ms"],
                "avg_rerank_latency_ms": per_threshold[th]["avg_rerank_latency_ms"],
            } for th in thresholds
        },
        "per_threshold_full": {
            str(th): {k: v for k, v in per_threshold[th].items() if k != "per_query"}
            for th in thresholds
        },
    }


# ============================================================
# 输出
# ============================================================

def ensure_output_dir():
    BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)


def save_ablation_results(results: dict):
    """保存 JSON / CSV / Markdown 三个结果文件。"""
    ensure_output_dir()

    # JSON（含 per-query 明细）
    json_path = BENCHMARK_DIR / "retrieval_ablation_results.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"[Output] Saved {json_path}", flush=True)

    # CSV：threshold × strategy 矩阵
    csv_path = BENCHMARK_DIR / "retrieval_ablation_results.csv"
    lines = ["threshold,strategy,hit_at_1,hit_at_3,hit_at_5,mrr,ingredient_coverage,"
             "avg_candidate_count,false_positive_rate,ranking_changed_rate,rerank_changed_rate"]
    sweep_by_th = {r["threshold"]: r for r in results["threshold_sweep"]}
    for th_str, abl in results["ablation"].items():
        if abl.get("status") != "RUN":
            continue
        th = float(th_str)
        srow = sweep_by_th.get(th, {})
        for p in PIPELINES:
            st = abl["strategies"][p]
            rrf_rate = abl["ranking_changed_rate"] if p == "hybrid_rrf" else ""
            rerank_rate = abl["rerank_changed_rate"] if p == "hybrid_rrf_rerank" else ""
            lines.append(
                f"{th},{p},{st['hit_at_1']},{st['hit_at_3']},{st['hit_at_5']},"
                f"{st['mrr']},{st['ingredient_coverage']},"
                f"{srow.get('avg_candidate_count', '')},{srow.get('false_positive_rate', '')},"
                f"{rrf_rate},{rerank_rate}"
            )
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[Output] Saved {csv_path}", flush=True)

    # Markdown 报告
    md_path = BENCHMARK_DIR / "retrieval_ablation_report.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(generate_ablation_markdown(results))
    print(f"[Output] Saved {md_path}", flush=True)


def _fmt(v, nd=4):
    if v is None or v == "":
        return "-"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def generate_ablation_markdown(results: dict) -> str:
    """生成人类可读的 ablation 报告。"""
    lines = []
    lines.append("# Retrieval Ablation Report")
    lines.append("")
    lines.append(f"- Dataset: {results['dataset_size']} queries")
    lines.append(f"- Mode: {results['mode']}")
    lines.append("- 假设：Candidate Pool 过小导致 RRF / Ingredient Rerank 无法发挥作用")
    lines.append("")

    # 1. Threshold Sweep
    lines.append("## 1. Threshold Sweep (Pipeline D = Hybrid RRF + Rerank)")
    lines.append("")
    lines.append("| Threshold | Avg Cand | Med Cand | Pool=0 | RelInPool | Hit@1 | Hit@3 | Hit@5 | MRR | Coverage | FP Rate |")
    lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in results["threshold_sweep"]:
        lines.append(
            f"| {r['threshold']:.2f} | {r['avg_candidate_count']} | {r['median_candidate_count']} | "
            f"{r['candidate_pool_zero_queries']} | {_fmt(r['relevant_in_pool_rate'])} | "
            f"{_fmt(r['hit_at_1'])} | {_fmt(r['hit_at_3'])} | {_fmt(r['hit_at_5'])} | "
            f"{_fmt(r['mrr'])} | {_fmt(r['ingredient_coverage'])} | {_fmt(r['false_positive_rate'])} |"
        )
    lines.append("")

    # 2. Candidate Pool 分析
    lines.append("## 2. Candidate Pool 分析（按 candidate_count 分桶，Hit@3 = Pipeline D）")
    lines.append("")
    for th_str, buckets in results["candidate_buckets_by_threshold"].items():
        lines.append(f"### threshold = {th_str}")
        lines.append("")
        lines.append("| Candidate Count | Queries | Hit@3 |")
        lines.append("|---|---:|---:|")
        for g in ["0", "1", "2", "3+"]:
            if g in buckets:
                lines.append(f"| {g} | {buckets[g]['queries']} | {_fmt(buckets[g]['hit_at_3'])} |")
        lines.append("")

    # 3. Ablation 矩阵
    lines.append("## 3. Ablation：4 Pipeline × 3 Threshold")
    lines.append("")
    for th_str, abl in results["ablation"].items():
        if abl.get("status") != "RUN":
            lines.append(f"### threshold = {th_str}: NOT RUN")
            lines.append("")
            continue
        lines.append(f"### threshold = {th_str}（avg candidate = {abl['avg_candidate_count']}，median = {abl['median_candidate_count']}）")
        lines.append("")
        lines.append("| Pipeline | Hit@1 | Hit@3 | Hit@5 | MRR | Coverage |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        for p in PIPELINES:
            st = abl["strategies"][p]
            lines.append(
                f"| {p} | {_fmt(st['hit_at_1'])} | {_fmt(st['hit_at_3'])} | "
                f"{_fmt(st['hit_at_5'])} | {_fmt(st['mrr'])} | {_fmt(st['ingredient_coverage'])} |"
            )
        lines.append("")
        ht = abl["hit_transitions"]
        lines.append(
            f"- ranking_changed (C vs B): {abl['ranking_changed_count']} / {results['dataset_size']} "
            f"= {abl['ranking_changed_rate']:.2%}"
        )
        lines.append(
            f"- rerank_changed (D vs C): {abl['rerank_changed_count']} / {results['dataset_size']} "
            f"= {abl['rerank_changed_rate']:.2%}"
        )
        lines.append(
            f"- RRF 使 Hit@3 提升 {len(ht['improved_by_rrf'])} 条 "
            f"({', '.join(ht['improved_by_rrf']) or '-'})，退化 {len(ht['degraded_by_rrf'])} 条 "
            f"({', '.join(ht['degraded_by_rrf']) or '-'})"
        )
        lines.append(
            f"- Rerank 使 Hit@3 提升 {len(ht['improved_by_rerank'])} 条 "
            f"({', '.join(ht['improved_by_rerank']) or '-'})，退化 {len(ht['degraded_by_rerank'])} 条 "
            f"({', '.join(ht['degraded_by_rerank']) or '-'})"
        )
        lines.append("")

    # 4. Candidate count vs rerank changed
    lines.append("## 4. Candidate Count 与 Rerank 变化率的关系")
    lines.append("")
    for th_str, rows in results["rerank_change_by_candidate_count_by_threshold"].items():
        lines.append(f"### threshold = {th_str}")
        lines.append("")
        lines.append("| Candidate Count | Queries | RRF Changed | RRF Rate | Rerank Changed | Rerank Rate |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        for b in rows:
            lines.append(
                f"| {b['bucket']} | {b['queries']} | {b['ranking_changed']} | "
                f"{b['ranking_changed_rate']:.2%} | {b['rerank_changed']} | {b['rerank_changed_rate']:.2%} |"
            )
        lines.append("")

    # 5. 0.50 → 0.30 新增候选
    lines.append("## 5. threshold 0.50 → 0.30 新增候选分析")
    lines.append("")
    new_cands = results.get("new_candidates_050_to_030", [])
    if not new_cands:
        lines.append("NOT RUN 或无新增候选。")
    else:
        lines.append("| Query | Cand@0.50 | Cand@0.30 | New Titles | New Relevant | Hit@0.50 | Hit@0.30 |")
        lines.append("|---|---:|---:|---|---|---:|---:|")
        for c in new_cands:
            lines.append(
                f"| {c['query_id']} {c['query']} | {c['candidates_at_0.5']} | {c['candidates_at_0.3']} | "
                f"{'; '.join(c['new_titles'])} | {c['new_titles_relevant']} | "
                f"{c['hit_at_0.5']} | {c['hit_at_0.3']} |"
            )
    lines.append("")

    # 6. False Positive 明细
    lines.append("## 6. False Positive 明细（Pipeline D Top-5）")
    lines.append("")
    lines.append("定义：返回标题不在该 query 的 relevant_titles 中（GT query）。")
    lines.append("")
    fp_details = results.get("false_positive_details", {})
    for th_str in ["0.5", "0.3"]:
        details = fp_details.get(th_str, [])
        lines.append(f"### threshold = {th_str}（{len(details)} 条 query 存在 FP）")
        lines.append("")
        if not details:
            lines.append("无 FP。")
        else:
            lines.append("| Query | False Positives | Relevant |")
            lines.append("|---|---|---|")
            for d in details:
                lines.append(
                    f"| {d['query_id']} 「{d['query']}」 | {'; '.join(d['false_positives'])} | "
                    f"{'; '.join(d['relevant_titles'][:3])} |"
                )
        lines.append("")

    # 7. Threshold 推荐
    rec = results["threshold_recommendation"]
    lines.append("## 7. Threshold 推荐（仅建议，未修改任何生产配置）")
    lines.append("")
    if rec.get("recommended_threshold") is None:
        lines.append(f"NOT RUN: {rec.get('reason', 'no data')}")
    else:
        lines.append(f"- **recommended threshold = {rec['recommended_threshold']}**")
        lines.append(f"- 规则：{rec['rule']}")
        lines.append(f"- 该点指标：Hit@3={rec['recommended_hit_at_3']}, MRR={rec['recommended_mrr']}, "
                     f"Coverage={rec['recommended_ingredient_coverage']}, "
                     f"FP={rec['recommended_false_positive_rate']}, "
                     f"AvgCand={rec['recommended_avg_candidate_count']}")
        lines.append(f"- Sweep 最优 Hit@3 = {rec['best_hit_at_3']}")
    lines.append("")

    # 8. Error Analysis
    lines.append("## 8. Error Analysis")
    lines.append("")
    for th_str, ea in results["error_analysis"].items():
        reasons = ", ".join(f"{k}={v}" for k, v in sorted(ea["error_reasons"].items()))
        lines.append(f"### threshold = {th_str}")
        lines.append("")
        lines.append(f"- 错误总数: {ea['total_errors']}（{reasons or '无'}）")
        fails = ea["still_failing_queries"]
        lines.append(f"- 仍然失败（Hit@3=0）的 GT query: {len(fails)} 条")
        for fq in fails:
            lines.append(
                f"  - {fq['query_id']} 「{fq['query']}」 cand={fq['candidate_count']} "
                f"relevant_in_pool={fq['relevant_in_pool']} "
                f"expected={fq['relevant_titles'][:3]} actual={fq['actual_titles'][:3]}"
            )
        lines.append("")

    # 9. 延迟
    lines.append("## 9. 延迟（各阶段平均，ms）")
    lines.append("")
    lines.append("| Threshold | RAG | Merge | RRF | Rerank(含RRF) |")
    lines.append("|---:|---:|---:|---:|---:|")
    for th_str, lat in results["latency_by_threshold"].items():
        lines.append(
            f"| {th_str} | {lat['avg_rag_latency_ms']:.1f} | {lat['avg_merge_latency_ms']:.1f} | "
            f"{lat['avg_rrf_latency_ms']:.1f} | {lat['avg_rerank_latency_ms']:.1f} |"
        )
    lines.append("")

    lines.append("## 10. 结论")
    lines.append("")
    lines.append("见 README「Retrieval Benchmark」章节与本报告数据；所有数字均来自真实运行。")
    lines.append("")
    return "\n".join(lines)
