from typing import Optional, List

from pydantic import BaseModel, Field

# --- 数据模型 ---
class ChatRequest(BaseModel):
    message: str = Field(description="用户发送给AI Agent的消息或问题")
    image_url: Optional[str] = Field(default=None, description="可选的图片URL，用于多模态输入")
    thread_id: str = Field(description="会话线程的唯一标识符，用于维护对话上下文")