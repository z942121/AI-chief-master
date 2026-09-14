from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages


class RecipeState(TypedDict):
    # ===== 历史会话记忆（跨轮持久化）=====
    messages: Annotated[list, add_messages]

    # ===== 上一轮快照（跨轮持久化，仅由 final_answer 更新）=====
    # 用于增量合并，不在 input_state 中重置
    last_effective_ingredients: list[dict]
    last_effective_preferences: dict

    # ===== 当前轮任务状态（每轮开始时重置）=====
    current_user_query: str
    current_image_data: str
    current_ingredients: list[dict]
    current_preferences: dict

    # 增量食材操作类型: new / add / remove / replace / update
    ingredient_operation: str
    # 本轮有效食材 = 合并历史 + 当前操作后用于检索的最终食材
    effective_ingredients: list[dict]
    # 本轮有效偏好 = 合并历史 + 当前偏好后的最终偏好
    effective_preferences: dict

    current_recipes: list[dict]
    current_nutrition_analysis: list[dict]
    current_review_result: dict
    current_retry_count: int

    final_recommendation: str
