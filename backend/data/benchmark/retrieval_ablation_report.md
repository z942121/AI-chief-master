# Retrieval Ablation Report

- Dataset: 35 queries
- Mode: offline
- 假设：Candidate Pool 过小导致 RRF / Ingredient Rerank 无法发挥作用

## 1. Threshold Sweep (Pipeline D = Hybrid RRF + Rerank)

| Threshold | Avg Cand | Med Cand | Pool=0 | RelInPool | Hit@1 | Hit@3 | Hit@5 | MRR | Coverage | FP Rate |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.20 | 5.66 | 6 | 0 | 1.0000 | 0.8065 | 0.9677 | 1.0000 | 0.8898 | 0.6774 | 0.5935 |
| 0.25 | 5.66 | 6 | 0 | 1.0000 | 0.8065 | 0.9677 | 1.0000 | 0.8898 | 0.6774 | 0.5935 |
| 0.30 | 5.66 | 6 | 0 | 1.0000 | 0.8065 | 0.9677 | 1.0000 | 0.8898 | 0.6774 | 0.5935 |
| 0.35 | 5.66 | 6 | 0 | 1.0000 | 0.8065 | 0.9677 | 1.0000 | 0.8898 | 0.6774 | 0.5935 |
| 0.40 | 4.2 | 5 | 1 | 0.9355 | 0.7742 | 0.9032 | 0.9355 | 0.8468 | 0.6452 | 0.5159 |
| 0.45 | 2.11 | 2 | 4 | 0.8387 | 0.8065 | 0.8387 | 0.8387 | 0.8226 | 0.5538 | 0.3043 |
| 0.50 | 1.31 | 1 | 8 | 0.6129 | 0.5806 | 0.6129 | 0.6129 | 0.5968 | 0.4462 | 0.3182 |

## 2. Candidate Pool 分析（按 candidate_count 分桶，Hit@3 = Pipeline D）

### threshold = 0.2

| Candidate Count | Queries | Hit@3 |
|---|---:|---:|
| 3+ | 31 | 0.9677 |

### threshold = 0.25

| Candidate Count | Queries | Hit@3 |
|---|---:|---:|
| 3+ | 31 | 0.9677 |

### threshold = 0.3

| Candidate Count | Queries | Hit@3 |
|---|---:|---:|
| 3+ | 31 | 0.9677 |

### threshold = 0.35

| Candidate Count | Queries | Hit@3 |
|---|---:|---:|
| 3+ | 31 | 0.9677 |

### threshold = 0.4

| Candidate Count | Queries | Hit@3 |
|---|---:|---:|
| 0 | 1 | 0.0000 |
| 2 | 2 | 1.0000 |
| 3+ | 28 | 0.9286 |

### threshold = 0.45

| Candidate Count | Queries | Hit@3 |
|---|---:|---:|
| 0 | 2 | 0.0000 |
| 1 | 7 | 0.5714 |
| 2 | 12 | 1.0000 |
| 3+ | 10 | 1.0000 |

### threshold = 0.5

| Candidate Count | Queries | Hit@3 |
|---|---:|---:|
| 0 | 6 | 0.0000 |
| 1 | 12 | 0.5000 |
| 2 | 9 | 1.0000 |
| 3+ | 4 | 1.0000 |

## 3. Ablation：4 Pipeline × 3 Threshold

### threshold = 0.5（avg candidate = 1.31，median = 1）

| Pipeline | Hit@1 | Hit@3 | Hit@5 | MRR | Coverage |
|---|---:|---:|---:|---:|---:|
| rag_only | 0.5161 | 0.5484 | 0.5484 | 0.5323 | 0.4462 |
| hybrid_merge | 0.5806 | 0.6129 | 0.6129 | 0.5968 | 0.4462 |
| hybrid_rrf | 0.5806 | 0.6129 | 0.6129 | 0.5968 | 0.4462 |
| hybrid_rrf_rerank | 0.5806 | 0.6129 | 0.6129 | 0.5968 | 0.4462 |

