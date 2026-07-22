"""
用户管理
"""

from fastapi import APIRouter, Depends, Query, HTTPException, status, Request
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func, desc
from sqlalchemy.orm import selectinload
from app.core.dependencies import require_admin, require_api_key, require_permission, require_permission
from app.core.orm import get_db_session
from app.services.auth_service import AuthService
from app.models.user import User
from app.schemas.permission import UserPermissionsResponse, PermissionUpdate
from app.services.permission_service import PermissionService
from app.models.permission import ResourcePermission, UserRoleRelation
from app.services.sso_user import LaplacePortalApiClient
import json
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

class CreateUserRequest(BaseModel):
    user_name: str
    real_name: Optional[str] = None
    role: str = "user"  # "admin" or "user"
    dept_code: Optional[str] = None
    org_path: Optional[str] = None
    extra_data: Optional[str] = None
    allowed_resources: Optional[list] = []
    role_ids: Optional[List[int]] = [] # Business Roles
    remark: Optional[str] = None

class SsoSyncRequest(BaseModel):
    usernames: List[str]
    role: str = "user"
    role_ids: Optional[List[int]] = []

@router.get("/sso-users")
async def get_sso_users(
    admin: dict = Depends(require_permission("element", "element:user:edit")),
    db: AsyncSession = Depends(get_db_session)
):
    """
    从 SSO 获取用户，并标记已存在于本地数据库中的用户。
    """
    from app.services.config_service import ConfigService
    if await ConfigService.get("yovole_sso_enabled") != "true":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="SSO 统一认证登录已被禁用"
        )
    try:
        # 1. Get all users from SSO
        sso_users = LaplacePortalApiClient.get_all_users()
        
        # 2. Get all existing usernames from local DB
        stmt = select(User.user_name)
        result = await db.execute(stmt)
        existing_usernames = set(result.scalars().all())
        
        # 3. Mark synced status
        items = []
        for user in sso_users:
            items.append({
                **user,
                "is_synced": user["code"] in existing_usernames
            })
            
        return {"items": items}
    except Exception as e:
        logger.error(f"Failed to fetch SSO users: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/sso-sync")
