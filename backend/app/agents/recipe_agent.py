import json
import time
import logging
from langchain_core.messages import HumanMessage, SystemMessage
from app.agents.shared import model, web_search, parse_json_response, safe_model_invoke
from app.agents.state import RecipeState

logger = logging.getLogger(__name__)

RECIPE_PARSE_PROMPT = """\
以下是通过网络搜索和本地知识库获取的菜谱相关信息：

{search_results}

当前轮可用食材：{ingredients}
用户饮食偏好：{preferences}

请基于以上搜索结果，整理出 1-3 个可行的菜谱推荐。
请以JSON格式输出结果（不要输出其他内容）：
[
    {{
        "name": "菜谱名称",
        "ingredients_needed": ["所需食材列表"],
        "steps": ["制作步骤1", "制作步骤2"],
        "source": "来源链接或来源说明",
        "difficulty": "简单/中等/困难",
        "cooking_time": "预估烹饪时间（分钟）",
        "description": "简短描述"
    }}
]

注意：
- 优先使用搜索到的真实菜谱信息
- 菜谱必须围绕当前轮提供的食材来推荐
- 如果搜索结果不足，可以基于食材推荐常见做法，但要标注source为"模型推荐"
- 尽量保留搜索结果的原始来源
"""


def _build_search_query(ingredients: list[dict], preferences: dict,
                        retry_constraints: dict, retry_count: int) -> tuple[str, str]:
    """构建 Tavily 搜索查询。只使用结构化字段，绝不拼接自然语言。

    Returns:
        (base_query, final_query) 用于日志输出
    """
    ingredient_names = [i.get("name", "") for i in ingredients if i.get("name")]
    base_query = " ".join(ingredient_names) + " 菜谱 做法"

    # 从 preferences 补充结构化字段
    meal_type = preferences.get("meal_type")
    if meal_type and meal_type not in (None, "无", ""):
        base_query += f" {meal_type}"

    final_query = base_query

    # 重试时只从 retry_constraints.search_keywords 追加关键词
    if retry_count > 0 and retry_constraints:
        search_keywords = retry_constraints.get("search_keywords", [])
        if search_keywords and isinstance(search_keywords, list):
            extra = " ".join(search_keywords[:2])
            if extra:
                final_query = base_query + " " + extra

    return base_query, final_query


def _build_rag_query(ingredients: list[dict], preferences: dict,
                     retry_constraints: dict, retry_count: int) -> str:
    """构建 RAG 查询。只使用结构化字段。"""
    ingredient_names = [i.get("name", "") for i in ingredients if i.get("name")]
    query_parts = ingredient_names[:]

    # 加入餐类型
    meal_type = preferences.get("meal_type")
    if meal_type and meal_type not in (None, "无", ""):
        query_parts.append(meal_type)

    # 重试时加入 search_keywords
    if retry_count > 0 and retry_constraints:
        search_keywords = retry_constraints.get("search_keywords", [])
        if search_keywords and isinstance(search_keywords, list):
            query_parts.extend(search_keywords[:2])

    return " ".join(query_parts)


def _merge_recipe_results(rag_results: list[dict], tavily_results: list[dict]) -> list[dict]:
    """融合 RAG 和 Tavily 结果，按标题去重，优先保留 RAG。

    Args:
        rag_results: RAG 检索结果 [{"title":..., "source":"local_rag", ...}]
        tavily_results: Tavily 搜索结果 [{"title":..., "source":"tavily", ...}]

    Returns:
        融合后的结果列表，最多 8 个
    """
    merged = {}
    seen_titles = set()

    # 优先加入 RAG 结果
    for item in rag_results:
        title = item.get("title", "").strip()
        if not title:
            continue
        key = title.replace(" ", "").lower()
        if key not in seen_titles:
            seen_titles.add(key)
            merged[key] = item

    # 再加入 Tavily 结果（去重）
    for item in tavily_results:
        title = item.get("title", "").strip()
        if not title:
            continue
        key = title.replace(" ", "").lower()
        if key not in seen_titles:
            seen_titles.add(key)
            merged[key] = item

    result = list(merged.values())[:8]
    return result


def _rag_results_to_search_format(rag_results: list[dict]) -> list[dict]:
    """将 RAG 结果转换为与 Tavily 兼容的格式，供 LLM 整理。"""
    formatted = []
    for item in rag_results:
        formatted.append({
            "title": item.get("title", ""),
            "content": item.get("content", ""),
            "source": "local_rag",
            "url": "",
            "score": item.get("score", 0),
        })
    return formatted