- ranking_changed (C vs B): 3 / 35 = 8.57%
- rerank_changed (D vs C): 2 / 35 = 5.71%
- RRF 使 Hit@3 提升 0 条 (-)，退化 0 条 (-)
- Rerank 使 Hit@3 提升 0 条 (-)，退化 0 条 (-)

### threshold = 0.4（avg candidate = 4.2，median = 5）

| Pipeline | Hit@1 | Hit@3 | Hit@5 | MRR | Coverage |
|---|---:|---:|---:|---:|---:|
| rag_only | 0.8065 | 0.8710 | 0.9355 | 0.8548 | 0.6452 |
| hybrid_merge | 0.8065 | 0.8710 | 0.9355 | 0.8548 | 0.6452 |
| hybrid_rrf | 0.8065 | 0.9032 | 0.9355 | 0.8629 | 0.6452 |
| hybrid_rrf_rerank | 0.7742 | 0.9032 | 0.9355 | 0.8468 | 0.6452 |

- ranking_changed (C vs B): 19 / 35 = 54.29%
- rerank_changed (D vs C): 8 / 35 = 22.86%
- RRF 使 Hit@3 提升 1 条 (q004)，退化 0 条 (-)
- Rerank 使 Hit@3 提升 0 条 (-)，退化 0 条 (-)

### threshold = 0.3（avg candidate = 5.66，median = 6）

| Pipeline | Hit@1 | Hit@3 | Hit@5 | MRR | Coverage |
|---|---:|---:|---:|---:|---:|
| rag_only | 0.8710 | 0.9355 | 1.0000 | 0.9194 | 0.6774 |
| hybrid_merge | 0.8710 | 0.9355 | 1.0000 | 0.9194 | 0.6774 |
| hybrid_rrf | 0.8387 | 0.9355 | 1.0000 | 0.9032 | 0.6774 |
| hybrid_rrf_rerank | 0.8065 | 0.9677 | 1.0000 | 0.8898 | 0.6774 |

- ranking_changed (C vs B): 23 / 35 = 65.71%
- rerank_changed (D vs C): 11 / 35 = 31.43%
- RRF 使 Hit@3 提升 1 条 (q004)，退化 1 条 (q003)
- Rerank 使 Hit@3 提升 1 条 (q003)，退化 0 条 (-)

## 4. Candidate Count 与 Rerank 变化率的关系

### threshold = 0.2

| Candidate Count | Queries | RRF Changed | RRF Rate | Rerank Changed | Rerank Rate |
|---|---:|---:|---:|---:|---:|
| 5+ | 35 | 23 | 65.71% | 11 | 31.43% |

### threshold = 0.25

| Candidate Count | Queries | RRF Changed | RRF Rate | Rerank Changed | Rerank Rate |
|---|---:|---:|---:|---:|---:|
| 5+ | 35 | 23 | 65.71% | 11 | 31.43% |

### threshold = 0.3

| Candidate Count | Queries | RRF Changed | RRF Rate | Rerank Changed | Rerank Rate |
|---|---:|---:|---:|---:|---:|
| 5+ | 35 | 23 | 65.71% | 11 | 31.43% |

### threshold = 0.35

| Candidate Count | Queries | RRF Changed | RRF Rate | Rerank Changed | Rerank Rate |
|---|---:|---:|---:|---:|---:|
| 5+ | 35 | 23 | 65.71% | 11 | 31.43% |

### threshold = 0.4

| Candidate Count | Queries | RRF Changed | RRF Rate | Rerank Changed | Rerank Rate |
|---|---:|---:|---:|---:|---:|
| 0 | 1 | 0 | 0.00% | 0 | 0.00% |
| 1 | 1 | 0 | 0.00% | 0 | 0.00% |
| 2 | 4 | 0 | 0.00% | 0 | 0.00% |
| 3 | 7 | 3 | 42.86% | 0 | 0.00% |
| 4 | 4 | 2 | 50.00% | 0 | 0.00% |
| 5+ | 18 | 14 | 77.78% | 8 | 44.44% |

