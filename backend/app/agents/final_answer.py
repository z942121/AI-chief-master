import json
import time
import logging
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from app.agents.shared import model, safe_model_invoke
from app.agents.state import RecipeState

logger = logging.getLogger(__name__)

FINAL_PROMPT = """\
请基于以下分析结果，为用户生成一份结构清晰、友好的菜谱推荐报告。

用户当前轮输入：{user_query}
当前轮可用食材：{ingredients}
用户饮食偏好：{preferences}

推荐菜谱：
{recipes}

营养分析：
{nutrition}

审核结果：{review_result}
审核轮次：{retry_count}

要求：
1. 使用Markdown格式输出
2. 推荐最佳菜谱，包含综合评分、推荐理由、制作步骤、营养信息、参考来源
3. 使用表格展示评分信息
4. 语言亲切、简洁
5. 只基于当前轮的食材和结果生成，不要引用历史轮的食材作为当前库存
6. 如果审核未通过或达到重试上限，请明确告知用户结果可能存在不确定性
7. 营养数据需标注"估算值"

输出格式参考：
# 今日推荐

## 推荐菜谱名称

**综合评分：XX/100**

| 指标 | 评分 |
|---|---:|
| 营养 | XX |
| 难度 | XX |
| 食材匹配 | XX |

### 推荐理由
...

### 制作步骤
1. ...

### 营养信息（估算值）
...

### 参考来源
...
"""

FOLLOWUP_PROMPT = """\
用户当前轮的问题：{user_query}

最近的对话历史（供理解上下文参考，不是当前食材清单）：
{conversation_history}

用户似乎在追问上一轮提到的内容。请结合对话上下文，理解用户在问什么，
并给出详细、有帮助的回答。

注意：
- 这是一个追问/跟进问题，不是新一轮的食材推荐
- 请围绕用户的具体问题给出详细解答
- 可以引用上一轮提到的菜谱名称进行展开说明
- 使用Markdown格式
- 语言亲切自然
"""


def _build_recent_context(state: RecipeState, max_turns: int = 2) -> str:
    """构建最近几轮的对话上下文，用于追问场景的语义理解。"""
    messages = state.get("messages", [])
    if not messages:
        return "（无对话历史）"

    parts = []
    count = 0
    for msg in reversed(messages):
        if count >= max_turns * 2:
            break
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        if isinstance(msg, HumanMessage):
            parts.insert(0, f"用户: {content}")
            count += 1
        elif isinstance(msg, AIMessage):
            # 助手消息截取前500字
            short = content[:500] + "..." if len(content) > 500 else content
            parts.insert(0, f"助手: {short}")
            count += 1

    return "\n\n".join(parts)


def final_answer_node(state: RecipeState) -> dict:
    _t0 = time.time()
    from app.observability.trace import start_span, end_span
    span = start_span("final_answer", "final")
    logger.info("=" * 50)
    logger.info("========== FINAL ==========")

    user_query = state.get("current_user_query", "")
    ingredients = state.get("effective_ingredients", []) or state.get("current_ingredients", [])
    preferences = state.get("effective_preferences", {}) or state.get("current_preferences", {})
    recipes = state.get("current_recipes", [])
    nutrition = state.get("current_nutrition_analysis", [])
    review_result = state.get("current_review_result", {})
    retry_count = state.get("current_retry_count", 0)

    logger.info(f"effective ingredients = {ingredients}")
    logger.info(f"current recipes count = {len(recipes)}")

    try:
        # 场景1：当前轮有菜谱，正常生成推荐报告
        if recipes:
            response = safe_model_invoke(
                "FinalAnswer",
                [
                    SystemMessage(content="你是私人厨师推荐专家，请用中文生成友好的菜谱推荐报告。只基于当前轮的食材。"),
                    HumanMessage(content=FINAL_PROMPT.format(
                        user_query=user_query,
                        ingredients=json.dumps(ingredients, ensure_ascii=False, indent=2),
                        preferences=json.dumps(preferences, ensure_ascii=False, indent=2),
                        recipes=json.dumps(recipes, ensure_ascii=False, indent=2),
                        nutrition=json.dumps(nutrition, ensure_ascii=False, indent=2),
                        review_result=json.dumps(review_result, ensure_ascii=False, indent=2),
                        retry_count=retry_count,
                    )),
                ],
            )
            if response is None:
                raise RuntimeError("FinalAnswer model invoke failed")
            final_text = response.content
            logger.info("[FinalAnswer] 正常推荐模式")

        # 场景2：当前轮无食材/菜谱，判断是否为追问，用对话历史语义理解回答
        else:
            logger.info("[FinalAnswer] 无当前轮食材，尝试用对话上下文理解追问")
            context = _build_recent_context(state, max_turns=2)
            response = safe_model_invoke(
                "FinalAnswer",
                [
                    SystemMessage(
                        content="你是私人厨师助手。用户在追问之前讨论过的内容，"
                                "请结合上下文给出详细有帮助的回答。注意：历史对话中提到的食材"
                                "是之前讨论的内容，不要当成用户现在的库存。"
                    ),
                    HumanMessage(content=FOLLOWUP_PROMPT.format(
                        user_query=user_query,
                        conversation_history=context,
                    )),
                ],
            )
            if response is None:
                raise RuntimeError("FinalAnswer model invoke failed")
            final_text = response.content
            logger.info("[FinalAnswer] 追问回答模式")

        if not final_text:
            final_text = "抱歉，暂时无法生成推荐，请稍后重试。"

        logger.info(f"[FinalAnswer] 生成完成，长度: {len(final_text)}")
        logger.info("========== FINAL DONE ==========")
        logger.info("=" * 50)
        _elapsed = time.time() - _t0
        end_span(span, status="success")

        return {
            "final_recommendation": final_text,
            "messages": [AIMessage(content=final_text)],
            "last_effective_ingredients": ingredients,
            "last_effective_preferences": preferences,
        }

    except Exception:
        logger.exception("[FinalAnswer] 生成失败")
        _elapsed = time.time() - _t0
        end_span(span, status="failed", error="final answer failed")
        error_msg = "抱歉，菜谱推荐生成失败，请稍后重试。"
        return {
            "final_recommendation": error_msg,
            "messages": [AIMessage(content=error_msg)],
            "last_effective_ingredients": ingredients,
            "last_effective_preferences": preferences,
        }
