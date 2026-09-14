# AI 私人厨师 (AI-Chief-Master)

基于 **FastAPI + LangGraph 多 Agent + Hybrid Retrieval (RAG + Tavily)** 的多模态食谱推荐系统。上传食材图片或输入文字描述，多个专职 Agent 协作完成食材识别、口味偏好理解、菜谱检索、营养分析与质量审核，并以 SSE 流式对话形式输出结构化的食谱推荐报告；不达标的结果会触发定向重试。

## 功能特性

- **多 Agent 协作**：Supervisor 编排 6 个专职 Agent（食材 / 偏好 / 菜谱 / 营养 / 审核 / 终答），支持并行与失败感知的定向重试
- **食材图片识别**：支持上传 jpg / png / gif / webp 等格式，通过通义千问多模态模型识别食材
- **本地菜谱知识库（RAG）**：基于 Chroma 向量数据库的本地菜谱检索，稳定、低延迟
- **联网食谱搜索**：集成 Tavily Search，根据可用食材检索可行菜谱
- **混合检索融合**：RAG + Tavily 结果经去重 → RRF 融合 → 食材感知重排序（Ingredient-aware Rerank）三段式 Pipeline
- **智能评估排序**：从营养价值、制作难度等维度打分并排序
- **质量审核与重试**：CriticAgent 审核检索与推荐质量，按失败类型定向回退对应 Agent（最多 2 次）
- **SSE 流式对话**：AI 回复实时逐字输出，各 Agent 阶段状态实时推送，支持 Markdown 渲染
- **多会话管理**：新建对话、切换历史会话、删除会话，按 `thread_id` 隔离
- **图片云存储**：食材图片上传至阿里云 OSS
- **可观测性**：请求级 Trace（RAG/Tavily/RRF 各阶段延迟）与指标采集，可选 LangSmith 追踪

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn |
| Agent 编排 | LangGraph `StateGraph`（7 节点多 Agent 工作流 + 失败感知条件路由） |
| 大模型 | 通义千问 `qwen3.6-flash-2026-04-16`（DashScope OpenAI 兼容接口） |
| 向量模型 | 通义千问 `text-embedding-v2`（DashScope 原生 API） |
| 向量数据库 | Chroma（Docker volume `ai_chief_chroma_data` 持久化） |
| 检索融合 | Dedup + RRF Fusion（k=60）+ Ingredient-aware Rerank |
| 联网搜索 | Tavily Search |
| 会话持久化 | LangGraph `PyMySQLSaver`（MySQL 主）+ `SqliteSaver`（自动回退备份） |
| 数据库 | MySQL 8.0（主）+ SQLite（`backend/data/personal_chief.db` 备份保留） |
| 对象存储 | 阿里云 OSS（`oss2`） |
| 可观测性 | 自研 Trace/Metrics（`app/observability/`）+ LangSmith（可选） |
| 容器化 | Docker Compose（mysql + backend + frontend） |
| 前端框架 | Vue 3 + Vite 5 |
| UI / 流式 | Ant Design Vue、@microsoft/fetch-event-source、markstream-vue |

## 项目结构

