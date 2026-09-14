import os
import re
import json
import base64
import logging
import asyncio

import requests
from langchain_core.messages import HumanMessage, AIMessage, AIMessageChunk

from app.agents.shared import get_checkpointer
from app.agents.workflow import get_graph
from app.observability.trace import (
    start_trace, set_trace_context, finish_trace,
    clear_trace_context, get_trace_context,
)

logger = logging.getLogger(__name__)

# Agent 节点 → 前端状态阶段映射
# key: LangGraph node name
# value: (stage_key, running_message, completed_message)
STAGE_MAP = {
    "supervisor": (
        "supervisor",
        "正在规划你的烹饪需求…",
        "需求规划完成",
    ),
    "ingredient_agent": (
        "ingredient",
        "正在分析你的食材…",
        "食材分析完成",
    ),
    "preference_agent": (
        "preference",
        "正在理解你的口味偏好…",
        "偏好分析完成",
    ),
    "recipe_agent": (
        "recipe",
        "正在搜索适合你的菜谱…",
        "菜谱搜索完成",
    ),
    "nutrition_agent": (
        "nutrition",
        "正在分析营养信息…",
        "营养分析完成",
    ),
    "critic_agent": (
        "critic",
        "正在进行最终审核…",
        "审核完成",
    ),
    "final_answer": (
        "final",
        "正在整理最终推荐…",
        "推荐整理完成",
    ),
}


def _emit_status(stage: str, status: str, message: str) -> str:
    """构造 SSE status 事件"""
    data = json.dumps(
        {"stage": stage, "status": status, "message": message},
        ensure_ascii=False,
    )
    return f"event: status\ndata: {data}\n\n"


def _emit_chunk(content: str) -> str:
    """构造 SSE chunk 事件"""
    data = json.dumps({"content": content}, ensure_ascii=False)
    return f"event: chunk\ndata: {data}\n\n"


def _emit_done() -> str:
    """构造 SSE done 事件"""
    data = json.dumps({"message": "completed"}, ensure_ascii=False)
    return f"event: done\ndata: {data}\n\n"


def _emit_error(message: str) -> str:
    """构造 SSE error 事件"""
    data = json.dumps({"message": message}, ensure_ascii=False)
    return f"event: error\ndata: {data}\n\n"


async def _stream_text_simulated(text: str, chunk_size: int = 3):
    """模拟流式输出：将文本按字符组分段 yield"""
    if not text:
        return

    chunks = []
    current = ""
    for i, char in enumerate(text):
        current += char
        if char in ("\n", "。", "！", "？", "；", ":", "：", "，", "、") and len(current) >= chunk_size:
            chunks.append(current)
            current = ""
        elif len(current) >= chunk_size * 3 and i < len(text) - 1:
            chunks.append(current)
            current = ""
    if current:
        chunks.append(current)

    for chunk in chunks:
        yield chunk
        await asyncio.sleep(0.005)


def _extract_final_text(output: dict) -> str:
    """从节点输出中提取最终推荐文本"""
    if not isinstance(output, dict):
        return ""

    final_text = output.get("final_recommendation", "")
    if not final_text:
        messages = output.get("messages", [])
        if messages and len(messages) > 0:
            msg = messages[0]
            if hasattr(msg, "content"):
                final_text = msg.content
            elif isinstance(msg, dict):
                final_text = msg.get("content", "")
    return final_text


