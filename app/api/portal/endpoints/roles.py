"""
角色管理接口
"""

import code

from fastapi import APIRouter, Depends, Query, HTTPException, status
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, desc, func
from app.core.dependencies import require_admin, require_permission
from app.core.orm import get_db_session
from app.models.permission import Role, ResourcePermission, UserRoleRelation
from app.schemas.permission import PermissionUpdate
from app.services.permission_service import PermissionService

router = APIRouter()

# --- 请求体 ---

class CreateRoleRequest(BaseModel):
    code: str
    name: str
    description: Optional[str] = None

class UpdateRoleRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

# --- 响应体 ---

class RoleResponse(BaseModel):
    id: int
    code: str
    name: str
    description: Optional[str]
    created_at: Optional[str]
    user_count: int

class RoleListResponse(BaseModel):
    total: int
    page: int
    size: int
    items: List[RoleResponse]

class BulkAssignUsersRequest(BaseModel):
    user_ids: List[int]

@router.get("", response_model=RoleListResponse)
async def list_roles(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=1000),
    search: Optional[str] = None,
    admin: dict = Depends(require_permission("menu", "menu:system:roles")),
    db: AsyncSession = Depends(get_db_session)
):
    """
    获取角色列表
    """
    stmt = select(Role).order_by(desc(Role.created_at))

    if search:
        stmt = stmt.where(Role.name.like(f"%{search}%") | Role.code.like(f"%{search}%"))

    # 计数
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar()

    # 分页
    stmt = stmt.offset((page - 1) * size).limit(size)
    result = await db.execute(stmt)
    roles = result.scalars().all()

    items = []
    for role in roles:
        # 获取角色下的用户数量
        user_count_stmt = select(func.count()).select_from(UserRoleRelation).where(UserRoleRelation.role_id == role.id)
        user_count = (await db.execute(user_count_stmt)).scalar()

        items.append({
            "id": role.id,
            "code": role.code,
            "name": role.name,
            "description": role.description,
            "created_at": role.created_at.isoformat() if role.created_at else None,
            "user_count": user_count
        })

    return {
        "total": total,
        "page": page,
        "size": size,
        "items": items
    }

@router.post("")
async def create_role(
    request: CreateRoleRequest,
    admin: dict = Depends(require_permission("element", "element:role:edit")),
    db: AsyncSession = Depends(get_db_session)
):
    """
    创建角色
    """
    # 检查角色是否存在
    existing = await db.execute(select(Role).where(Role.code == request.code))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="角色编码已存在")

    new_role = Role(
        code=request.code,
        name=request.name,
        description=request.description
    )
    db.add(new_role)
    await db.commit()
    await db.refresh(new_role)

    return {
        "id": new_role.id,
        "code": new_role.code,
        "name": new_role.name,
        "description": new_role.description,
        "created_at": new_role.created_at.isoformat()
    }


@router.put("/{role_id}")
async def update_role(
    role_id: int,
    request: UpdateRoleRequest,
    admin: dict = Depends(require_permission("element", "element:role:edit")),
    db: AsyncSession = Depends(get_db_session)
):
    """
    更新角色
    """
    role = await db.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
        
    if request.name is not None:
        role.name = request.name
    if request.description is not None:
        role.description = request.description
        
    await db.commit()
    await db.refresh(role)
    return {
        "id": role.id,
        "code": role.code,
        "name": role.name,
        "description": role.description,
        "created_at": role.created_at.isoformat()
    }

@router.delete("/{role_id}")
async def delete_role(
    role_id: int,
    admin: dict = Depends(require_permission("element", "element:role:edit")),
    db: AsyncSession = Depends(get_db_session)
):
    """
    删除角色
    """
    role = await db.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")

    users_stmt = select(UserRoleRelation.user_id).where(UserRoleRelation.role_id == role_id)
    users_result = await db.execute(users_stmt)
    affected_user_ids = list(users_result.scalars().all())

    # Clean up permissions
    await db.execute(delete(ResourcePermission).where(ResourcePermission.role_id == role_id))

    # Clean up user relations
    await db.execute(delete(UserRoleRelation).where(UserRoleRelation.role_id == role_id))
    
    await db.delete(role)
    await db.commit()

    if affected_user_ids:
        perm_service = PermissionService(db)
        await perm_service.invalidate_cached_permissions_for_users(affected_user_ids)

    return {"message": "Role deleted successfully"}

# --- 角色-用户管理 ---

@router.get("/{role_id}/users")
async def get_role_users(
    role_id: int,
    admin: dict = Depends(require_permission("element", "element:role:edit")),
    db: AsyncSession = Depends(get_db_session)
):
    """
    获取分配到此角色的用户。
    """
    role = await db.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
        
    stmt = select(UserRoleRelation.user_id).where(UserRoleRelation.role_id == role_id)
    result = await db.execute(stmt)
    user_ids = result.scalars().all()
    
    return {"user_ids": user_ids}

@router.post("/{role_id}/users")
async def bulk_assign_role_users(
    role_id: int,
    request: BulkAssignUsersRequest,
    admin: dict = Depends(require_permission("element", "element:role:edit")),
    db: AsyncSession = Depends(get_db_session)
):
    """
    批量将用户分配给此角色。 
    这仅替换此角色的所有用户分配。 
    它不会影响分配给用户的其他角色。
    """
    role = await db.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    
    target_user_ids = set(request.user_ids)
    
    # 1. 获取当前分配到此角色的用户
    stmt = select(UserRoleRelation.user_id).where(UserRoleRelation.role_id == role_id)
    result = await db.execute(stmt)
    current_user_ids = set(result.scalars().all())
    
    # 2. 确定需要添加和删除的用户
    ids_to_add = target_user_ids - current_user_ids
    ids_to_remove = current_user_ids - target_user_ids
    
    # 3. 执行删除
    if ids_to_remove:
        delete_stmt = delete(UserRoleRelation).where(
            UserRoleRelation.role_id == role_id,
            UserRoleRelation.user_id.in_(ids_to_remove)
        )
        await db.execute(delete_stmt)
        
    # 4. 执行添加
    for uid in ids_to_add:
        relation = UserRoleRelation(user_id=uid, role_id=role_id)
        db.add(relation)
        
    await db.commit()

    affected_user_ids = ids_to_add | ids_to_remove
    if affected_user_ids:
        perm_service = PermissionService(db)
        await perm_service.invalidate_cached_permissions_for_users(affected_user_ids)

    return {"message": f"成功更新角色用户:添加 {len(ids_to_add)}, 删除 {len(ids_to_remove)}"}

# --- 角色资源-权限管理 ---

@router.get("/{role_id}/permissions")
async def get_role_resources(
    role_id: int,
    admin: dict = Depends(require_permission("element", "element:role:edit")),
    db: AsyncSession = Depends(get_db_session)
):
    """
    获取分配到此角色的资源。
    """
    role = await db.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
        
    service = PermissionService(db)
    return await service.get_role_permissions(role_id)

@router.put("/{role_id}/permissions")
async def update_role_resources(
    role_id: int,
    permissions: PermissionUpdate,
    admin: dict = Depends(require_permission("element", "element:role:edit")),
    db: AsyncSession = Depends(get_db_session)
):
    """
    更新此角色的资源权限。
    """
    role = await db.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
        
    service = PermissionService(db)
    await service.update_role_permissions(role_id, permissions)
    return {"message": "Role permissions updated successfully"}