"""Chroma 向量库检索器。

Score 语义说明：
- Chroma 使用 L2 距离（squared Euclidean），默认 collection metadata 为 None
- similarity_search_with_score 返回原始 L2 距离，越小越相似
- 本模块通过 1/(1+distance) 转换为 0~1 的相似度，越大越相关
- RAG_SCORE_THRESHOLD 控制最低相似度，低于此值的结果被过滤

Rerank 流程（在 threshold 之后）：
- 从 RAG 结果的 Markdown content 中提取菜谱食材列表
- 将用户食材和菜谱食材做归一化后集合匹配
- ingredient_match_score = 匹配到的用户食材数 / 用户食材总数
- rerank_score = semantic_score * w1 + ingredient_match_score * w2
- 按 rerank_score 降序排序后返回
"""
import os
import re
import logging
from typing import List, Dict, Optional

from langchain_chroma import Chroma
from langchain_core.documents import Document

from app.rag.embedding import get_embedding_function

logger = logging.getLogger(__name__)

# 常量
CHROMA_PERSIST_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "chroma"
)
COLLECTION_NAME = "recipe_knowledge_base"
TOP_K = 3

# 默认阈值：可通过 .env 的 RAG_SCORE_THRESHOLD 覆盖
DEFAULT_SCORE_THRESHOLD = 0.50

# 默认 rerank 权重
DEFAULT_SEMANTIC_WEIGHT = 0.4
DEFAULT_INGREDIENT_WEIGHT = 0.6

_vector_store: Optional[Chroma] = None

# 食材同义词归一化表
# 仅覆盖当前知识库中实际存在的同义词，不盲目扩展
INGREDIENT_ALIASES = {
    # 西红柿 / 番茄
    "西红柿": "番茄",
    "西红柿子": "番茄",
    "小番茄": "番茄",
    "番茄": "番茄",
    # 土豆 / 马铃薯
    "土豆": "马铃薯",
    "马铃薯": "马铃薯",
    "洋芋": "马铃薯",
}


def get_score_threshold() -> float:
    """从环境变量读取相似度阈值，解析失败则用默认值。"""
    raw = os.getenv("RAG_SCORE_THRESHOLD", str(DEFAULT_SCORE_THRESHOLD))
    try:
        val = float(raw)
        if val < 0.0 or val > 1.0:
            logger.warning(f"[RAG] RAG_SCORE_THRESHOLD={val} 超出 [0,1] 范围，使用默认值 {DEFAULT_SCORE_THRESHOLD}")
            return DEFAULT_SCORE_THRESHOLD
        return val
    except ValueError:
        logger.warning(f"[RAG] RAG_SCORE_THRESHOLD='{raw}' 非合法浮点数，使用默认值 {DEFAULT_SCORE_THRESHOLD}")
        return DEFAULT_SCORE_THRESHOLD


def get_rerank_weights() -> tuple[float, float]:
    """从环境变量读取 rerank 权重，校验之和约等于 1。"""
    try:
        sw = float(os.getenv("RAG_SEMANTIC_WEIGHT", str(DEFAULT_SEMANTIC_WEIGHT)))
    except ValueError:
        sw = DEFAULT_SEMANTIC_WEIGHT
    try:
        iw = float(os.getenv("RAG_INGREDIENT_WEIGHT", str(DEFAULT_INGREDIENT_WEIGHT)))
    except ValueError:
        iw = DEFAULT_INGREDIENT_WEIGHT

    total = sw + iw
    if abs(total - 1.0) > 0.05:
        logger.warning(f"[RAG] rerank 权重之和={total:.2f}，偏离 1.0，使用默认值 {DEFAULT_SEMANTIC_WEIGHT}/{DEFAULT_INGREDIENT_WEIGHT}")
        return DEFAULT_SEMANTIC_WEIGHT, DEFAULT_INGREDIENT_WEIGHT
    return sw, iw


def _normalize_ingredient(name: str) -> str:
    """食材名称归一化：查别名表，未命中则原样返回。"""
    name = name.strip()
    return INGREDIENT_ALIASES.get(name, name)


