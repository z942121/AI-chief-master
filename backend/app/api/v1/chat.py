from fastapi import APIRouter
from app.models.schemas import ChatRequest
from fastapi.responses import StreamingResponse
from app.agents.personal_chief import search_recipes, get_messages, clear_messages
from app.services.session_service import (
    get_all_sessions,
    save_session,
    update_session_title,
    delete_session
)
from app.observability.metrics import get_metrics_collector
from uuid import uuid4


router = APIRouter()


@router.post("/chat/stream")
async def chat_endpoint(request: ChatRequest):
    """流式对话

    SSE 事件类型：
    - status: Agent 工作状态变化 {stage, status, message}
    - chunk: 最终回答 Markdown 流式 {content}
    - done: 完成 {message: "completed"}
    - error: 错误 {message}
    """
    request_id = str(uuid4())
    return StreamingResponse(
        search_recipes(request.message, request.image_url, request.thread_id),
        media_type="text/event-stream",
        headers={
            "X-Request-ID": request_id,
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/chat/messages")
async def get_chat_messages(thread_id: str):
    """获取历史消息"""
    messages = get_messages(thread_id)
    return {"messages": messages}


# ========== 会话列表管理 ==========

@router.get("/chat/sessions")
async def list_sessions():
    """获取所有会话列表"""
    sessions = get_all_sessions()
    return {"sessions": sessions}


@router.post("/chat/sessions")
async def create_or_update_session(thread_id: str, title: str = "新对话"):
    """保存会话到列表"""
    session = save_session(thread_id, title)
    return {"session": session}


@router.put("/chat/sessions/{thread_id}")
async def update_session(thread_id: str, title: str):
    """更新会话标题"""
    session = update_session_title(thread_id, title)
    if session:
        return {"session": session}
    return {"error": "会话不存在"}, 404


@router.delete("/chat/sessions/{thread_id}")
async def remove_session(thread_id: str):
    """删除会话"""
    # 先删除后端的聊天记录
    clear_messages(thread_id)
    # 再删除会话记录
    success = delete_session(thread_id)
    return {"success": success}


# ========== Observability Metrics ==========

@router.get("/metrics")
async def get_metrics():
    """获取 Agent Observability 指标"""
    mc = get_metrics_collector()
    return mc.to_dict()