### threshold = 0.45

| Candidate Count | Queries | RRF Changed | RRF Rate | Rerank Changed | Rerank Rate |
|---|---:|---:|---:|---:|---:|
| 0 | 4 | 0 | 0.00% | 0 | 0.00% |
| 1 | 8 | 0 | 0.00% | 0 | 0.00% |
| 2 | 12 | 0 | 0.00% | 0 | 0.00% |
| 3 | 5 | 2 | 40.00% | 0 | 0.00% |
| 4 | 3 | 3 | 100.00% | 2 | 66.67% |
| 5+ | 3 | 3 | 100.00% | 3 | 100.00% |

### threshold = 0.5

| Candidate Count | Queries | RRF Changed | RRF Rate | Rerank Changed | Rerank Rate |
|---|---:|---:|---:|---:|---:|
| 0 | 8 | 0 | 0.00% | 0 | 0.00% |
| 1 | 14 | 0 | 0.00% | 0 | 0.00% |
| 2 | 9 | 0 | 0.00% | 0 | 0.00% |
| 3 | 2 | 1 | 50.00% | 0 | 0.00% |
| 4 | 2 | 2 | 100.00% | 2 | 100.00% |

## 5. threshold 0.50 → 0.30 新增候选分析

| Query | Cand@0.50 | Cand@0.30 | New Titles | New Relevant | Hit@0.50 | Hit@0.30 |
|---|---:|---:|---|---|---:|---:|
| q001 西红柿 鸡蛋 | 4 | 7 | 番茄炒蛋; 蛋炒饭; 宫保鸡丁 | [True, False, False] | 1 | 1 |
| q002 牛肉 土豆 | 2 | 6 | 葱爆牛肉; 青椒肉丝; 宫保鸡丁; 麻婆豆腐 | [False, False, False, False] | 1 | 1 |
| q003 鸡肉 胡萝卜 | 1 | 6 | 土豆炖牛肉; 鸡胸肉沙拉; 宫保鸡丁; 红烧肉; 地三鲜 | [True, False, False, False, False] | 0 | 1 |
| q004 鸡蛋 豆腐 | 1 | 6 | 西红柿鸡蛋面; 蛋炒饭; 番茄炒蛋; 麻婆豆腐; 地三鲜 | [False, False, False, True, False] | 0 | 1 |
| q005 西兰花 | 2 | 6 | 地三鲜; 葱爆牛肉; 西红柿鸡蛋汤; 鸡胸肉沙拉 | [False, False, False, False] | 1 | 1 |
| q006 鸡翅 可乐 | 2 | 6 | 鸡胸肉沙拉; 宫保鸡丁; 番茄炒蛋; 地三鲜 | [False, False, False, False] | 1 | 1 |
| q007 我有西红柿、鸡蛋、土豆 | 3 | 6 | 番茄炒蛋; 土豆炖牛肉; 蛋炒饭 | [True, True, False] | 1 | 1 |
| q008 牛肉、土豆、洋葱怎么做 | 3 | 6 | 麻婆豆腐; 蒜蓉西兰花; 红烧肉 | [False, False, False] | 1 | 1 |
| q009 鸡肉、香菇、青椒 | 1 | 6 | 青椒肉丝; 地三鲜; 鱼香肉丝; 鸡胸肉沙拉 | [True, False, False, False] | 1 | 1 |
| q010 猪肉 青椒 | 2 | 6 | 鱼香肉丝; 地三鲜; 宫保鸡丁; 葱爆牛肉 | [True, False, False, False] | 1 | 1 |
| q011 番茄 鸡蛋 | 2 | 6 | 西红柿鸡蛋面; 西红柿鸡蛋汤; 蛋炒饭; 鸡胸肉沙拉 | [True, True, False, False] | 1 | 1 |
| q012 马铃薯 牛肉 | 1 | 6 | 土豆炖牛肉; 葱爆牛肉; 麻婆豆腐; 青椒肉丝; 宫保鸡丁 | [True, False, False, False, False] | 0 | 1 |
| q013 洋芋 牛肉 | 1 | 6 | 土豆炖牛肉; 葱爆牛肉; 宫保鸡丁; 鱼香肉丝; 麻婆豆腐 | [True, False, False, False, False] | 0 | 1 |
| q014 番茄 炒蛋 | 2 | 6 | 西红柿鸡蛋面; 西红柿鸡蛋汤; 蛋炒饭; 葱爆牛肉 | [False, False, False, False] | 1 | 1 |
| q015 西红柿鸡蛋，不吃辣 | 2 | 5 | 番茄炒蛋; 蛋炒饭; 鸡胸肉沙拉 | [True, False, False] | 1 | 1 |
| q016 牛肉土豆，少油 | 1 | 5 | 葱爆牛肉; 青椒肉丝; 鱼香肉丝; 宫保鸡丁 | [False, False, False, False] | 1 | 1 |
| q017 鸡肉，不要辣 | 0 | 5 | 鸡胸肉沙拉; 宫保鸡丁; 可乐鸡翅; 青椒肉丝; 红烧肉 | [True, True, False, False, False] | 0 | 1 |
| q018 家常牛肉怎么做 | 2 | 6 | 葱爆牛肉; 红烧肉; 宫保鸡丁; 青椒肉丝 | [True, True, False, False] | 1 | 1 |
| q019 鸡蛋简单做法 | 4 | 6 | 西红柿鸡蛋汤; 可乐鸡翅 | [True, False] | 1 | 1 |
| q020 适合下饭的番茄菜 | 0 | 5 | 番茄炒蛋; 西红柿鸡蛋面; 西红柿鸡蛋汤; 蛋炒饭; 地三鲜 | [True, False, True, False, False] | 0 | 1 |
| q021 下饭菜谱 | 0 | 5 | 蛋炒饭; 土豆炖牛肉; 地三鲜; 麻婆豆腐; 番茄炒蛋 | [False, False, False, True, False] | 0 | 0 |
| q022 简单的家常菜 | 0 | 5 | 地三鲜; 番茄炒蛋; 蒜蓉西兰花; 红烧肉; 蛋炒饭 | [False, True, False, False, True] | 0 | 1 |
| q023 鳕鱼怎么做 | 1 | 6 | 鱼香肉丝; 麻婆豆腐; 葱爆牛肉; 土豆炖牛肉; 可乐鸡翅 | [False, False, False, False, False] | 0 | 0 |
| q024 法式牛排怎么做 | 1 | 6 | 土豆炖牛肉; 鸡胸肉沙拉; 葱爆牛肉; 红烧肉; 麻婆豆腐 | [False, False, False, False, False] | 0 | 0 |
| q025 三文鱼刺身 | 0 | 5 | 地三鲜; 鱼香肉丝; 青椒肉丝; 葱爆牛肉; 红烧肉 | [False, False, False, False, False] | 0 | 0 |
| q026 羊肉泡馍 | 0 | 5 | 土豆炖牛肉; 葱爆牛肉; 红烧肉; 鱼香肉丝; 地三鲜 | [False, False, False, False, False] | 0 | 0 |
| q027 西红柿 | 1 | 5 | 西红柿鸡蛋面; 番茄炒蛋; 红烧肉; 青椒肉丝 | [True, True, False, False] | 1 | 1 |
| q028 鸡蛋 | 0 | 5 | 蛋炒饭; 番茄炒蛋; 西红柿鸡蛋面; 西红柿鸡蛋汤; 可乐鸡翅 | [True, True, True, True, False] | 0 | 1 |
| q029 五花肉 | 1 | 6 | 红烧肉; 鱼香肉丝; 青椒肉丝; 土豆炖牛肉; 葱爆牛肉 | [True, False, False, False, False] | 0 | 1 |
| q030 豆腐怎么做好吃 | 2 | 6 | 地三鲜; 土豆炖牛肉; 西红柿鸡蛋面; 蛋炒饭 | [False, False, False, False] | 1 | 1 |
| q031 鸡胸肉 减脂 | 1 | 5 | 宫保鸡丁; 可乐鸡翅; 鱼香肉丝; 土豆炖牛肉 | [False, False, False, False] | 1 | 1 |
| q032 茄子 土豆 青椒 | 1 | 6 | 青椒肉丝; 土豆炖牛肉; 番茄炒蛋; 西红柿鸡蛋面 | [False, False, False, False] | 1 | 1 |
| q033 肉丝 青椒 | 1 | 5 | 鱼香肉丝; 葱爆牛肉; 红烧肉; 土豆炖牛肉 | [False, False, False, False] | 1 | 1 |
| q034 木耳 胡萝卜 猪肉 | 0 | 5 | 鱼香肉丝; 土豆炖牛肉; 青椒肉丝; 地三鲜; 红烧肉 | [True, False, False, False, False] | 0 | 1 |
| q035 剩饭怎么做 | 1 | 6 | 蛋炒饭; 西红柿鸡蛋面; 番茄炒蛋; 红烧肉; 地三鲜 | [True, False, False, False, False] | 0 | 1 |

