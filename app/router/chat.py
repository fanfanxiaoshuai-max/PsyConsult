import re
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse

from app.app_config.settings import settings
from app.schemas.chat import ChatRequest
from app.service.chat_service import stream_chat

router = APIRouter()
from app.dependencies.auth import require_chat_identity

@router.post("/chat")
async def chat_endpoint(
    request: ChatRequest,
    user_id: Annotated[str, Depends(require_chat_identity)],
):
    """
    处理多智能体聊天请求，并使用 SSE (Server-Sent Events) 返回流式响应。
    如果命中 L1 语义缓存，将直接返回缓存结果。
    否则进入 Agent 图编排流程。
    """
    return StreamingResponse(
        stream_chat(request.query, user_id, request.session_id),
        media_type="text/event-stream"
    )