def _extract_recipe_ingredients(content: str) -> List[str]:
    """从菜谱 Markdown 内容中解析食材名称列表。

    解析 ## 食材 区块，提取每行 "- 食材名：用量" 的食材名部分。
    """
    ingredients = []
    in_ingredient_section = False

    for line in content.split("\n"):
        stripped = line.strip()

        # 检测食材区块开始
        if re.match(r"^#{2,3}\s*食材", stripped):
            in_ingredient_section = True
            continue

        # 遇到下一个同级或更高级标题，结束区块
        if in_ingredient_section and re.match(r"^#{2,3}\s", stripped):
            break

        if not in_ingredient_section:
            continue

        # 解析 "- 食材名：用量" 或 "- 食材名: 用量"
        m = re.match(r"^[-*]\s*(.+?)[：:]", stripped)
        if m:
            ingredient_name = m.group(1).strip()
            if ingredient_name:
                ingredients.append(ingredient_name)

    return ingredients


def _calculate_ingredient_match_score(
    user_ingredients: List[str],
    recipe_ingredients: List[str],
) -> tuple[float, List[str]]:
    """计算食材匹配度。

    Returns:
        (score, matched_names)
        score = 匹配到的用户食材数 / 用户食材总数
        matched_names: 实际匹配到的食材名称列表
    """
    if not user_ingredients:
        return 0.0, []

    user_normalized = {_normalize_ingredient(name) for name in user_ingredients if name.strip()}
    recipe_normalized = {_normalize_ingredient(name) for name in recipe_ingredients if name.strip()}

    if not user_normalized:
        return 0.0, []

    matched = user_normalized & recipe_normalized
    score = len(matched) / len(user_normalized)

    return round(score, 4), sorted(matched)


def get_vector_store() -> Optional[Chroma]:
    """获取 Chroma 向量库实例（懒加载，失败返回 None）。"""
    global _vector_store
    if _vector_store is not None:
        return _vector_store

    try:
        os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)
        embeddings = get_embedding_function()
        _vector_store = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=embeddings,
            persist_directory=CHROMA_PERSIST_DIR,
        )
        logger.info(f"[RAG] Chroma 向量库加载成功: {CHROMA_PERSIST_DIR}")
        return _vector_store
    except Exception as e:
        logger.error(f"[RAG] Chroma 初始化失败: {e}")
        _vector_store = None
        return None