## 6. False Positive 明细（Pipeline D Top-5）

定义：返回标题不在该 query 的 relevant_titles 中（GT query）。

### threshold = 0.5（13 条 query 存在 FP）

| Query | False Positives | Relevant |
|---|---|---|
| q001 「西红柿 鸡蛋」 | 西红柿炒鸡蛋的家常做法; 西红柿鸡蛋汤做法 | 番茄炒蛋; 西红柿鸡蛋汤; 西红柿鸡蛋面 |
| q002 「牛肉 土豆」 | 土豆炖牛肉的做法 | 土豆炖牛肉 |
| q003 「鸡肉 胡萝卜」 | 胡萝卜炒鸡肉 | 土豆炖牛肉 |
| q004 「鸡蛋 豆腐」 | 鸡蛋豆腐羹 | 麻婆豆腐 |
| q005 「西兰花」 | 蒜蓉西兰花做法 | 蒜蓉西兰花 |
| q006 「鸡翅 可乐」 | 可乐鸡翅经典做法 | 可乐鸡翅 |
| q012 「马铃薯 牛肉」 | 马铃薯炖牛肉 | 土豆炖牛肉 |
| q013 「洋芋 牛肉」 | 洋芋炖牛肉 | 土豆炖牛肉 |
| q014 「番茄 炒蛋」 | 番茄炒蛋家常做法 | 番茄炒蛋 |
| q018 「家常牛肉怎么做」 | 红烧牛肉的家常做法 | 土豆炖牛肉; 葱爆牛肉; 红烧肉 |
| q019 「鸡蛋简单做法」 | 西红柿鸡蛋面 | 番茄炒蛋; 西红柿鸡蛋汤; 蛋炒饭 |
| q029 「五花肉」 | 红烧肉经典做法 | 红烧肉 |
| q035 「剩饭怎么做」 | 蛋炒饭做法 | 蛋炒饭 |