```
AI-Chief-Master/
├── backend/                        # Python 后端
│   ├── app/
│   │   ├── main.py                 # FastAPI 入口
│   │   ├── agents/                 # LangGraph 多 Agent 工作流
│   │   │   ├── workflow.py         # StateGraph 拓扑（并行 + 失败感知路由）
│   │   │   ├── state.py            # RecipeState（messages + current_* 当前轮字段）
│   │   │   ├── supervisor.py       # 执行规划
│   │   │   ├── ingredient_agent.py # 食材识别（含多模态）
│   │   │   ├── preference_agent.py # 口味偏好解析
│   │   │   ├── recipe_agent.py     # 混合检索（RAG + Tavily + Pipeline 融合）
│   │   │   ├── nutrition_agent.py  # 营养分析
│   │   │   ├── critic_agent.py     # 质量审核 + 重试路由
│   │   │   ├── final_answer.py     # 结构化推荐输出
│   │   │   ├── shared.py           # 模型/Checkpointer/工具单例
│   │   │   └── personal_chief.py   # SSE 流式编排（status/chunk/done 事件）
│   │   ├── rag/                    # 检索模块
│   │   │   ├── embedding.py        # DashScope text-embedding-v2
│   │   │   ├── ingest.py           # 菜谱入库（Markdown → Chroma）
│   │   │   ├── retriever.py        # Chroma 相似度检索 + RAG 内部 rerank
│   │   │   └── retrieval_pipeline.py # Dedup → RRF → Ingredient Rerank
│   │   ├── api/v1/                 # chat.py（SSE 对话）、oss.py（上传）
│   │   ├── db/database.py           # MySQL 初始化
│   │   ├── models/                 # Pydantic / SQLAlchemy 模型
│   │   ├── observability/          # trace.py（阶段延迟）、metrics.py
│   │   ├── services/               # 会话 CRUD
│   │   └── common/logger.py        # 日志配置
│   ├── data/
│   │   ├── recipes/                # 本地菜谱知识库（Markdown）
│   │   ├── chroma/                 # Chroma 向量库（本地开发）
│   │   ├── benchmark/              # 检索基准测试结果
│   │   └── personal_chief.db       # SQLite Checkpointer 备份
│   ├── tests/                      # 单元测试 + 检索基准脚本
│   │   ├── data/                   # 35 条标注查询 + Tavily 离线 fixtures
│   │   ├── test_retrieval_benchmark.py / test_retrieval_pipeline.py
│   │   ├── test_observability.py / test_ingredient_context.py
│   │   ├── test_failure_aware_routing.py
│   │   ├── benchmark_retrieval.py / benchmark_ablation.py
│   │   └── verify_prod_env.py / run_sse_test.py  # 生产验证脚本
│   ├── Dockerfile
│   ├── .env / .env.example         # 环境变量（勿提交到 Git）
│   └── pyproject.toml
├── frontend/                       # Vue 3 前端（Nginx 容器，对外 8080）
├── docker-compose.yml              # mysql + backend + frontend
├── start.ps1 / stop.ps1            # Windows 一键启停脚本
└── README.md
```

## 环境要求

- **Python** >= 3.10（本地开发）
- **Docker** + Docker Compose（推荐部署方式）
- **Node.js** >= 18（仅本地前端开发需要）
- 通义千问 DashScope API Key
- Tavily API Key
- 阿里云 OSS 账号（Bucket + AccessKey）

## 环境变量

在 `backend/` 目录创建 `.env` 文件（参考 `backend/.env.example`，已在 `.gitignore` 中忽略；Docker 部署时由 compose `env_file` 自动注入）：

```env
# 通义千问（DashScope OpenAI 兼容接口）
DASHSCOPE_API_KEY=your_dashscope_api_key
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

# Embedding 模型（用于 RAG，DashScope 原生 API）
EMBEDDING_MODEL=text-embedding-v2
DASHSCOPE_EMBEDDING_URL=https://dashscope.aliyuncs.com/api/v1

# Tavily 联网搜索
TAVILY_API_KEY=your_tavily_api_key

# 阿里云 OSS
OSS_ACCESS_KEY_ID=your_access_key_id
OSS_ACCESS_KEY_SECRET=your_access_key_secret
OSS_BUCKET=your_bucket_name
OSS_ENDPOINT=oss-cn-beijing.aliyuncs.com

# LangSmith 追踪（可选）
LANGSMITH_API_KEY=your_langsmith_api_key
LANGSMITH_TRACING=false
LANGSMITH_PROJECT=personal-chief

# ===== RAG 检索配置 =====
# 相似度阈值（0~1，越大越严格）。低于此值的 RAG 结果被过滤
# 2026-09-14 Ablation 实验后由 0.50 调整为 0.35：
#   Hit@3 0.6129 → 0.9677，平均候选池 1.31 → 5.66，空候选池 8/35 → 0
RAG_SCORE_THRESHOLD=0.35

# RAG 内部 rerank 权重（语义 + 食材匹配，和约为 1.0）
RAG_SEMANTIC_WEIGHT=0.4
RAG_INGREDIENT_WEIGHT=0.6

# Hybrid Retrieval 融合权重（RRF 分数 + 食材匹配，和约为 1.0）
RRF_FINAL_WEIGHT=0.5
RRF_INGREDIENT_WEIGHT=0.5

# ===== MySQL（LangGraph Checkpointer，Docker 内主机名为 mysql）=====
MYSQL_HOST=mysql
MYSQL_PORT=3306
MYSQL_USER=your_user
MYSQL_PASSWORD=your_password
MYSQL_ROOT_PASSWORD=your_root_password
MYSQL_DATABASE=ai_chief
```