def search_recipes(
    query: str,
    top_k: int = TOP_K,
    user_ingredients: Optional[List[Dict]] = None,
) -> List[Dict]:
    """从本地 RAG 检索菜谱，过滤低相似度结果并按食材匹配度重排序。

    流程：
        Chroma similarity search → Distance→Similarity → Threshold Filter
        → Ingredient Match → Rerank → Sort by rerank_score DESC

    Args:
        query: 搜索查询（结构化构建，如"西红柿 鸡蛋 晚餐"）
        top_k: 最多召回多少条（召回上限，非最终返回数）
        user_ingredients: 用户当前食材 [{"name": "西红柿"}, ...]，
                          传入则启用 rerank，None 则跳过

    Returns:
        list of dict: 每项包含 title, source, content, score(semantic),
                      ingredient_match_score, rerank_score, metadata
        只返回相似度 >= RAG_SCORE_THRESHOLD 的结果。
        如果 RAG 不可用、无结果、或全部低于阈值，返回空列表。
    """
    import time as _time
    from app.observability.trace import record_retrieval
    from app.observability.metrics import get_metrics_collector

    _rag_t0 = _time.time()
    threshold = get_score_threshold()
    semantic_weight, ingredient_weight = get_rerank_weights()

    logger.info(f"[RAG] query = {query}")
    logger.info(f"[RAG] top_k = {top_k}, threshold = {threshold}")
    logger.info(f"[RAG] rerank weights: semantic={semantic_weight}, ingredient={ingredient_weight}")

    store = get_vector_store()
    if store is None:
        logger.warning("[RAG] unavailable, fallback to Tavily")
        record_retrieval("rag", query=query, candidates=0, passed=0,
                        filtered=0, latency_ms=0, status="unavailable")
        get_metrics_collector().record_rag(hit=False)
        return []

    try:
        results = store.similarity_search_with_score(query, k=top_k)
    except Exception as e:
        logger.error(f"[RAG] 检索失败: {e}")
        _rag_latency = int((_time.time() - _rag_t0) * 1000)
        record_retrieval("rag", query=query, candidates=0, passed=0,
                        filtered=0, latency_ms=_rag_latency, status="failed",
                        error=str(e)[:100])
        get_metrics_collector().record_rag(hit=False)
        return []

    # 构建完整候选列表（转换 distance → similarity）
    all_candidates = []
    for doc, raw_distance in results:
        similarity = 1.0 / (1.0 + raw_distance) if raw_distance >= 0 else 0.0
        recipe = {
            "title": doc.metadata.get("title", "未知菜谱"),
            "source": "local_rag",
            "content": doc.page_content,
            "score": round(similarity, 4),
            "metadata": doc.metadata,
        }
        all_candidates.append(recipe)

    # 日志：召回的全部结果
    logger.info(f"[RAG] retrieved {len(all_candidates)} candidates:")
    for r in all_candidates:
        logger.info(f"[RAG]   - {r['title']}: semantic={r['score']}")

    # ===== 阈值过滤：保留 similarity >= threshold =====
    accepted = []
    filtered_out = []
    for r in all_candidates:
        if r["score"] >= threshold:
            accepted.append(r)
        else:
            filtered_out.append(r)

    logger.info(f"[RAG] accepted (>= {threshold}): {len(accepted)}")
    for r in accepted:
        logger.info(f"[RAG]   + {r['title']}: semantic={r['score']}")

    if filtered_out:
        logger.info(f"[RAG] filtered (< {threshold}): {len(filtered_out)}")
        for r in filtered_out:
            logger.info(f"[RAG]   x {r['title']}: semantic={r['score']}")
    else:
        logger.info(f"[RAG] filtered: 0 (all above threshold)")

    # ===== Observability: RAG Metrics =====
    _rag_latency = int((_time.time() - _rag_t0) * 1000)
    _rag_hit = len(accepted) > 0
    record_retrieval(
        "rag",
        query=query,
        candidates=len(all_candidates),
        threshold=threshold,
        passed=len(accepted),
        filtered=len(filtered_out),
        latency_ms=_rag_latency,
        status="success",
    )
    get_metrics_collector().record_rag(hit=_rag_hit)

    if not accepted:
        logger.info(f"[RAG] 所有结果低于阈值 {threshold}，返回空列表，回退到 Tavily")
        return accepted

    # ===== Ingredient-aware Rerank =====
    user_ingredient_names = []
    if user_ingredients:
        user_ingredient_names = [
            i.get("name", "") for i in user_ingredients
            if isinstance(i, dict) and i.get("name")
        ]

    if user_ingredient_names:
        logger.info(f"[RAG] user ingredients: {user_ingredient_names}")

        for r in accepted:
            recipe_ingredients = _extract_recipe_ingredients(r["content"])
            match_score, matched_names = _calculate_ingredient_match_score(
                user_ingredient_names, recipe_ingredients
            )
            rerank_score = round(
                r["score"] * semantic_weight + match_score * ingredient_weight, 4
            )
            r["ingredient_match_score"] = match_score
            r["rerank_score"] = rerank_score
            logger.info(f"[RAG]   rerank: {r['title']}")
            logger.info(f"[RAG]     recipe_ingredients: {recipe_ingredients}")
            logger.info(f"[RAG]     matched: {matched_names}")
            logger.info(f"[RAG]     semantic={r['score']}, ingredient_match={match_score}, rerank={rerank_score}")

        # 按 rerank_score 降序排序
        accepted.sort(key=lambda x: x["rerank_score"], reverse=True)

        logger.info(f"[RAG] final ranking:")
        for i, r in enumerate(accepted):
            logger.info(f"[RAG]   {i+1}. {r['title']} (rerank={r['rerank_score']})")
    else:
        # 无用户食材信息，跳过 rerank
        for r in accepted:
            r["ingredient_match_score"] = 0.0
            r["rerank_score"] = r["score"]
        logger.info(f"[RAG] 无用户食材，跳过 rerank")

    return accepted
