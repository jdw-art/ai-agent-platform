from fastapi import APIRouter, Depends
from app.core.dependencies import require_admin, require_api_key

from app.api.portal.endpoints import auth, audit, management, roles, changelog

portal_router = APIRouter()

# 1. 认证 (Auth)
portal_router.include_router(auth.router, prefix="/auth", tags=["认证"])

# 5. 审计日志 (Audit)
portal_router.include_router(audit.router, prefix="/audit", tags=["审计日志"], dependencies=[Depends(require_api_key)])

# # 8.1 用户管理 (Management)
# portal_router.include_router(management.router, prefix="/management", tags=["用户管理"], dependencies=[Depends(require_api_key)])

# 8.2 角色管理 (Roles)
portal_router.include_router(roles.router, prefix="/roles", tags=["角色管理"], dependencies=[Depends(require_api_key)])

# 16. 变更日志 (Changelog)
portal_router.include_router(changelog.router, prefix="/changelog", tags=["变更日志"], dependencies=[Depends(require_api_key)])