> MySQL 不可用时自动回退 SQLite（`backend/data/personal_chief.db`），服务不中断。

## 快速启动

### 方式一：Docker 一键部署（推荐）

```powershell
# Windows：右键 start.ps1 → 使用 PowerShell 运行（或执行 ./start.ps1）
# 等价于：
docker compose up -d
```

启动内容：

| 服务 | 容器 | 端口 | 说明 |
|------|------|------|------|
| mysql | ai-chief-mysql | 3306（内部） | LangGraph Checkpointer，healthcheck 就绪 |
| backend | ai-chief-backend | 8001（内部） | FastAPI，不对外暴露 |
| frontend | ai-chief-frontend | **8080 → 80** | Nginx 托管前端并将 `/api` 转发到 backend |

- 访问入口：http://localhost:8080
- 健康检查：http://localhost:8080/health（Nginx 已配置 SSE 透传：`proxy_buffering off`）
- Chroma 数据持久化在 Docker volume `ai_chief_chroma_data`；首次启动需初始化向量库（见下）
- 修改 `backend/.env` 后需 `docker compose up -d --force-recreate backend` 才能生效（`restart` 不重读 env_file）

```powershell
# 首次启动后，向容器内 Chroma 初始化菜谱向量库
docker exec ai-chief-backend python -m app.rag.ingest

# 常用命令
docker compose logs -f backend     # 查看后端日志
./stop.ps1                          # 或 docker compose down
```

### 方式二：本地开发

#### 1. 启动后端

```bash
# 创建并激活虚拟环境
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

# 安装依赖
cd backend
pip install -e .

# oss.py 使用 oss2 库，需额外安装
pip install oss2

# 启动服务（默认 http://127.0.0.1:8001）
python -m app.main
```

#### 1.1 初始化 RAG 向量库（首次必做）

```bash
cd backend

# 将 data/recipes/ 中的菜谱向量化并存入 Chroma
python -m app.rag.ingest
```

执行后会在 `backend/data/chroma/` 生成向量数据库文件。
菜谱源文件位于 `backend/data/recipes/`，可自行添加更多 Markdown 菜谱。

启动后可访问 Swagger 文档：http://127.0.0.1:8001/docs

#### 2. 启动前端

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 http://localhost:5173 即可使用。开发环境下，Vite 会将 `/api` 请求代理到后端 `http://127.0.0.1:8001`。

#### 3. 生产构建（可选）

```bash
cd frontend
npm run build
```

构建产物输出至 `frontend/dist/`，需配置反向代理将 `/api` 转发到后端服务。

## RAG 本地菜谱知识库与混合检索

系统内置基于 Chroma 的本地 RAG 检索能力，与 Tavily 联网搜索形成混合检索，经统一融合 Pipeline 输出最终候选，兼顾稳定性与覆盖面。

### 检索架构（三段式融合 Pipeline）