### threshold = 0.3（30 条 query 存在 FP）

| Query | False Positives | Relevant |
|---|---|---|
| q001 「西红柿 鸡蛋」 | 西红柿炒鸡蛋的家常做法; 蛋炒饭 | 番茄炒蛋; 西红柿鸡蛋汤; 西红柿鸡蛋面 |
| q002 「牛肉 土豆」 | 土豆炖牛肉的做法; 葱爆牛肉; 青椒肉丝; 宫保鸡丁 | 土豆炖牛肉 |
| q003 「鸡肉 胡萝卜」 | 鸡胸肉沙拉; 胡萝卜炒鸡肉; 宫保鸡丁; 红烧肉 | 土豆炖牛肉 |
| q004 「鸡蛋 豆腐」 | 西红柿鸡蛋面; 鸡蛋豆腐羹; 蛋炒饭; 番茄炒蛋 | 麻婆豆腐 |
| q005 「西兰花」 | 蒜蓉西兰花做法; 地三鲜; 葱爆牛肉; 西红柿鸡蛋汤 | 蒜蓉西兰花 |
| q006 「鸡翅 可乐」 | 可乐鸡翅经典做法; 鸡胸肉沙拉; 宫保鸡丁; 番茄炒蛋 | 可乐鸡翅 |
| q008 「牛肉、土豆、洋葱怎么做」 | 麻婆豆腐; 蒜蓉西兰花 | 土豆炖牛肉; 葱爆牛肉 |
| q009 「鸡肉、香菇、青椒」 | 地三鲜; 鱼香肉丝 | 宫保鸡丁; 青椒肉丝 |
| q010 「猪肉 青椒」 | 地三鲜; 宫保鸡丁 | 青椒肉丝; 鱼香肉丝 |
| q011 「番茄 鸡蛋」 | 蛋炒饭 | 番茄炒蛋; 西红柿鸡蛋汤; 西红柿鸡蛋面 |
| q012 「马铃薯 牛肉」 | 马铃薯炖牛肉; 葱爆牛肉; 麻婆豆腐; 青椒肉丝 | 土豆炖牛肉 |
| q013 「洋芋 牛肉」 | 洋芋炖牛肉; 葱爆牛肉; 宫保鸡丁; 鱼香肉丝 | 土豆炖牛肉 |
| q014 「番茄 炒蛋」 | 西红柿鸡蛋面; 西红柿鸡蛋汤; 蛋炒饭; 番茄炒蛋家常做法 | 番茄炒蛋 |
| q015 「西红柿鸡蛋，不吃辣」 | 蛋炒饭; 鸡胸肉沙拉 | 番茄炒蛋; 西红柿鸡蛋汤; 西红柿鸡蛋面 |
| q016 「牛肉土豆，少油」 | 葱爆牛肉; 青椒肉丝; 鱼香肉丝; 宫保鸡丁 | 土豆炖牛肉 |
| q017 「鸡肉，不要辣」 | 可乐鸡翅; 青椒肉丝; 红烧肉 | 宫保鸡丁; 鸡胸肉沙拉 |
| q018 「家常牛肉怎么做」 | 红烧牛肉的家常做法; 宫保鸡丁 | 土豆炖牛肉; 葱爆牛肉; 红烧肉 |
| q019 「鸡蛋简单做法」 | 西红柿鸡蛋面 | 番茄炒蛋; 西红柿鸡蛋汤; 蛋炒饭 |
| q020 「适合下饭的番茄菜」 | 西红柿鸡蛋面; 蛋炒饭; 地三鲜 | 番茄炒蛋; 西红柿鸡蛋汤 |
| q021 「下饭菜谱」 | 蛋炒饭; 土豆炖牛肉; 地三鲜; 番茄炒蛋 | 鱼香肉丝; 宫保鸡丁; 麻婆豆腐 |
| q022 「简单的家常菜」 | 地三鲜; 蒜蓉西兰花; 红烧肉 | 番茄炒蛋; 蛋炒饭; 西红柿鸡蛋汤 |
| q027 「西红柿」 | 红烧肉; 青椒肉丝 | 番茄炒蛋; 西红柿鸡蛋汤; 西红柿鸡蛋面 |
| q028 「鸡蛋」 | 可乐鸡翅 | 番茄炒蛋; 西红柿鸡蛋汤; 蛋炒饭 |
| q029 「五花肉」 | 红烧肉经典做法; 鱼香肉丝; 青椒肉丝; 土豆炖牛肉 | 红烧肉 |
| q030 「豆腐怎么做好吃」 | 地三鲜; 土豆炖牛肉; 西红柿鸡蛋面 | 麻婆豆腐 |
| q031 「鸡胸肉 减脂」 | 宫保鸡丁; 可乐鸡翅; 鱼香肉丝; 土豆炖牛肉 | 鸡胸肉沙拉 |
| q032 「茄子 土豆 青椒」 | 青椒肉丝; 土豆炖牛肉; 番茄炒蛋 | 地三鲜 |
| q033 「肉丝 青椒」 | 鱼香肉丝; 葱爆牛肉; 红烧肉; 土豆炖牛肉 | 青椒肉丝 |
| q034 「木耳 胡萝卜 猪肉」 | 土豆炖牛肉; 青椒肉丝; 地三鲜; 红烧肉 | 鱼香肉丝 |
| q035 「剩饭怎么做」 | 蛋炒饭做法; 西红柿鸡蛋面; 番茄炒蛋; 红烧肉 | 蛋炒饭 |