def recipe_agent_node(state: RecipeState) -> dict:
    _t0 = time.time()
    from app.observability.trace import start_span, end_span
    span = start_span("recipe_agent", "recipe")
    logger.info("[Graph] Recipe START")

    ingredients = state.get("effective_ingredients", []) or state.get("current_ingredients", [])
    preferences = state.get("effective_preferences", {}) or state.get("current_preferences", {})
    retry_count = state.get("current_retry_count", 0)
    review_result = state.get("current_review_result", {})

    retry_constraints = review_result.get("retry_constraints", {}) if review_result else {}
    if not isinstance(retry_constraints, dict):
        retry_constraints = {}

    logger.info(f"effective ingredients = {ingredients}")

    if not ingredients:
        logger.warning("[RecipeAgent] 无有效食材，跳过搜索")
        return {"current_recipes": []}

    # 构建查询
    base_query, final_tavily_query = _build_search_query(
        ingredients, preferences, retry_constraints, retry_count
    )
    rag_query = _build_rag_query(
        ingredients, preferences, retry_constraints, retry_count
    )

    logger.info(f"base query = {base_query}")
    logger.info(f"retry constraints = {retry_constraints}")
    logger.info(f"retry count = {retry_count}")
    logger.info(f"final tavily query = {final_tavily_query}")
    logger.info(f"RAG query = {rag_query}")

    # ===== 双路检索：RAG + Tavily =====
    rag_results = []
    try:
        from app.rag.retriever import search_recipes
        rag_results = search_recipes(rag_query, top_k=5, user_ingredients=ingredients)
        logger.info(f"[RecipeAgent] RAG results = {len(rag_results)}")
        for r in rag_results:
            logger.info(f"  [RAG] {r['title']} (score={r['score']})")
    except Exception as e:
        logger.error(f"[RecipeAgent] RAG 检索异常: {e}")
        logger.warning("[RecipeAgent] RAG unavailable, fallback to Tavily only")
        rag_results = []

    # Tavily 搜索
    tavily_results = []
    _tavily_t0 = time.time()
    try:
        from app.observability.trace import record_retrieval
        from app.observability.metrics import get_metrics_collector

        results = web_search.invoke({"query": final_tavily_query})
        tavily_raw = results.get("results", [])
        tavily_results = [
            {
                "title": r.get("title", ""),
                "content": r.get("content", ""),
                "source": "tavily",
                "url": r.get("url", ""),
            }
            for r in tavily_raw
        ]
        _tavily_latency = int((time.time() - _tavily_t0) * 1000)
        logger.info(f"[RecipeAgent] Tavily results = {len(tavily_results)}")
        record_retrieval(
            "tavily",
            query=final_tavily_query,
            results=len(tavily_results),
            latency_ms=_tavily_latency,
            status="success",
        )
        get_metrics_collector().record_tavily(success=True)
    except Exception as e:
        _tavily_latency = int((time.time() - _tavily_t0) * 1000)
        logger.exception("[RecipeAgent] Tavily搜索失败")
        record_retrieval(
            "tavily",
            query=final_tavily_query,
            results=0,
            latency_ms=_tavily_latency,
            status="failed",
            error=str(e)[:100],
        )
        get_metrics_collector().record_tavily(success=False)
        tavily_results = []

    # ===== 检索 Pipeline: Dedup → RRF → Ingredient Rerank → Top-K =====
    from app.rag.retrieval_pipeline import run_retrieval_pipeline
    merged = run_retrieval_pipeline(
        rag_results=_rag_results_to_search_format(rag_results),
        tavily_results=tavily_results,
        user_ingredients=ingredients,
        top_k=3,
    )
    logger.info(f"[RecipeAgent] pipeline results = {len(merged)}")
    for m in merged:
        logger.info(f"  [{m.get('source','?')}] {m.get('title','')} (final={m.get('rerank_score', 0)})")

    if not merged:
        logger.warning("[RecipeAgent] 双路检索均无结果")
        return {"current_recipes": []}

    # 交给 LLM 整理成结构化菜谱
    try:
        response = safe_model_invoke(
            "RecipeAgent",
            [
                SystemMessage(content="你是菜谱整理专家。只基于当前轮的食材来推荐菜谱。"),
                HumanMessage(content=RECIPE_PARSE_PROMPT.format(
                    search_results=json.dumps(merged, ensure_ascii=False, indent=2),
                    ingredients=ingredients,
                    preferences=preferences,
                )),
            ],
        )

        if response is None:
            raise RuntimeError("RecipeAgent model invoke failed")

        recipes = parse_json_response(response.content)

        if not isinstance(recipes, list):
            recipes = recipes.get("recipes", []) if isinstance(recipes, dict) else []

        logger.info(f"[RecipeAgent] 整理出 {len(recipes)} 个菜谱")
        _elapsed = time.time() - _t0
        logger.info(f"[Graph] Recipe END | {_elapsed:.1f}s")
        end_span(span, status="success")
        return {"current_recipes": recipes}

    except Exception:
        logger.exception("[RecipeAgent] 菜谱整理失败")
        _elapsed = time.time() - _t0
        logger.info(f"[Graph] Recipe END | {_elapsed:.1f}s (error)")
        end_span(span, status="failed", error="recipe agent failed")
        return {"current_recipes": []}
