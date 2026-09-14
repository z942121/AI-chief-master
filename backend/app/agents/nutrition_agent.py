import json
import time
import logging
from langchain_core.messages import HumanMessage, SystemMessage
from app.agents.shared import model, parse_json_response, safe_model_invoke
from app.agents.state import RecipeState

logger = logging.getLogger(__name__)

NUTRITION_PROMPT = """\
请对以下候选菜谱进行营养分析。

菜谱列表：
{recipes}

当前轮食材：{ingredients}
用户饮食目标：{diet_goal}

请以JSON格式输出结果（不要输出其他内容）：
[
    {{
        "recipe_name": "菜谱名称",
        "calories": "估算热量（千卡）",
        "protein": "蛋白质含量估算",
        "fat": "脂肪含量估算",
        "carbs": "碳水化合物估算",
        "fiber": "膳食纤维估算",
        "balance_score": 0到100的整数,
        "note": "备注，如是否符合用户饮食目标"
    }}
]

重要：
- 所有数据都是基于食材及份量的粗略估算
- 在note中注明"估算值"
- 不要将估算数据包装成精确的医学/营养数据
"""


def nutrition_agent_node(state: RecipeState) -> dict:
    _t0 = time.time()
    from app.observability.trace import start_span, end_span
    span = start_span("nutrition_agent", "nutrition")
    logger.info("[Graph] Nutrition START")
    logger.info("[NutritionAgent] 开始营养分析")

    recipes = state.get("current_recipes", [])
    ingredients = state.get("effective_ingredients", []) or state.get("current_ingredients", [])
    preferences = state.get("effective_preferences", {}) or state.get("current_preferences", {})
    diet_goal = preferences.get("diet_goal", "日常")

    if not recipes:
        logger.warning("[NutritionAgent] 无菜谱可分析")
        return {"current_nutrition_analysis": []}

    try:
        response = safe_model_invoke(
            "NutritionAgent",
            [
                SystemMessage(content="你是营养分析专家。"),
                HumanMessage(content=NUTRITION_PROMPT.format(
                    recipes=json.dumps(recipes, ensure_ascii=False, indent=2),
                    ingredients=ingredients,
                    diet_goal=diet_goal,
                )),
            ],
        )

        if response is None:
            raise RuntimeError("NutritionAgent model invoke failed")

        nutrition = parse_json_response(response.content)

        if not isinstance(nutrition, list):
            nutrition = []

        logger.info(f"[NutritionAgent] 完成 {len(nutrition)} 个菜谱的营养分析")
        _elapsed = time.time() - _t0
        logger.info(f"[Graph] Nutrition END | {_elapsed:.1f}s")
        end_span(span, status="success")
        return {"current_nutrition_analysis": nutrition}

    except Exception:
        logger.exception("[NutritionAgent] 营养分析失败")
        _elapsed = time.time() - _t0
        logger.info(f"[Graph] Nutrition END | {_elapsed:.1f}s (error)")
        end_span(span, status="failed", error="nutrition agent failed")
        return {"current_nutrition_analysis": []}