```
User Query (结构化: current_ingredients + preferences)
     ↓
RecipeAgent（检索编排，RAG 不新增 Graph 节点）
     ├── Chroma RAG (本地知识库, Top-5, threshold=0.35 过滤)
     │     └── RAG 内部 rerank: 0.4*语义 + 0.6*食材匹配
     └── Tavily    (联网搜索, Top-5)
     ↓
 ① Deduplication（URL / 标题去重）
     ↓
 ② RRF Fusion（rank-based, k=60: 1/(60+rank) 融合两路排名）
     ↓
 ③ Ingredient-aware Rerank（食材归一化集合匹配）
     ↓
 Final Score = 0.5 * RRF + 0.5 * 食材匹配度 → Top-3
     ↓
 LLM 整理为结构化菜谱 → current_recipes
```

### 模块说明

| 模块 | 路径 | 职责 |
|------|------|------|
| 菜谱源数据 | `backend/data/recipes/*.md` | Markdown 格式的本地菜谱知识库 |
| Embedding | `app/rag/embedding.py` | DashScope `text-embedding-v2`，调用原生 API |
| 入库脚本 | `app/rag/ingest.py` | Markdown → Document → Embedding → Chroma |
| 检索器 | `app/rag/retriever.py` | 相似度搜索 + 阈值过滤 + RAG 内部食材 rerank |
| 融合 Pipeline | `app/rag/retrieval_pipeline.py` | Dedup → RRF 融合 → 食材感知重排序 |
| 混合检索编排 | `app/agents/recipe_agent.py` | RAG + Tavily 并行检索，Pipeline 融合，优雅降级 |
| 可观测性 | `app/observability/` | RAG/Tavily/RRF 各阶段延迟追踪 |

### 关键设计

1. **RAG 不新增 Graph 节点**：作为 RecipeAgent 内部能力，不改变 LangGraph 拓扑
2. **结构化 Query**：RAG 和 Tavily 的查询都只从 `current_ingredients`、`current_preferences`、`retry_constraints.search_keywords` 构建，绝不拼接自然语言
3. **三段式融合**：去重 → RRF 融合两路排名 → 食材感知重排序，本地菜谱因标注食材完整通常在 rerank 后占优
4. **优雅降级**：RAG 不可用时自动降级为纯 Tavily 搜索，不影响主流程
5. **状态隔离**：RAG 结果只写入 `current_recipes`，每轮重置，不跨轮污染
6. **Retry 兼容**：Critic 的 `retry_constraints.search_keywords` 同时作用于 RAG 和 Tavily 查询
7. **阈值可调**：`RAG_SCORE_THRESHOLD=0.35`（经 Ablation 实验校准，见下节）

### 添加新菜谱

1. 在 `backend/data/recipes/` 新建 `.md` 文件，按已有菜谱格式编写（需包含 `## 食材` 区块，rerank 依赖其解析食材）
2. 重新执行入库：`python -m app.rag.ingest`（自动去重，可重复执行；Docker 部署时在容器内执行）

## Retrieval Benchmark

系统提供可重复的检索基准测试，通过实验回答 RAG / Tavily / Hybrid 检索的有效性问题。

### 快速运行

```bash
cd backend

# 离线模式（默认，使用 Tavily fixtures，适合 CI）
python tests/benchmark_retrieval.py --offline

# 在线模式（调用真实 Tavily API）
python tests/benchmark_retrieval.py --online

# 完全跳过 Tavily
python tests/benchmark_retrieval.py --skip-tavily
```

输出文件位于 `backend/data/benchmark/`：
- `retrieval_benchmark_results.json` — 完整结果（含 per-query）
- `retrieval_benchmark_results.csv` — 策略对比表
- `retrieval_benchmark_report.md` — 人类可读报告

### 测试数据

| 文件 | 说明 |
|------|------|
| `tests/data/retrieval_benchmark.json` | 35 条标注查询，覆盖 exact_ingredient / multi_ingredient / synonym / preference / ambiguous / rag_miss 6 类 |
| `tests/data/tavily_benchmark_fixtures.json` | 22 条 Tavily 离线 fixture，用于 CI 可重复性 |

### 4 种策略对比

| 策略 | 说明 |
|------|------|
| `rag_only` | 仅 Chroma RAG 检索 |
| `tavily_only` | 仅 Tavily 联网搜索 |
| `hybrid_merge` | RAG + Tavily 简单合并去重 |
| `hybrid_rrf` | RRF 融合 + Ingredient-aware Rerank（生产 pipeline） |

