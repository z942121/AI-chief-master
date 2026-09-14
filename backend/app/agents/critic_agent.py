import json
import time
import logging
from langchain_core.messages import HumanMessage, SystemMessage
from app.agents.shared import model, parse_json_response, MAX_RETRY, safe_model_invoke
from app.agents.state import RecipeState

logger = logging.getLogger(__name__)

CRITIC_PROMPT = """\
请审核以下菜谱推荐结果，确保满足用户需求。

用户原始需求：{user_query}
当前轮可用食材：{ingredients}
用户偏好：{preferences}

推荐菜谱：
{recipes}

营养分析：
{nutrition}

审核要点：
1. 菜谱是否围绕当前轮的食材展开
2. 是否违反用户忌口（avoid列表）
3. 是否满足用户烹饪时间要求（max_cooking_time）
4. 菜谱难度是否合理
5. 营养分析是否存在明显问题
6. 是否存在明显的模型幻觉（编造不存在的菜谱或食材）
7. 是否满足用户当前轮的需求

请以JSON格式输出审核结果（不要输出其他内容）：
{{
    "passed": true或false,
    "score": 0到100的整数,
    "retry_target": "失败时需要重试的目标节点",
    "issues": ["发现的问题列表"],
    "retry_constraints": {{
        "must_use_ingredients": ["必须使用的食材"],
        "forbidden_ingredients": ["禁止使用的食材"],
        "search_keywords": ["补充搜索关键词，用于重试时精确搜索"]
    }},
    "suggestions": ["改进建议的自然语言描述，仅供参考，不用于搜索"]
}}

判断标准：
- score >= 70 视为通过
- 如果菜谱明显不符合当前轮食材（使用了大量非当前食材），直接判定不通过
- 如果违反用户忌口，直接判定不通过
- retry_constraints 必须是结构化数据，search_keywords 只能是 1-2 个关键词短语
- passed=true 时 retry_constraints 可以为空对象，retry_target 为空字符串

retry_target 分类规则（passed=false 时必须填写）：
- "recipe": 菜谱质量问题。包括：审核要点1(食材不匹配)、2(违反忌口)、3(时间超标)、4(难度不合理)、6(模型幻觉)，以及有食材但搜索无结果的情况。
- "nutrition": 营养分析问题。包括：审核要点5(营养数据缺失或不合理)。
- "planning": 需求理解偏差。包括：审核要点7(用户需求未被正确理解)，以及食材/偏好提取明显遗漏的情况。
"""