async def search_recipes(prompt: str, image: str, thread_id: str):
    """调用 Multi-Agent 工作流搜索食谱（异步流式）

    使用 graph.stream(stream_mode="debug") 获取节点级实时事件：
    - type="task" → 节点即将启动 → 发送 status: running
    - type="task_result" → 节点已完成 → 发送 status: completed

    SSE 事件类型：
    - status: Agent 工作状态变化 {stage, status, message}
    - chunk: 最终回答 Markdown 流式 {content}
    - done: 完成 {message: "completed"}
    - error: 错误 {message}
    """
    logger.info("=" * 50)
    logger.info("========== NEW TURN ==========")
    logger.info(f"user_query = {prompt}")
    logger.info(f"has_image = {bool(image and image.strip())}")
    logger.info(f"thread_id = {thread_id}")
    logger.info("=" * 50)

    # ===== Observability: 启动 Trace =====
    trace = start_trace(thread_id)
    set_trace_context(trace)

    try:
        image_data = ""

        if image and image.strip():
            response = requests.get(image, timeout=30)
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "image/jpeg")
            image_base64 = base64.b64encode(response.content).decode("utf-8")
            image_data = f"data:{content_type};base64,{image_base64}"

        message = HumanMessage(content=prompt)

        input_state = {
            "messages": [message],
            "current_user_query": prompt,
            "current_image_data": image_data,
            "current_ingredients": [],
            "current_preferences": {},
            "ingredient_operation": "",
            "effective_ingredients": [],
            "effective_preferences": {},
            "current_recipes": [],
            "current_nutrition_analysis": [],
            "current_review_result": {},
            "current_retry_count": 0,
            "final_recommendation": "",
        }

        config = {"configurable": {"thread_id": thread_id}}
        graph = get_graph()

        # 使用 debug stream mode 获取节点级实时事件
        # debug 模式在节点启动前 yield "task" 事件，在节点完成后 yield "task_result" 事件
        # 这样前端能实时看到 "正在分析食材…" 而不是等节点完成才显示
        node_run_counts = {}
        final_answer_sent = False

        for chunk in graph.stream(input_state, config, stream_mode="debug"):
            if not isinstance(chunk, dict):
                continue

            event_type = chunk.get("type", "")
            payload = chunk.get("payload", {})
            node_name = payload.get("name", "")

            # 只处理 STAGE_MAP 中定义的节点
            if node_name not in STAGE_MAP:
                continue

            stage_key, running_msg, completed_msg = STAGE_MAP[node_name]

            # ===== 节点即将启动 → 发送 status: running =====
            if event_type == "task":
                run_count = node_run_counts.get(node_name, 0) + 1
                node_run_counts[node_name] = run_count

                # 增量食材操作时，调整食材阶段文案
                if node_name == "ingredient_agent" and run_count == 1:
                    from app.agents.ingredient_context import detect_operation
                    op = detect_operation(prompt)
                    if op == "add":
                        running_msg = "正在合并新增食材…"
                    elif op == "remove":
                        running_msg = "正在更新食材清单…"
                    elif op == "replace":
                        running_msg = "正在替换食材…"
                    elif op == "update":
                        running_msg = "正在更新食材数量…"

                # 重试时在消息中注明
                if run_count > 1 and node_name != "supervisor":
                    running_msg = running_msg.rstrip("…") + f"（第{run_count}次）…"

                logger.info(f"[Status] → {stage_key} running (node={node_name}, run={run_count})")
                yield _emit_status(stage_key, "running", running_msg)

                # 让事件循环有机会立即把 SSE 发给客户端
                await asyncio.sleep(0.01)

            # ===== 节点已完成 → 发送 status: completed =====
            elif event_type == "task_result":
                logger.info(f"[Status] ✓ {stage_key} completed (node={node_name})")
                yield _emit_status(stage_key, "completed", completed_msg)

                # final_answer 完成后，提取文本并模拟流式输出
                if node_name == "final_answer" and not final_answer_sent:
                    final_answer_sent = True
                    result = payload.get("result", {})
                    final_text = _extract_final_text(result)

                    if final_text:
                        logger.info(f"[FinalAnswer] 开始流式输出，长度: {len(final_text)}")
                        async for text_chunk in _stream_text_simulated(final_text):
                            yield _emit_chunk(text_chunk)
                        logger.info("[FinalAnswer] 流式输出完成")

        # ===== 全部完成 → 发送 done =====
        logger.info("输出完成")
        finish_trace(trace, status="success")
        clear_trace_context()
        yield _emit_done()

    except Exception as e:
        logger.exception(f"\n[错误]: {str(e)}")
        finish_trace(trace, status="failed")
        clear_trace_context()
        yield _emit_error("信息检索失败，请稍后重试。")


def get_messages(thread_id: str) -> list:
    """获取指定会话的历史消息"""
    try:
        graph = get_graph()
        config = {"configurable": {"thread_id": thread_id}}
        snapshot = graph.get_state(config)
        if snapshot and snapshot.values:
            messages = snapshot.values.get("messages", [])
            result = []
            for msg in messages:
                if hasattr(msg, "content") and hasattr(msg, "type"):
                    role = "user" if msg.type == "human" else "assistant"
                    result.append({
                        "role": role,
                        "content": msg.content if isinstance(msg.content, str) else str(msg.content),
                    })
            return result
    except Exception as e:
        logger.error(f"[get_messages] 获取历史消息失败: {e}")
    return []


def clear_messages(thread_id: str) -> bool:
    """清除指定会话的历史消息"""
    try:
        graph = get_graph()
        config = {"configurable": {"thread_id": thread_id}}
        graph.update_state(
            config,
            {
                "messages": [],
                "current_user_query": "",
                "current_ingredients": [],
                "current_preferences": {},
                "ingredient_operation": "",
                "effective_ingredients": [],
                "effective_preferences": {},
                "last_effective_ingredients": [],
                "last_effective_preferences": {},
                "current_recipes": [],
                "current_nutrition_analysis": [],
                "current_review_result": {},
                "current_retry_count": 0,
                "final_recommendation": "",
            },
        )
        logger.info(f"[clear_messages] 会话 {thread_id} 状态已重置")
        return True
    except Exception as e:
        logger.error(f"[clear_messages] 清除会话失败: {e}")
        return False