### Metrics

- **Hit@1 / Hit@3 / Hit@5**：relevant title 出现在 Top-K 结果中
- **MRR**：第一个 relevant recipe 排名的倒数
- **Ingredient Coverage**：返回结果中覆盖用户食材的比例
- **Avg / P50 / P95 Latency**：延迟均值与百分位
- **RAG Hit Rate / Tavily Success Rate / Fallback Rate**

### Sweep 实验

| 实验 | 参数 | 范围 |
|------|------|------|
| Threshold Sweep | RAG score threshold | 0.30 ~ 0.70 |
| RRF Weight Sweep | final / ingredient weight | 0.2/0.8 ~ 0.8/0.2 |
| Top-K Sweep | top_k | 1, 3, 5 |

### Benchmark 结果（Offline, 2026-09-14）

#### 策略对比

| 策略 | Hit@1 | Hit@3 | MRR | Coverage | Avg Latency | P95 Latency |
|------|------:|------:|----:|---------:|------------:|------------:|
| rag_only | 0.5161 | 0.5484 | 0.5323 | 0.4462 | 1534.9ms | 3014.2ms |
| tavily_only | 0.2581 | 0.2581 | 0.2581 | 0.0645 | 2.1ms | 2.2ms |
| hybrid_merge | 0.5806 | 0.6129 | 0.5968 | 0.4462 | 1620.3ms | 2592.8ms |
| hybrid_rrf | 0.5806 | 0.6129 | 0.5968 | 0.4462 | 1422.0ms | 2257.3ms |

#### Threshold Sweep

| Threshold | Hit@3 | Coverage | RAG Hit Rate |
|----------:|------:|---------:|-------------:|
| 0.30 | 0.9677 | 0.6774 | 1.0000 |
| **0.35（生产值）** | **0.9677** | **0.6774** | **1.0000** |
| 0.40 | 0.9032 | 0.6452 | 0.9714 |
| 0.50（旧值） | 0.6129 | 0.4462 | 0.7714 |
| 0.60 | 0.3871 | 0.1667 | 0.6571 |
| 0.70 | 0.2581 | 0.0645 | 0.6286 |

> 0.35 行数据来自 Ablation 实验（0.20~0.35 四个点结果一致，RAG top_k=5 形成候选上限；空候选池=0）。

#### RRF Weight Sweep

| Final / Ingredient | Hit@3 | MRR |
|-------------------:|------:|----:|
| 0.2 / 0.8 | 0.6129 | 0.5968 |
| 0.5 / 0.5（默认） | 0.6129 | 0.5968 |
| 0.8 / 0.2 | 0.6129 | 0.5968 |

> 所有权重组合产生相同结果，表明当前数据集下 RRF 权重对 Top-3 排序无影响。

#### Top-K Sweep

| Top-K | Hit | Coverage | Avg Latency |
|------:|----:|---------:|------------:|
| 1 | 0.5806 | 0.4462 | 1355.4ms |
| **3** | **0.6129** | **0.4462** | **1300.9ms** |
| 5 | 0.6129 | 0.4462 | 1554.2ms |

### 关键发现

1. **RAG 有效**：Hit@3=0.5484，是主要检索来源，但 51.4% 查询无结果（threshold 过高）
2. **Tavily 有限**：Hit@3=0.2581，Coverage=0.0645，但延迟极低（2ms），作为补充有价值
3. **Hybrid 优于单一**：Hit@3 从 0.5484 提升到 0.6129（+11.8%），Tavily 补充了 RAG 未命中的查询
4. **RRF 对排序无影响**：RRF weight sweep 显示所有权重组合结果相同，但 RRF pipeline 的 P95 延迟比简单合并低 13%（2257ms vs 2593ms）
5. **Ingredient Rerank 无效果**：权重从 0.2 到 0.8 结果一致，说明 rerank 未改变 Top-3 排序
6. **threshold=0.50 过高**：0.30 时 Hit@3=0.9677（+58%），建议降至 0.30~0.40
7. **RRF weight=0.5/0.5 可接受**：无敏感度差异，保持默认即可
8. **Top-K=3 合理**：k=3 与 k=5 效果相同但延迟更低
9. **延迟分析**：RAG 主导延迟（~1.3s），Tavily 几乎零开销（2ms），RRF pipeline 比简单合并快 13%
10. **主要问题**：RAG threshold 过高导致大量漏检；Tavily Coverage 极低；RRF rerank 未实际影响排序

