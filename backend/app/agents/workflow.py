import logging
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from app.agents.state import RecipeState
from app.agents.supervisor import supervisor_node
from app.agents.ingredient_agent import ingredient_agent_node
from app.agents.preference_agent import preference_agent_node
from app.agents.recipe_agent import recipe_agent_node
from app.agents.nutrition_agent import nutrition_agent_node
from app.agents.critic_agent import critic_agent_node, should_retry
from app.agents.final_answer import final_answer_node
from app.agents.shared import get_checkpointer

logger = logging.getLogger(__name__)

_graph = None


def _build_graph():
    builder = StateGraph(RecipeState)

    builder.add_node("supervisor", supervisor_node)
    builder.add_node("ingredient_agent", ingredient_agent_node)
    builder.add_node("preference_agent", preference_agent_node)
    builder.add_node("recipe_agent", recipe_agent_node)
    builder.add_node("nutrition_agent", nutrition_agent_node)
    builder.add_node("critic_agent", critic_agent_node)
    builder.add_node("final_answer", final_answer_node)

    # Fan-out: supervisor → (ingredient_agent, preference_agent) 并行
    # Fan-in:  (ingredient_agent, preference_agent) → recipe_agent
    # LangGraph 原生并行：同一 super-step 内执行，recipe_agent 等待两者完成
    #
    # Retry 路由（Failure-aware Conditional Routing）：
    #   critic_agent → should_retry → "recipe_agent"（菜谱问题，跳过 supervisor/ingredient/preference）
    #   critic_agent → should_retry → "nutrition_agent"（营养问题，跳过 recipe）
    #   critic_agent → should_retry → "supervisor"（规划问题，完整重跑）
    #   critic_agent → should_retry → "final_answer"（通过/达到上限/无食材）
    #   conditional edge 直达目标节点，不触发 fan-in 等待
    builder.add_edge(START, "supervisor")
    builder.add_edge("supervisor", "ingredient_agent")
    builder.add_edge("supervisor", "preference_agent")
    builder.add_edge("ingredient_agent", "recipe_agent")
    builder.add_edge("preference_agent", "recipe_agent")
    builder.add_edge("recipe_agent", "nutrition_agent")
    builder.add_edge("nutrition_agent", "critic_agent")
    builder.add_conditional_edges("critic_agent", should_retry)
    builder.add_edge("final_answer", END)

    return builder.compile(checkpointer=get_checkpointer())


def get_graph():
    global _graph
    if _graph is None:
        logger.info("[Workflow] 初始化 Multi-Agent 工作流")
        _graph = _build_graph()
    return _graph