async def sync_sso_users(
    request: SsoSyncRequest,
    admin: dict = Depends(require_permission("element", "element:user:edit")),
    db: AsyncSession = Depends(get_db_session)
):
    """
    通过角色分配将选定的用户从 SSO 批量同步到本地数据库。
    """
    from app.services.config_service import ConfigService
    if await ConfigService.get("yovole_sso_enabled") != "true":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="SSO 统一认证登录已被禁用"
        )
    if not request.usernames:
        return {"message": "No users selected"}
        
    try:
        # 1. Get SSO data to fetch real names/emails
        sso_users = LaplacePortalApiClient.get_all_users()
        sso_map = {u["code"]: u for u in sso_users}
        
        # 2. Filter out already existing users
        stmt = select(User.user_name).where(User.user_name.in_(request.usernames))
        existing = set((await db.execute(stmt)).scalars().all())
        
        to_sync = [u for u in request.usernames if u not in existing]
        
        count = 0
        service = PermissionService(db)
        
        for username in to_sync:
            sso_data = sso_map.get(username)
            if not sso_data:
                continue
                
            # Create user and generate API Key
            await AuthService.generate_api_key(
                user_name=username,
                real_name=sso_data.get("name"),
                role=request.role,
                remark=f"SSO Sync: {sso_data.get('department')} / {sso_data.get('position')}",
                db=db
            )
            
            # Find newly created user
            res = await db.execute(select(User).where(User.user_name == username))
            new_user = res.scalar_one()
            
            # Assign Business Roles
            if request.role_ids:
                await service.update_user_roles(new_user.id, request.role_ids)
                
            count += 1
            
        return {"message": f"Successfully synced {count} users", "count": count}
    except Exception as e:
        logger.error(f"SSO Sync Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class UpdateUserRequest(BaseModel):
    real_name: Optional[str] = None
    role: Optional[str] = None
    dept_code: Optional[str] = None
    org_path: Optional[str] = None
    extra_data: Optional[str] = None
    allowed_resources: Optional[list] = None
    role_ids: Optional[List[int]] = None # Business Roles
    remark: Optional[str] = None

class UpdateStatusRequest(BaseModel):
    status: int  # 1=enabled, 0=disabled

@router.get("/users/{user_id}/permissions", response_model=UserPermissionsResponse)
async def get_user_permissions(
    user_id: int,
    admin: dict = Depends(require_permission("element", "element:user:edit")),
    db: AsyncSession = Depends(get_db_session)
):
    """
    获取用户的所有权限。仅限管理员
    """
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    service = PermissionService(db)
    return await service.get_user_permissions(user_id)

@router.put("/users/{user_id}/permissions")
async def update_user_permissions(
    user_id: int,
    permissions: PermissionUpdate,
    admin: dict = Depends(require_permission("element", "element:user:edit")),
    db: AsyncSession = Depends(get_db_session)
):
    """
    更新用户权限。仅限管理员
    """
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    service = PermissionService(db)
    await service.update_user_permissions(user_id, permissions)
    return {"message": "Permissions updated successfully"}

@router.get("/users")
async def list_users(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=1000),
    search: Optional[str] = None,
    role: Optional[str] = None,
    status_filter: Optional[int] = Query(None, alias="status"),
    admin: dict = Depends(require_permission("element", "element:user:edit")),
    db: AsyncSession = Depends(get_db_session)
):
    """
    获取用户列表。仅限管理员
    """
    stmt = select(User).order_by(desc(User.created_at))
    
    if search:
        stmt = stmt.where((User.user_name.like(f"%{search}%")) | (User.real_name.like(f"%{search}%")))
    if role and role in ["admin", "user"]:
        stmt = stmt.where(User.role == role)
    if status_filter is not None:
        stmt = stmt.where(User.status == status_filter)
        
    # Count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar()
    
    # Page
    stmt = stmt.offset((page - 1) * size).limit(size)
    rows = (await db.execute(stmt)).scalars().all()
    
    items = []
    for row in rows:
        role_ids = [r.id for r in row.roles] if row.roles else []
        role_names = [r.name for r in row.roles] if row.roles else []
        
        items.append({
            "id": row.id,
            "user_name": row.user_name,
            "real_name": row.real_name,
            "role": row.role,
            "dept_code": row.dept_code,
            "org_path": row.org_path,
            "extra_data": row.extra_data,
            "role_ids": role_ids,
            "role_names": role_names,
            "remark": row.remark,
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "allowed_resources": []
        })

    return {
        "total": total,
        "page": page,
        "size": size,
        "items": items
    }

