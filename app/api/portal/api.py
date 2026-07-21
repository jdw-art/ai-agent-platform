from fastapi import APIRouter, Depends
from app.core.dependencies import require_admin, require_api_key

from app.api.portal.endpoints import auth, audit

portal_router = APIRouter()

# 1. 认证 (Auth)
portal_router.include_router(auth.router, prefix="/auth", tags=["认证"])

# 5. 审计日志 (Audit)
portal_router.include_router(audit.router, prefix="/audit", tags=["审计日志"], dependencies=[Depends(require_api_key)])
