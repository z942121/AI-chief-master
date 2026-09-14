"""Run retrieval ablation benchmark inline (在容器 /app 下执行)。

用法：docker exec ai-chief-backend bash -c "cd /app && python tests/run_ablation_inline.py"
"""
import logging
import sys

logging.basicConfig(level=logging.WARNING)
sys.path.insert(0, '/app')

from tests.benchmark_ablation import (
    load_dataset, load_tavily_fixtures, OfflineTavilyAdapter,
    run_ablation, save_ablation_results,
)

dataset = load_dataset()
print(f"Dataset: {len(dataset)} queries", flush=True)

fixtures = load_tavily_fixtures()
adapter = OfflineTavilyAdapter(fixtures)
print(f"Tavily fixtures: {len(fixtures)} queries", flush=True)

results = run_ablation(dataset, adapter)
save_ablation_results(results)

print("\n===== SUMMARY =====", flush=True)
print("\nThreshold Sweep (Pipeline D):", flush=True)
for r in results["threshold_sweep"]:
    print(
        f"  {r['threshold']:.2f}: avg_cand={r['avg_candidate_count']} "
        f"med_cand={r['median_candidate_count']} hit@3={r['hit_at_3']:.4f} "
        f"mrr={r['mrr']:.4f} cov={r['ingredient_coverage']:.4f} "
        f"fp={r['false_positive_rate']:.4f}", flush=True)

print("\nAblation:", flush=True)
for th, abl in results["ablation"].items():
    if abl.get("status") != "RUN":
        print(f"  {th}: NOT RUN", flush=True)
        continue
    print(f"  threshold={th} (avg_cand={abl['avg_candidate_count']}):", flush=True)
    for p, st in abl["strategies"].items():
        print(f"    {p:20s} hit@3={st['hit_at_3']:.4f} mrr={st['mrr']:.4f} "
              f"cov={st['ingredient_coverage']:.4f}", flush=True)
    print(f"    ranking_changed={abl['ranking_changed_rate']:.2%} "
          f"rerank_changed={abl['rerank_changed_rate']:.2%}", flush=True)
    ht = abl["hit_transitions"]
    print(f"    rrf improved={len(ht['improved_by_rrf'])} degraded={len(ht['degraded_by_rrf'])} | "
          f"rerank improved={len(ht['improved_by_rerank'])} degraded={len(ht['degraded_by_rerank'])}",
          flush=True)

print("\nRerank change by candidate count (threshold=0.30):", flush=True)
for b in results["rerank_change_by_candidate_count_by_threshold"].get("0.3", []):
    print(f"  cand={b['bucket']}: queries={b['queries']} "
          f"rerank_changed_rate={b['rerank_changed_rate']:.2%} "
          f"rrf_changed_rate={b['ranking_changed_rate']:.2%}", flush=True)

rec = results["threshold_recommendation"]
print(f"\nRecommended threshold: {rec.get('recommended_threshold')} (rule: {rec.get('rule')})",
      flush=True)
print("\nDone. Results saved to /app/data/benchmark/", flush=True)
