import sys
import os

# 将 agent 目录加入 sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

AGENT_DIR = os.path.join(PROJECT_ROOT, "agent")
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from fastapi import FastAPI, Header
from typing import Annotated
from app.dependencies.auth import authenticated_principal
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.app_config.settings import settings
from app.infra.logging_config import configure_backend_logging
from app.router import chat, knowledge_graph, candidate_graph, project_workbench, transcribe
from app.portal.router import router as platform_router
from app.service.chat_service import init_agent_system, shutdown_agent_system

configure_backend_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化
    from app.portal.store import recover_interrupted
    recover_interrupted()
    await init_agent_system()
    yield
    # 关闭时清理
    await shutdown_agent_system()
    from core.graph.repository import close_graph_connections
    close_graph_connections()

app = FastAPI(title="Clinical Decision Support System API", lifespan=lifespan)

@app.get('/api/identity')
def identity(authorization: Annotated[str | None, Header()] = None):
    principal=authenticated_principal(authorization)
    return dict(user_id=principal[0] if principal else settings.api_local_user_id,
                role=principal[1] if principal else 'reader')

# 配置跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(platform_router, prefix="/api")
app.include_router(transcribe.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(knowledge_graph.router, prefix="/api")
app.include_router(candidate_graph.router, prefix="/api")
app.include_router(project_workbench.router, prefix="/api")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.app_main:app", host="0.0.0.0", port=5000, reload=True)