### Retrieval Ablation（Candidate Pool 假设验证, 2026-09-14）

> 完整报告：`backend/data/benchmark/retrieval_ablation_report.md`

验证假设：**Candidate Pool 过小是 RRF 与 Ingredient Rerank 无效的主要原因**。

```bash
cd backend
python tests/run_ablation_inline.py   # 需在容器内运行（访问 Chroma）
```

输出：`retrieval_ablation_results.json` / `.csv` / `_report.md`

#### Threshold Sweep（Pipeline D = Hybrid RRF + Rerank）

| Threshold | Avg Cand | Med Cand | Pool=0 | Hit@1 | Hit@3 | Hit@5 | MRR | Coverage | FP Rate |
|----------:|---------:|---------:|-------:|------:|------:|------:|----:|---------:|--------:|
| 0.20 | 5.66 | 6 | 0 | 0.8065 | 0.9677 | 1.0000 | 0.8898 | 0.6774 | 0.5935 |
| 0.30 | 5.66 | 6 | 0 | 0.8065 | 0.9677 | 1.0000 | 0.8898 | 0.6774 | 0.5935 |
| 0.35 | 5.66 | 6 | 0 | 0.8065 | 0.9677 | 1.0000 | 0.8898 | 0.6774 | 0.5935 |
| 0.40 | 4.20 | 5 | 1 | 0.7742 | 0.9032 | 0.9355 | 0.8468 | 0.6452 | 0.5159 |
| 0.45 | 2.11 | 2 | 4 | 0.8065 | 0.8387 | 0.8387 | 0.8226 | 0.5538 | 0.3043 |
| 0.50（实验前生产值） | 1.31 | 1 | 8 | 0.5806 | 0.6129 | 0.6129 | 0.5968 | 0.4462 | 0.3182 |

> 0.20~0.35 结果完全一致：RAG top_k=5 已提供全部候选，继续降低 threshold 不再产生新候选。

#### Ablation：4 Pipeline × 3 Threshold

| Threshold | Pipeline | Hit@3 | MRR | ranking_changed | rerank_changed | Hit 转换 |
|----------:|----------|------:|----:|----------------:|---------------:|----------|
| 0.50 (cand=1.31) | rag_only / merge / rrf / rerank | 0.5484~0.6129 | 0.5323~0.5968 | 8.57% | 5.71% | 无 |
| 0.40 (cand=4.20) | rag_only → rrf | 0.8710→0.9032 | 0.8548→0.8629 | 54.29% | 22.86% | RRF +1（q004） |
| 0.30 (cand=5.66) | rag_only → rrf → rerank | 0.9355→0.9677 | 0.9194→0.8898 | 65.71% | 31.43% | RRF +1/-1，Rerank +1（q003） |

#### Candidate Count 与 Rerank 变化率（threshold=0.40）

| Candidate Count | Queries | RRF Changed | Rerank Changed |
|----------------:|--------:|------------:|---------------:|
| 0~2 | 6 | 0.00% | 0.00% |
| 3 | 7 | 42.86% | 0.00% |
| 4 | 4 | 50.00% | 0.00% |
| 5+ | 18 | 77.78% | 44.44% |

#### Ablation 结论