## 7. Threshold 推荐（仅建议，未修改任何生产配置）

- **recommended threshold = 0.35**
- 规则：highest threshold whose hit_at_3 >= max(0.9677) - 0.02; tie-break on lower false_positive_rate
- 该点指标：Hit@3=0.9677, MRR=0.8898, Coverage=0.6774, FP=0.5935, AvgCand=5.66
- Sweep 最优 Hit@3 = 0.9677

## 8. Error Analysis

### threshold = 0.2

- 错误总数: 10（ingredient_mismatch=5, no_ground_truth=4, ranking_error=1）
- 仍然失败（Hit@3=0）的 GT query: 1 条
  - q021 「下饭菜谱」 cand=5 relevant_in_pool=True expected=['鱼香肉丝', '宫保鸡丁', '麻婆豆腐'] actual=['蛋炒饭', '土豆炖牛肉', '地三鲜']

### threshold = 0.25

- 错误总数: 10（ingredient_mismatch=5, no_ground_truth=4, ranking_error=1）
- 仍然失败（Hit@3=0）的 GT query: 1 条
  - q021 「下饭菜谱」 cand=5 relevant_in_pool=True expected=['鱼香肉丝', '宫保鸡丁', '麻婆豆腐'] actual=['蛋炒饭', '土豆炖牛肉', '地三鲜']