@router.post("/users")
async def create_user(
    request: CreateUserRequest,
    admin: dict = Depends(require_permission("element", "element:user:edit")),
    db: AsyncSession = Depends(get_db_session)
):
    """
    创建带有API密钥的用户。仅限管理员
    """
    # 验证角色
    if request.role not in ["admin", "user"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role must be 'admin' or 'user'"
        )
    
    # 检查用户名是否存在重复
    existing = await db.execute(select(User).where(User.user_name == request.user_name))
    if existing.scalar_one_or_none():
         raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在"
        )
    
    try:
        # 生成API密钥
        api_key = await AuthService.generate_api_key(
            request.user_name,
            real_name=request.real_name,
            role=request.role,
            remark=request.remark,
            dept_code=request.dept_code,
            org_path=request.org_path,
            extra_data=request.extra_data,
            db=db # Pass session!
        )
        
        # 获取用户信息，确保角色加载完成
        result = await db.execute(select(User).options(selectinload(User.roles)).where(User.user_name == request.user_name))
        user = result.scalar_one()
        
        # 分配业务角色
        if request.role_ids:
            service = PermissionService(db)
            await service.update_user_roles(user.id, request.role_ids)
            # Refresh to get roles
            await db.refresh(user)

        # 构建响应结构
        role_ids = request.role_ids or []
        
        return {
            "id": user.id,
            "user_name": user.user_name,
            "real_name": user.real_name,
            "role": user.role,
            "dept_code": user.dept_code,
            "org_path": user.org_path,
            "extra_data": user.extra_data,
            "role_ids": role_ids,
            "remark": user.remark,
            "status": user.status,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "api_key": api_key, # Explicit return
            "allowed_resources": request.allowed_resources or []
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.put("/users/{user_id}")
async def update_user(
    user_id: int,
    request: UpdateUserRequest,
    admin: dict = Depends(require_permission("element", "element:user:edit")),
    db: AsyncSession = Depends(get_db_session)
):
    """
    更新用户及权限，仅限管理员
    """
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
        
    if request.role is not None:
        if request.role not in ["admin", "user"]:
             raise HTTPException(status_code=400, detail="Invalid role")
        user.role = request.role
    
    if request.real_name is not None:
        user.real_name = request.real_name
        
    if request.dept_code is not None:
        user.dept_code = request.dept_code
    
    if request.org_path is not None:
        user.org_path = request.org_path
        
    if request.extra_data is not None:
        user.extra_data = request.extra_data
        
    if request.remark is not None:
        user.remark = request.remark
        
    # 更新业务角色
    if request.role_ids is not None:
        service = PermissionService(db)
        await service.update_user_roles(user_id, request.role_ids)
        
    try:
        await db.commit()
        # 获取用户信息，确保角色加载完成
        result = await db.execute(
            select(User).options(selectinload(User.roles)).where(User.id == user_id)
        )
        user = result.scalar_one()
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to commit user update: {e}")
        raise HTTPException(status_code=500, detail=f"Database update failed: {str(e)}")

    # 清除权限缓存，确保最新角色生效
    try:
        from app.core.redis import get_redis
        redis = await get_redis()
        if redis:
            await redis.delete(f"sys:auth:permissions:v2:user:{user_id}")
    except Exception as e:
        logger.error(f"Failed to clear permission cache for user {user_id}: {e}")
    
    role_ids = [r.id for r in user.roles]
    role_names = [r.name for r in user.roles]

    return {
        "id": user.id,
        "user_name": user.user_name,
        "real_name": user.real_name,
        "role": user.role,
        "dept_code": user.dept_code,
        "org_path": user.org_path,
        "extra_data": user.extra_data,
        "role_ids": role_ids,
        "role_names": role_names,
        "remark": user.remark,
        "status": user.status,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        "allowed_resources": []
    }

@router.patch("/users/{user_id}/status")
async def update_user_status(
    user_id: int,
    request: UpdateStatusRequest,
    admin: dict = Depends(require_permission("element", "element:user:edit")),
    db: AsyncSession = Depends(get_db_session)
):
    """
    更新用户状态，仅限管理员
    """
    current_user_id = admin.get("user_id")
    try:
        current_user_id = int(current_user_id) if current_user_id else None
    except (ValueError, TypeError):
        logger.warning(f"Failed to convert current_user_id to int: {current_user_id}")
    
    if user_id == current_user_id and request.status == 0:
        raise HTTPException(status_code=403, detail="Cannot disable yourself")
        
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    user.status = request.status
    await db.commit()
    
    #-auth 清除用户缓存，确保最新状态生效
    # 仅当用户状态从启用到禁用时才需要清除缓存
    if user.api_key_hash:
        try:
            from app.core.redis import get_redis
            redis = await get_redis()
            if redis:
                await redis.delete(f"auth:api_key:{user.api_key_hash}")
        except Exception as e:
            logger.error(f"Failed to clear user cache: {e}")
    
    return {"message": "User status updated successfully"}

@router.get("/api-key/{user_id}")
async def get_user_api_key(
    user_id: int,
    current_user: dict = Depends(require_api_key),
    db: AsyncSession = Depends(get_db_session)
):
    """
    获取用户 API Key，仅限管理员或用户本人
    """
    current_user_id = current_user.get("user_id")
    current_role = current_user.get("role")
    
    try:
        current_user_id = int(current_user_id) if current_user_id else None
    except (ValueError, TypeError):
        logger.warning(f"Failed to convert current_user_id to int: {current_user_id}")
    
    if current_role != "admin" and user_id != current_user_id:
        raise HTTPException(status_code=403, detail="You can only view your own API Key")
        
    api_key = await AuthService.get_decrypted_api_key(user_id, db=db)
    
    if not api_key:
        raise HTTPException(status_code=404, detail="API Key not found or decryption failed")
        
    return {
        "user_id": user_id,
        "api_key": api_key
    }

@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    admin: dict = Depends(require_permission("element", "element:user:edit")),
    db: AsyncSession = Depends(get_db_session)
):
    """
    删除用户，仅限管理员
    """
    current_user_id = admin.get("user_id")
    try:
        current_user_id = int(current_user_id) if current_user_id else None
    except (ValueError, TypeError):
        logger.warning(f"Failed to convert current_user_id to int: {current_user_id}")
    
    if user_id == current_user_id:
        raise HTTPException(status_code=403, detail="Cannot delete yourself")
        
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if user.role == "admin" and user.user_name == "admin":
         raise HTTPException(status_code=403, detail="Cannot delete system admin")
         
    # 保存用户 API Key 哈希值，用于后续清除缓存
    api_key_hash = user.api_key_hash
         
    # 1. 删除用户关联的资源权限和任务
    from app.models.task import AgentScheduledTask
    
    await db.execute(delete(ResourcePermission).where(ResourcePermission.user_id == user_id))
    await db.execute(delete(AgentScheduledTask).where(AgentScheduledTask.user_id == user_id))
    
    # 2. 使用ORM关系清理UserRoleRelation
    # This avoids StaleDataError because SQLAlchemy will track the deletion
    user.roles = []
    await db.flush()
    
    # 3. 删除用户
    await db.delete(user)
    await db.commit()
    
    # 4. 清除用户缓存
    if api_key_hash:
        try:
            from app.core.redis import get_redis
            redis = await get_redis()
            if redis:
                await redis.delete(f"auth:api_key:{api_key_hash}")
                await redis.delete(f"sys:auth:permissions:v2:user:{user_id}")
        except Exception as e:
            logger.error(f"Failed to clear user cache: {e}")
    
    return {"message": "User deleted successfully"}

