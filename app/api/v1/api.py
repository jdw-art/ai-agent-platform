from fastapi import APIRouter, Depends
from app.core.dependencies import require_api_key, verify_v1_api_access
from app.api.v1.endpoints import chat

# API Key + `verify_v1_api_access`（`chatbi.public_router` 单独挂在下方，不经此依赖）
v1_secured = APIRouter(dependencies=[Depends(require_api_key), Depends(verify_v1_api_access)])

v1_secured.include_router(chat.router, prefix="/chat", tags=["V1 智能体对话"])

v1_router = APIRouter()
v1_router.include_router(v1_secured)