1. **假设成立**：threshold=0.50 时平均候选仅 1.31（中位数 1），8/35 查询候选为 0；候选 ≤2 时 RRF/Rerank 变化率为 0% —— 无空间可重排
2. **RRF 开始有效**：cand≥3 后变化率跳升至 43~100%，threshold=0.40 时 RRF 使 Hit@3 +3.2pp（q004 被顶入 Top-3）
3. **Rerank 开始有效但幅度小**：threshold=0.30 时 rerank_changed=31.43%，挽回 q003（RRF 降级的那条），最终 Hit@3 达 0.9677；但 MRR 略降（0.9194→0.8898），Hit@1 略降
4. **threshold 建议 0.35**（推荐规则：最高 Hit@3 ≥ max-0.02 的最大 threshold）
5. **组件保留建议**：RRF=KEEP；Ingredient Rerank=KEEP（在低 threshold 下有正贡献）
6. **Top-K=3 仍合理**：Hit@5=1.0 说明相关结果基本都在 Top-3 内

#### 生产落地（2026-09-14）

基于上述结论，`backend/.env` 中 `RAG_SCORE_THRESHOLD` 已由 **0.50 正式调整为 0.35**：

- 回归验证：55 个单元测试通过、`compileall` 通过、MySQL Checkpointer（PyMySQLSaver）正常
- 真实查询验证（SSE 端到端）：「西红柿鸡蛋」「牛肉土豆」「西红柿鸡蛋 + 不吃辣」三条全部正常，RAG 候选 5/5 通过阈值、无空候选池回退，Ingredient Rerank 使食材匹配度 1.0 的本地菜谱稳定进入 Top-3，偏好约束（不吃辣）正确生效
- 生产验证脚本：`backend/tests/verify_prod_env.py`（环境自检）、`backend/tests/run_sse_test.py`（SSE 端到端）

### 单元测试

```bash
cd backend
python -m pytest -q          # 全量：55 passed
python -m compileall app     # 语法编译检查
```

| 测试文件 | 覆盖内容 |
|----------|----------|
| `test_retrieval_benchmark.py` | Dataset 加载、Tavily Fixtures、Metrics 计算、百分位、错误分析、排序变化判断（titles_differ）、False Positive、候选分桶、候选数与 rerank 关系、Hit 转换、新候选分析、threshold 推荐、Ablation 四管线端到端（fake RAG + 真实 dedup/RRF/rerank）、threshold 设置与恢复 |
| `test_retrieval_pipeline.py` | 融合 Pipeline（Dedup / RRF / Ingredient Rerank）单元逻辑 |
| `test_observability.py` | Trace / Metrics 采集 |
| `test_ingredient_context.py` | 食材上下文传递 |
| `test_failure_aware_routing.py` | Critic 失败感知重试路由 |

## API 接口

### 聊天与会话

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/chat/stream` | SSE 流式对话（核心接口） |
| `GET` | `/api/v1/chat/messages?thread_id=` | 获取会话历史消息 |
| `GET` | `/api/v1/chat/sessions` | 获取所有会话列表 |
| `POST` | `/api/v1/chat/sessions?thread_id=&title=` | 创建或更新会话 |
| `PUT` | `/api/v1/chat/sessions/{thread_id}?title=` | 更新会话标题 |
| `DELETE` | `/api/v1/chat/sessions/{thread_id}` | 删除会话及 Agent 记忆 |

**流式对话请求体：**

```json
{
  "message": "帮我推荐几道家常菜",
  "image_url": "https://example.com/food.jpg",
  "thread_id": "thread_1234567890_abc"
}
```

### 文件上传

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/oss/upload` | 上传图片到 OSS（最大 10MB） |
| `GET` | `/api/v1/oss/presign-url?oss_key=&expires=` | 获取预签名访问 URL |

### 健康检查

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 返回 `{"status": "ok"}` |

## Agent 工作流程