@router.post("/users/{user_id}/reset-key")
async def reset_user_api_key(
    user_id: int,
    admin: dict = Depends(require_permission("element", "element:user:edit")),
    db: AsyncSession = Depends(get_db_session)
):
    """
    重置用户 API Key，仅限管理员
    """
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    new_api_key = await AuthService.reset_api_key(user_id, db=db)
    
    if not new_api_key:
        raise HTTPException(status_code=500, detail="Failed to reset API Key")
        
    return {
        "message": "API Key reset successfully",
        "user_id": user_id,
        "api_key": new_api_key
    }

@router.get("/resources/available")
async def get_available_resources(
    request: Request,
    admin: dict = Depends(require_permission("element", "element:user:edit")),
    db: AsyncSession = Depends(get_db_session)
):
    """
    获取所有可用资源，包括智能体、元数据集和API端资源，仅限管理员
    """
    from app.services.api_discovery_service import ApiDiscoveryService
    from app.services.metadata_service import MetadataService
    from app.models.agent import AIAgent
    
    # 1. 智能体
    agent_stmt = select(AIAgent.id, AIAgent.name, AIAgent.display_name).where(
        AIAgent.is_enabled == True,
        AIAgent.is_system == True
    )
    agent_rows = (await db.execute(agent_stmt)).all()
    
    agents = [{"id": r.id, "name": r.display_name or r.name, "key": r.id} for r in agent_rows]
    
    # 2. 元数据集
    meta_datasets = await MetadataService.get_datasets(db)
    datasets = [{"id": str(d.id), "name": d.display_name or d.name, "key": str(d.id)} for d in meta_datasets]
    
    # 3. API资源
    all_apis = ApiDiscoveryService.get_v1_api_resources(request.app)
    # 过滤器：仅显示 /users/ 和 /schema 端点（隐藏 /chat，因为它们已列入全局白名单）
    apis = [
        api for api in all_apis 
        if (
            api["path"].startswith("/api/v1/users") or 
            api["path"].startswith("/api/v1/schema") or
            api["path"] == "/api/v1/chatbi/sql/execute"
        )
    ]
    # 如果需要，格式化 API 以匹配 UI 期望，或保持原样。 
    # ApiDiscoveryService 返回包含 id、名称、描述、组的字典。
    
    return {
        "agents": agents,
        "metadata": datasets,
        "apis": apis
    }

