import time
import logging
from langchain_core.messages import HumanMessage, SystemMessage
from app.agents.shared import model, parse_json_response, safe_model_invoke
from app.agents.state import RecipeState
from app.agents.ingredient_context import detect_operation, merge_ingredients

logger = logging.getLogger(__name__)

INGREDIENT_PROMPT_WITH_IMAGE = """\
请识别图片中的所有食材，并评估其新鲜度和大致份量。

请以JSON格式输出结果（不要输出其他内容）：
{
    "ingredients": [
        {
            "name": "食材名称",
            "amount": "数量或份量（如200g、2个）",
            "freshness": "新鲜度评估（新鲜/较新鲜/不新鲜）"
        }
    ]
}

注意：
- 如果无法确定某项，用"未知"表示
- 不要编造不存在的食材
- 只识别图片中实际存在的食材
"""

INGREDIENT_PROMPT_TEXT_ONLY = """\
请从以下用户描述中提取所有食材信息。

用户描述：{user_query}

请以JSON格式输出结果（不要输出其他内容）：
{{
    "ingredients": [
        {{
            "name": "食材名称",
            "amount": "数量或份量（如200g、2个），未知则填未知",
            "freshness": "默认新鲜"
        }}
    ]
}}

注意：
- 只提取用户在这句话中明确提到的食材
- 不要编造用户未提及的食材
- 如果用户没有提到具体食材，返回空列表
"""


def ingredient_agent_node(state: RecipeState) -> dict:
    _t0 = time.time()
    from app.observability.trace import start_span, end_span
    span = start_span("ingredient_agent", "ingredient")
    logger.info("[Graph] Ingredient START")

    image_data = state.get("current_image_data", "")
    user_query = state.get("current_user_query", "")
    last_effective = state.get("last_effective_ingredients", [])

    logger.info(f"current user query = {user_query}")
    logger.info(f"has image = {bool(image_data)}")

    try:
        if image_data:
            logger.info("[IngredientAgent] 分析当前轮图片")
            message = HumanMessage(content=[
                {"type": "image", "url": image_data},
                {"type": "text", "text": INGREDIENT_PROMPT_WITH_IMAGE},
            ])
            response = safe_model_invoke(
                "IngredientAgent",
                [
                    SystemMessage(content="你是食材识别专家，只识别图片中的食材。"),
                    message,
                ],
            )
        else:
            logger.info("[IngredientAgent] 从当前轮文本提取食材")
            response = safe_model_invoke(
                "IngredientAgent",
                [
                    SystemMessage(content="你是食材提取专家，只从用户当前这句话中提取食材。"),
                    HumanMessage(
                        content=INGREDIENT_PROMPT_TEXT_ONLY.format(
                            user_query=user_query
                        )
                    ),
                ],
            )

        if response is None:
            raise RuntimeError("IngredientAgent model invoke failed")

        result = parse_json_response(response.content)

        if result and "ingredients" in result and isinstance(result["ingredients"], list):
            ingredients = result["ingredients"]
        else:
            logger.warning("[IngredientAgent] 未能解析食材JSON，返回空列表")
            ingredients = []

        logger.info(f"current ingredients = {ingredients}")

        # ===== 增量食材上下文合并 =====
        operation = detect_operation(user_query) if not image_data else "new"

        logger.info(f"[IngredientContext] previous ingredients = {last_effective}")
        logger.info(f"[IngredientContext] current ingredients = {ingredients}")
        logger.info(f"[IngredientContext] operation = {operation}")

        effective_ingredients = merge_ingredients(ingredients, operation, last_effective)

        logger.info(f"[IngredientContext] effective ingredients = {effective_ingredients}")

        _elapsed = time.time() - _t0
        logger.info(f"[Graph] Ingredient END | {_elapsed:.1f}s")
        end_span(span, status="success")

        return {
            "current_ingredients": ingredients,
            "effective_ingredients": effective_ingredients,
            "ingredient_operation": operation,
        }

    except Exception:
        logger.exception("[IngredientAgent] 食材分析失败")
        _elapsed = time.time() - _t0
        logger.info(f"[Graph] Ingredient END | {_elapsed:.1f}s (error)")
        end_span(span, status="failed", error="ingredient agent failed")
        return {
            "current_ingredients": [],
            "effective_ingredients": list(last_effective) if last_effective else [],
            "ingredient_operation": "new",
        }