def critic_agent_node(state: RecipeState) -> dict:
    _t0 = time.time()
    from app.observability.trace import start_span, end_span, record_critic, record_retry
    span = start_span("critic_agent", "critic")
    logger.info("[Graph] Critic START")

    recipes = state.get("current_recipes", [])
    ingredients = state.get("effective_ingredients", []) or state.get("current_ingredients", [])
    preferences = state.get("effective_preferences", {}) or state.get("current_preferences", {})
    nutrition = state.get("current_nutrition_analysis", [])
    user_query = state.get("current_user_query", "")
    retry_count = state.get("current_retry_count", 0)

    logger.info(f"effective ingredients = {ingredients}")

    if not recipes:
        logger.warning("[CriticAgent] 无菜谱可审核")
        ingredient_names = [i.get("name", "") for i in ingredients if i.get("name")]
        return {
            "current_review_result": {
                "passed": False,
                "score": 0,
                "retry_target": "recipe",
                "issues": ["未获取到任何菜谱"],
                "retry_constraints": {
                    "must_use_ingredients": ingredient_names,
                    "forbidden_ingredients": [],
                    "search_keywords": ["家常做法"],
                },
                "suggestions": ["请重新搜索菜谱"],
            },
            "current_retry_count": retry_count + 1,
        }

    try:
        response = safe_model_invoke(
            "CriticAgent",
            [
                SystemMessage(content="你是菜谱推荐审核专家。只基于当前轮的食材和偏好进行审核。"),
                HumanMessage(content=CRITIC_PROMPT.format(
                    user_query=user_query,
                    ingredients=json.dumps(ingredients, ensure_ascii=False),
                    preferences=json.dumps(preferences, ensure_ascii=False),
                    recipes=json.dumps(recipes, ensure_ascii=False, indent=2),
                    nutrition=json.dumps(nutrition, ensure_ascii=False, indent=2),
                )),
            ],
        )

        if response is None:
            raise RuntimeError("CriticAgent model invoke failed")

        review = parse_json_response(response.content)

        if not review or not isinstance(review, dict):
            review = {
                "passed": True,
                "score": 75,
                "retry_target": "",
                "issues": [],
                "retry_constraints": {},
                "suggestions": [],
            }

        if review.get("score", 0) >= 70:
            review["passed"] = True

        # 确保 retry_constraints 字段存在
        if "retry_constraints" not in review or not isinstance(review["retry_constraints"], dict):
            review["retry_constraints"] = {}

        # 确保 retry_target 字段存在且合法
        valid_targets = {"recipe", "nutrition", "planning", ""}
        raw_target = review.get("retry_target", "recipe")
        if raw_target not in valid_targets:
            logger.warning(f"[CriticAgent] 非法 retry_target='{raw_target}'，降级为 'recipe'")
            raw_target = "recipe"
        if review.get("passed", False):
            raw_target = ""
        review["retry_target"] = raw_target

        logger.info(f"passed = {review.get('passed')}")
        logger.info(f"score = {review.get('score')}")
        logger.info(f"retry_target = {review.get('retry_target', '')}")
        logger.info(f"issues = {review.get('issues', [])}")
        logger.info(f"retry_constraints = {review.get('retry_constraints', {})}")

        # ===== Observability: 记录 Critic 结果 =====
        record_critic(
            score=review.get("score", 0),
            passed=review.get("passed", False),
            retry_target=review.get("retry_target", ""),
            issues=review.get("issues", []),
            retry_count=retry_count + 1,
        )

        # 如果未通过且需要 Retry，记录 Retry
        if not review.get("passed") and review.get("retry_target"):
            record_retry(
                target=review["retry_target"],
                reason="; ".join(review.get("issues", []))[:200],
            )

        _elapsed = time.time() - _t0
        logger.info(f"[Graph] Critic END | {_elapsed:.1f}s")
        end_span(span, status="success")

        return {
            "current_review_result": review,
            "current_retry_count": retry_count + 1,
        }

    except Exception:
        logger.exception("[CriticAgent] 审核失败")
        _elapsed = time.time() - _t0
        logger.info(f"[Graph] Critic END | {_elapsed:.1f}s (error)")
        end_span(span, status="failed", error="critic agent failed")
        return {
                "current_review_result": {
                    "passed": True,
                    "score": 60,
                    "retry_target": "",
                    "issues": ["审核过程出错，使用默认通过"],
                    "retry_constraints": {},
                    "suggestions": [],
                },
                "current_retry_count": retry_count + 1,
            }


def should_retry(state: RecipeState) -> str:
    """Failure-aware Conditional Routing。

    路由规则：
    - passed=True 或 retry_count >= MAX_RETRY → final_answer
    - current_ingredients 为空 → final_answer（无食材，重新搜索无意义）
    - retry_target = "nutrition" → nutrition_agent（只重跑营养分析）
    - retry_target = "planning" → supervisor（完整重跑 Supervisor → Ingredient + Preference → Recipe → Nutrition）
    - retry_target = "recipe" 或未知值 → recipe_agent（局部重试 Recipe → Nutrition）
    """
    review = state.get("current_review_result", {})
    retry_count = state.get("current_retry_count", 0)

    if review.get("passed", False) or retry_count >= MAX_RETRY:
        if retry_count >= MAX_RETRY and not review.get("passed", False):
            logger.warning(
                f"[CriticAgent] 达到最大重试次数({MAX_RETRY})，"
                f"强制结束并标注不确定性"
            )
        return "final_answer"

    ingredients = state.get("effective_ingredients", []) or state.get("current_ingredients", [])
    if not ingredients:
        logger.warning("[CriticAgent] 无有效食材，跳过 Retry，直接进入 FinalAnswer")
        return "final_answer"

    retry_target = review.get("retry_target", "recipe")

    if retry_target == "nutrition":
        logger.info(f"[CriticAgent] Retry → nutrition_agent (retry_count={retry_count})")
        return "nutrition_agent"

    if retry_target == "planning":
        logger.info(f"[CriticAgent] Retry → supervisor (planning, retry_count={retry_count})")
        return "supervisor"

    # recipe 或未知值统一降级到 recipe
    if retry_target not in ("recipe", "nutrition", "planning"):
        logger.warning(f"[CriticAgent] 未知 retry_target='{retry_target}'，降级为 recipe_agent")
    else:
        logger.info(f"[CriticAgent] Retry → recipe_agent (retry_count={retry_count})")
    return "recipe_agent"
