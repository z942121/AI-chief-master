# Retrieval Benchmark Report

## Dataset

- Total Queries: 35
- Mode: offline
- Categories:
- ambiguous: 7
- exact_ingredient: 10
- multi_ingredient: 6
- preference: 4
- rag_miss: 4
- synonym: 4

## Strategy Comparison

| Strategy | Hit@1 | Hit@3 | Hit@5 | MRR | Ingredient Coverage | Avg Latency (ms) | P50 (ms) | P95 (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| rag_only | 0.5161 | 0.5484 | 0.5484 | 0.5323 | 0.4462 | 1534.9 | 1258.9 | 3014.2 |
| tavily_only | 0.2581 | 0.2581 | 0.2581 | 0.2581 | 0.0645 | 2.1 | 2.1 | 2.2 |
| hybrid_merge | 0.5806 | 0.6129 | 0.6129 | 0.5968 | 0.4462 | 1620.3 | 1338.4 | 2592.8 |
| hybrid_rrf | 0.5806 | 0.6129 | 0.6129 | 0.5968 | 0.4462 | 1422.0 | 1306.5 | 2257.3 |

## Threshold Experiment

| Threshold | Hit@3 | Ingredient Coverage | Avg Latency (ms) | RAG Hit Rate |
|---:|---:|---:|---:|---:|
| 0.30 | 0.9677 | 0.6774 | 1465.2 | 1.0000 |
| 0.40 | 0.9032 | 0.6452 | 1512.7 | 0.9714 |
| 0.50 | 0.6129 | 0.4462 | 1283.4 | 0.7714 |
| 0.60 | 0.3871 | 0.1667 | 1411.1 | 0.6571 |
| 0.70 | 0.2581 | 0.0645 | 1384.3 | 0.6286 |

## RRF Weight Experiment

| Final Weight | Ingredient Weight | Hit@3 | MRR | Ingredient Coverage |
|---:|---:|---:|---:|---:|
| 0.2 | 0.8 | 0.6129 | 0.5968 | 0.4462 |
| 0.3 | 0.7 | 0.6129 | 0.5968 | 0.4462 |
| 0.4 | 0.6 | 0.6129 | 0.5968 | 0.4462 |
| 0.5 | 0.5 | 0.6129 | 0.5968 | 0.4462 |
| 0.6 | 0.4 | 0.6129 | 0.5968 | 0.4462 |
| 0.7 | 0.3 | 0.6129 | 0.5968 | 0.4462 |
| 0.8 | 0.2 | 0.6129 | 0.5968 | 0.4462 |

## Top-K Experiment

| Top-K | Hit | Ingredient Coverage | Avg Latency (ms) |
|---:|---:|---:|---:|
| 1 | 0.5806 | 0.4462 | 1355.4 |
| 3 | 0.6129 | 0.4462 | 1300.9 |
| 5 | 0.6129 | 0.4462 | 1554.2 |

## Error Analysis

Error count by reason:
- ingredient_mismatch: 42
- no_ground_truth: 16
- rag_miss: 37

Total errors: 95

## Notes

- Benchmark uses manually annotated Ground Truth based on `backend/data/recipes/`.
- Offline mode uses Tavily fixtures for CI; Online mode calls real Tavily API.
- Latency measured with `time.perf_counter()`.
- P50/P95 computed with standard library `statistics` module.
- Results are from a single run; for production decisions, run multiple times and average.
