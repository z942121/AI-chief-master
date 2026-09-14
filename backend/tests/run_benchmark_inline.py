"""Run benchmark inline."""
import logging
import sys
import os

logging.basicConfig(level=logging.WARNING)
sys.path.insert(0, '/app')

from tests.benchmark_retrieval import (
    load_dataset, load_tavily_fixtures, OfflineTavilyAdapter,
    run_strategy_benchmark, strategy_rag_only, strategy_tavily_only,
    strategy_hybrid_merge, strategy_hybrid_rrf,
    run_threshold_sweep, run_rrf_weight_sweep, run_topk_sweep,
    save_json, save_csv, generate_markdown_report,
)

dataset = load_dataset()
print(f"Dataset: {len(dataset)} queries")

fixtures = load_tavily_fixtures()
tavily_adapter = OfflineTavilyAdapter(fixtures)
print(f"Tavily fixtures: {len(fixtures)} queries")

# Run all 4 strategies
rag_bench = run_strategy_benchmark(dataset, strategy_rag_only, "rag_only", top_k=5)
print(f"RAG Only: Hit@3={rag_bench['hit_at_3']:.4f} MRR={rag_bench['mrr']:.4f} Cov={rag_bench['ingredient_coverage']:.4f} Latency={rag_bench['avg_latency_ms']:.1f}ms")

tav_bench = run_strategy_benchmark(dataset, strategy_tavily_only, "tavily_only", tavily_adapter=tavily_adapter, top_k=5)
print(f"Tavily Only: Hit@3={tav_bench['hit_at_3']:.4f} MRR={tav_bench['mrr']:.4f} Cov={tav_bench['ingredient_coverage']:.4f} Latency={tav_bench['avg_latency_ms']:.1f}ms")

merge_bench = run_strategy_benchmark(dataset, strategy_hybrid_merge, "hybrid_merge", tavily_adapter=tavily_adapter, top_k=5)
print(f"Hybrid Merge: Hit@3={merge_bench['hit_at_3']:.4f} MRR={merge_bench['mrr']:.4f} Cov={merge_bench['ingredient_coverage']:.4f} Latency={merge_bench['avg_latency_ms']:.1f}ms")

rrf_bench = run_strategy_benchmark(dataset, strategy_hybrid_rrf, "hybrid_rrf", tavily_adapter=tavily_adapter, top_k=5)
print(f"Hybrid RRF: Hit@3={rrf_bench['hit_at_3']:.4f} MRR={rrf_bench['mrr']:.4f} Cov={rrf_bench['ingredient_coverage']:.4f} Latency={rrf_bench['avg_latency_ms']:.1f}ms")

# Run sweeps
threshold_results = run_threshold_sweep(dataset, tavily_adapter)
print("\nThreshold Sweep:")
for t in threshold_results:
    print(f"  {t['threshold']:.2f}: Hit@3={t['hit_at_3']:.4f} Cov={t['ingredient_coverage']:.4f} Lat={t['avg_latency_ms']:.1f}ms")

rrf_weight_results = run_rrf_weight_sweep(dataset, tavily_adapter)
print("\nRRF Weight Sweep:")
for r in rrf_weight_results:
    print(f"  {r['final_weight']:.1f}/{r['ingredient_weight']:.1f}: Hit@3={r['hit_at_3']:.4f} MRR={r['mrr']:.4f}")

topk_results = run_topk_sweep(dataset, tavily_adapter)
print("\nTop-K Sweep:")
for t in topk_results:
    print(f"  k={t['top_k']}: Hit={t['hit_at_k']:.4f} Cov={t['ingredient_coverage']:.4f} Lat={t['avg_latency_ms']:.1f}ms")

# Save results
strategy_results = [rag_bench, tav_bench, merge_bench, rrf_bench]
full_results = {
    "mode": "offline",
    "dataset_size": len(dataset),
    "strategy_results": [{k: v for k, v in s.items() if k != "per_query"} for s in strategy_results],
    "threshold_sweep": threshold_results,
    "rrf_weight_sweep": rrf_weight_results,
    "topk_sweep": topk_results,
}
save_json(full_results, "retrieval_benchmark_results.json")
save_csv(strategy_results, "retrieval_benchmark_results.csv")
generate_markdown_report(dataset, strategy_results, threshold_results, rrf_weight_results, topk_results, mode="offline")
print("\nResults saved to: /app/data/benchmark/")

# Print error summary
for s in strategy_results:
    errors = s.get("errors", [])
    if errors:
        print(f"\n{s['strategy']} errors ({len(errors)}):")
        for e in errors[:5]:
            print(f"  {e['query_id']}: {e['reason']}")
