import time
import logging
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from app.agents.shared import safe_model_invoke
from app.agents.state import RecipeState

logger = logging.getLogger(__name__)

SUPERVISOR_PROMPT = """\
你是一个固定流程的多智能体系统协调者。

系统包含以下固定节点（按执行顺序）：
1. IngredientAgent - 食材识别
2. PreferenceAgent - 偏好提取
3. RecipeAgent - 菜谱搜索
4. NutritionAgent - 营养分析
5. CriticAgent - 质量审核
6. FinalAnswer - 最终回答生成

当前轮用户输入：{current_user_query}
当前轮已识别食材：{current_ingredients}
当前轮已提取偏好：{current_preferences}

当前状态：{status}
{status_detail}

请输出当前任务的"执行策略与约束"（80字以内）。
要求：
- 明确当前阶段的核心目标
- 列出 2-3 条关键约束
- 不要编造不存在的 Agent 名称
- 不要提到"语义解析Agent""推荐Agent""信息抽取Agent"等不存在的节点
- 只使用上面列出的真实节点名称
"""


def _build_semantic_context(state: RecipeState) -> str:
    """从 messages 历史构建语义上下文（仅供理解对话指代，不作为食材依据）。"""
    messages = state.get("messages", [])
    current_query = state.get("current_user_query", "")

    if len(messages) <= 1:
        return current_query

    parts = []
    recent_messages = messages[-4:] if len(messages) >= 4 else messages
    for msg in recent_messages:
        if isinstance(msg, HumanMessage):
            content = msg.content
            if isinstance(content, str):
                parts.append(f"用户: {content}")
        elif isinstance(msg, AIMessage):
            content = msg.content
            if isinstance(content, str):
                short = content[:200] + "..." if len(content) > 200 else content
                parts.append(f"助手: {short}")

    return "\n".join(parts) if parts else current_query


def supervisor_node(state: RecipeState) -> dict:
    _t0 = time.time()
    from app.observability.trace import start_span, end_span
    span = start_span("supervisor", "supervisor")
    logger.info("[Graph] Supervisor START")

    retry_count = state.get("current_retry_count", 0)
    review_result = state.get("current_review_result", {})
    current_query = state.get("current_user_query", "")
    current_ingredients = state.get("effective_ingredients", []) or state.get("current_ingredients", [])
    current_preferences = state.get("effective_preferences", {}) or state.get("current_preferences", {})

    semantic_context = _build_semantic_context(state)
    logger.info(f"[Supervisor] 语义上下文长度: {len(semantic_context)}")

    if retry_count > 0 and review_result:
        suggestions = review_result.get("suggestions", [])
        issues = review_result.get("issues", [])
        status = f"重试 #{retry_count}"
        status_detail = (
            f"上次审核未通过。问题: {issues}。\n"
            f"请基于这些问题调整策略，保持当前轮食材不变，重新搜索菜谱。"
        )
        logger.info(
            f"[Supervisor] 第{retry_count}次重试，"
            f"问题: {issues}, 建议: {suggestions}"
        )
    else:
        status = "首次执行"
        status_detail = "按标准流程执行。"

    try:
        plan = safe_model_invoke(
            "Supervisor",
            [
                SystemMessage(
                    content="你是一个任务协调者，请简洁地输出执行策略与约束，不要虚构Agent名称。"
                ),
                HumanMessage(content=SUPERVISOR_PROMPT.format(
                    current_user_query=semantic_context,
                    current_ingredients=current_ingredients,
                    current_preferences=current_preferences,
                    status=status,
                    status_detail=status_detail,
                )),
            ],
        )
        if plan:
            logger.info(f"[Supervisor] 执行策略: {plan.content[:200]}")
        else:
            logger.warning("[Supervisor] 模型调用失败，使用默认策略")
    except Exception:
        logger.exception("[Supervisor] 规划失败，使用默认策略")

    # Supervisor 不修改 current_ingredients，只做规划
    _elapsed = time.time() - _t0
    logger.info(f"[Graph] Supervisor END | {_elapsed:.1f}s")
    end_span(span, status="success")
    return {}