### threshold = 0.3

- 错误总数: 10（ingredient_mismatch=5, no_ground_truth=4, ranking_error=1）
- 仍然失败（Hit@3=0）的 GT query: 1 条
  - q021 「下饭菜谱」 cand=5 relevant_in_pool=True expected=['鱼香肉丝', '宫保鸡丁', '麻婆豆腐'] actual=['蛋炒饭', '土豆炖牛肉', '地三鲜']

### threshold = 0.35

- 错误总数: 10（ingredient_mismatch=5, no_ground_truth=4, ranking_error=1）
- 仍然失败（Hit@3=0）的 GT query: 1 条
  - q021 「下饭菜谱」 cand=5 relevant_in_pool=True expected=['鱼香肉丝', '宫保鸡丁', '麻婆豆腐'] actual=['蛋炒饭', '土豆炖牛肉', '地三鲜']

### threshold = 0.4

- 错误总数: 12（ingredient_mismatch=6, no_ground_truth=4, rag_miss=1, ranking_error=1）
- 仍然失败（Hit@3=0）的 GT query: 3 条
  - q003 「鸡肉 胡萝卜」 cand=3 relevant_in_pool=False expected=['土豆炖牛肉'] actual=['鸡胸肉沙拉', '胡萝卜炒鸡肉', '宫保鸡丁']
  - q021 「下饭菜谱」 cand=5 relevant_in_pool=True expected=['鱼香肉丝', '宫保鸡丁', '麻婆豆腐'] actual=['蛋炒饭', '土豆炖牛肉', '地三鲜']
  - q034 「木耳 胡萝卜 猪肉」 cand=0 relevant_in_pool=False expected=['鱼香肉丝'] actual=[]

### threshold = 0.45