```
用户输入（文本 + 可选图片 URL，HumanMessage 多模态）
        ↓
   ┌────────────┐
   │ Supervisor │  规划本轮执行策略（只使用 current_* 当前轮状态）
   └─────┬──────┘
         ↓ fan-out 并行
   ┌─────────────────────┬─────────────────────┐
   │  IngredientAgent    │  PreferenceAgent     │
   │  食材识别/新鲜度评估  │  口味偏好/忌口解析    │
   └──────────┬──────────┴──────────┬──────────┘
              ↓ fan-in              ↓
        ┌───────────────────────────┐
        │ RecipeAgent（混合检索）      │
        │ RAG(Chroma) + Tavily      │
        │ → Dedup → RRF → Rerank    │
        └────────────┬──────────────┘
                     ↓
             ┌───────────────┐
             │ NutritionAgent │  营养分析
             └───────┬───────┘
                     ↓
             ┌───────────────┐
             │  CriticAgent    │  质量审核
             └───────┬───────┘
                     ↓ should_retry 条件路由
        ┌────────────┼────────────────┐
        │ 菜谱问题    │ 营养问题 │ 规划问题 │ 通过/无食材/重试上限
        ↓            ↓         ↓        ↓
  RecipeAgent   NutritionAgent  Supervisor  FinalAnswer
  （重检索）      （重分析）      （完整重跑）  （结构化推荐 → END）
```

- **每轮状态隔离**：`RecipeState` 区分历史 `messages` 与当前轮 `current_*` 字段（current_ingredients / current_preferences / current_recipes / current_retry_count 等），新一轮开始时重置，避免跨轮污染
- **失败感知重试**：CriticAgent 按失败类型定向回退（MAX_RETRY=2），通过 `retry_constraints.search_keywords` 修正下轮检索查询
- **SSE 阶段推送**：基于 `stream_mode="debug"` 实时发射各 Agent 的 running/completed status 事件（如「正在分析你的食材…」），随后 chunk 逐字流式输出最终推荐
- **多模态输入**：图片走通义千问多模态识别，文字与图片可同时提供

## 数据存储

| 存储层 | 机制 | 数据 | 说明 |
|--------|------|------|------|
| Agent 记忆 | LangGraph `PyMySQLSaver` | 完整对话 messages / State | Docker 内 MySQL 8.0（`ai_chief` 库），按 `thread_id` 隔离会话 |
| Agent 记忆备份 | LangGraph `SqliteSaver` | 同上 | MySQL 不可用时自动回退，`backend/data/personal_chief.db` |
| 会话元数据 | `sessions` 表 | thread_id、title、created_at、updated_at | MySQL（本地开发为 SQLite） |
| 菜谱向量库 | Chroma | 15 条本地菜谱 embedding | Docker volume `ai_chief_chroma_data`（本地开发 `backend/data/chroma/`） |

- Checkpointer 表由官方 setup 方法初始化（checkpoints / checkpoint_blobs / checkpoint_writes / checkpoint_migrations），不使用自定义表结构
- 前端通过 `localStorage` 的 `cook_thread_id` 键维护当前会话 ID
- 删除会话时会同时清空 LangGraph checkpoint 中的 Agent 记忆

## 典型使用流程

1. 用户上传食材图片 → `POST /api/v1/oss/upload` → 获得 `file_url`
2. 输入文字描述（可选）→ `POST /api/v1/chat/stream` → SSE 实时显示推荐报告
3. 通过右上角菜单管理会话：新建对话、查看历史、切换或删除

## 注意事项

- 环境变量文件位于 `backend/.env`（非项目根目录），含敏感密钥，请勿提交到版本库
- `pyproject.toml` 中声明了 `alibabacloud-oss-v2`，但 `oss.py` 实际使用 `oss2`，本地安装时需额外执行 `pip install oss2`
- 后端默认端口 `8001`（Docker 内部），前端开发端口 `5173`、Docker 访问端口 `8080`
- 修改 `backend/.env` 后需 `docker compose up -d --force-recreate backend`（`restart` 不会重读 env_file）
- MySQL 凭据只从 `backend/.env` 读取，代码中不硬编码；连接失败自动回退 SQLite
- 删除会话时会同时清空 LangGraph checkpoint 中的 Agent 记忆
- 本地 SQLite（`backend/data/personal_chief.db`）与 Chroma 数据为持久化数据，请勿删除

## License

MIT
