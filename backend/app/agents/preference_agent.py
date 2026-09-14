import json
import time
import logging
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from app.agents.shared import model, parse_json_response, safe_model_invoke
from app.agents.state import RecipeState
from app.agents.ingredient_context import merge_preferences

logger = logging.getLogger(__name__)

PREFERENCE_PROMPT = """\
请从以下对话中提取用户的饮食偏好和约束条件。

当前轮用户输入：{current_user_query}

最近对话历史（仅供理解上下文，不代表当前食材）：
{conversation_history}

请以JSON格式输出结果（不要输出其他内容）：
{{
    "diet_goal": "饮食目标（减脂/增肌/日常/无），没有则为null",
    "spicy": true或false,
    "avoid": ["忌口食材列表"],
    "max_cooking_time": 数字（分钟），没有要求则为null,
    "servings": 数字（人数），没有要求则为null,
    "meal_type": "早餐/午餐/晚餐/夜宵/无",
    "other": "其他特殊要求，没有则为null"
}}

注意：
- 综合当前轮和历史对话提取用户偏好（偏好应该持续有效）
- 只提取用户明确提到的信息
- 没有提到的字段用null
- 不要编造用户未提及的偏好
"""


def _build_history_summary(state: RecipeState) -> str:
    """构建简洁的历史对话摘要，用于提取跨轮偏好。"""
    messages = state.get("messages", [])
    if len(messages) <= 1:
        return "（无历史对话）"

    parts = []
    for msg in messages[-6:]:  # 最多取最近3轮
        if isinstance(msg, HumanMessage):
            content = msg.content
            if isinstance(content, str):
                parts.append(f"用户: {content}")
        elif isinstance(msg, AIMessage):
            pass  # 不提取助手消息中的偏好

    return "\n".join(parts) if parts else "（无历史对话）"


def preference_agent_node(state: RecipeState) -> dict:
    _t0 = time.time()
    from app.observability.trace import start_span, end_span
    span = start_span("preference_agent", "preference")
    logger.info("[Graph] Preference START")

    current_query = state.get("current_user_query", "")
    history_summary = _build_history_summary(state)
    last_effective_prefs = state.get("last_effective_preferences", {})

    try:
        response = safe_model_invoke(
            "PreferenceAgent",
            [
                SystemMessage(content="你是饮食偏好分析专家，从对话中提取用户的长期饮食偏好。"),
                HumanMessage(content=PREFERENCE_PROMPT.format(
                    current_user_query=current_query,
                    conversation_history=history_summary,
                )),
            ],
        )

        if response is None:
            raise RuntimeError("PreferenceAgent model invoke failed")

        result = parse_json_response(response.content)

        if result and isinstance(result, dict):
            preferences = result
        else:
            logger.warning("[PreferenceAgent] 未能解析偏好JSON")
            preferences = {}

        logger.info(f"[PreferenceAgent] 提取到偏好: {preferences}")

        # ===== 偏好继承合并 =====
        logger.info(f"[PreferenceContext] previous preferences = {last_effective_prefs}")
        logger.info(f"[PreferenceContext] current preferences = {preferences}")

        effective_preferences = merge_preferences(preferences, last_effective_prefs)

        logger.info(f"[PreferenceContext] effective preferences = {effective_preferences}")

        _elapsed = time.time() - _t0
        logger.info(f"[Graph] Preference END | {_elapsed:.1f}s")
        end_span(span, status="success")
        return {
            "current_preferences": preferences,
            "effective_preferences": effective_preferences,
        }

    except Exception:
        logger.exception("[PreferenceAgent] 偏好提取失败")
        _elapsed = time.time() - _t0
        logger.info(f"[Graph] Preference END | {_elapsed:.1f}s (error)")
        end_span(span, status="failed", error="preference agent failed")
        return {
            "current_preferences": {},
            "effective_preferences": dict(last_effective_prefs) if last_effective_prefs else {},
        }