- 错误总数: 16（ingredient_mismatch=9, no_ground_truth=4, rag_miss=2, ranking_error=1）
- 仍然失败（Hit@3=0）的 GT query: 5 条
  - q003 「鸡肉 胡萝卜」 cand=1 relevant_in_pool=False expected=['土豆炖牛肉'] actual=['胡萝卜炒鸡肉']
  - q021 「下饭菜谱」 cand=1 relevant_in_pool=False expected=['鱼香肉丝', '宫保鸡丁', '麻婆豆腐'] actual=['蛋炒饭']
  - q022 「简单的家常菜」 cand=0 relevant_in_pool=False expected=['番茄炒蛋', '蛋炒饭', '西红柿鸡蛋汤'] actual=[]
  - q029 「五花肉」 cand=1 relevant_in_pool=False expected=['红烧肉'] actual=['红烧肉经典做法']
  - q034 「木耳 胡萝卜 猪肉」 cand=0 relevant_in_pool=False expected=['鱼香肉丝'] actual=[]

### threshold = 0.5

- 错误总数: 20（ingredient_mismatch=10, no_ground_truth=4, rag_miss=6）
- 仍然失败（Hit@3=0）的 GT query: 12 条
  - q003 「鸡肉 胡萝卜」 cand=1 relevant_in_pool=False expected=['土豆炖牛肉'] actual=['胡萝卜炒鸡肉']
  - q004 「鸡蛋 豆腐」 cand=1 relevant_in_pool=False expected=['麻婆豆腐'] actual=['鸡蛋豆腐羹']
  - q012 「马铃薯 牛肉」 cand=1 relevant_in_pool=False expected=['土豆炖牛肉'] actual=['马铃薯炖牛肉']
  - q013 「洋芋 牛肉」 cand=1 relevant_in_pool=False expected=['土豆炖牛肉'] actual=['洋芋炖牛肉']
  - q017 「鸡肉，不要辣」 cand=0 relevant_in_pool=False expected=['宫保鸡丁', '鸡胸肉沙拉'] actual=[]
  - q020 「适合下饭的番茄菜」 cand=0 relevant_in_pool=False expected=['番茄炒蛋', '西红柿鸡蛋汤'] actual=[]
  - q021 「下饭菜谱」 cand=0 relevant_in_pool=False expected=['鱼香肉丝', '宫保鸡丁', '麻婆豆腐'] actual=[]
  - q022 「简单的家常菜」 cand=0 relevant_in_pool=False expected=['番茄炒蛋', '蛋炒饭', '西红柿鸡蛋汤'] actual=[]
  - q028 「鸡蛋」 cand=0 relevant_in_pool=False expected=['番茄炒蛋', '西红柿鸡蛋汤', '蛋炒饭'] actual=[]
  - q029 「五花肉」 cand=1 relevant_in_pool=False expected=['红烧肉'] actual=['红烧肉经典做法']
  - q034 「木耳 胡萝卜 猪肉」 cand=0 relevant_in_pool=False expected=['鱼香肉丝'] actual=[]
  - q035 「剩饭怎么做」 cand=1 relevant_in_pool=False expected=['蛋炒饭'] actual=['蛋炒饭做法']

## 9. 延迟（各阶段平均，ms）

| Threshold | RAG | Merge | RRF | Rerank(含RRF) |
|---:|---:|---:|---:|---:|
| 0.2 | 1269.7 | 0.1 | 0.0 | 0.2 |
| 0.25 | 1342.3 | 0.1 | 0.0 | 0.1 |
| 0.3 | 1350.8 | 0.1 | 0.0 | 0.2 |
| 0.35 | 1196.9 | 0.1 | 0.0 | 0.2 |
| 0.4 | 1281.2 | 0.1 | 0.0 | 0.1 |
| 0.45 | 1267.9 | 0.1 | 0.0 | 0.1 |
| 0.5 | 1279.1 | 0.1 | 0.0 | 0.1 |

## 10. 结论

见 README「Retrieval Benchmark」章节与本报告数据；所有数字均来自真实运行。
