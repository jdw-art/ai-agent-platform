"""
快捷指令服务
"""

from operator import or_
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel
from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.portal.endpoints.audit import is_admin
from app.core.orm import Base
from sqlalchemy import Column, Integer, String, Text, DateTime, func

# ORM 模型
class SlashCommand(Base):
    __tablename__ = "slash_commands"

    id = Column(Integer, primary_key=True, autoincrement=True)
    label = Column(String(50), nullable=False)
    command = Column(Text, nullable=False)
    sort_order = Column(Integer, default=0)
    created_by = Column(String(64), default="system")
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

# Pydantic Schemas
class SlashCommandBase(BaseModel):
    label: str
    command: str
    sort_order: int = 0

class SlashCommandCreate(SlashCommandBase):
    pass

class SlashCommandUpdate(SlashCommandBase):
    pass

class SlashCommandReorderItem(BaseModel):
    id: int
    sort_order: int

class SlashCommandReorderRequest(BaseModel):
    items: List[SlashCommandReorderItem]

class SlashCommandResponse(SlashCommandBase):
    id: int
    created_by: str
    created_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class SlashCommandService:
    @staticmethod
    async def list_commands(session: AsyncSession, user: dict) -> List[SlashCommand]:
        """
        获取所有快捷指令
        1. system/admin 指令
        2. 用户指令
        """
        from sqlalchemy import case, or_

        username = user.get("username", "unknown")

        # 过滤逻辑
        filter_condition = or_(
            SlashCommand.created_by.in_(["system", "admin"]),
            SlashCommand.created_by == username
        )

        # 排序逻辑：用户指令优先，其他次之
        priority_sort = case(
            (SlashCommand.created_by == username, 0),
            else_=1
        )

        stmt = select(SlashCommand).where(filter_condition).order_by(
            priority_sort.asc(),
            SlashCommand.sort_order.asc()
        )

        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def create_command(session: AsyncSession, data: SlashCommandCreate, user_name: str) -> SlashCommand:
        """
        创建快捷指令
        """
        cmd = SlashCommand(**data.dict(), created_by=user_name)
        session.add(cmd)
        await session.commit()
        await session.refresh(cmd)
        return cmd

    @staticmethod
    async def update_command(session: AsyncSession, cmd_id: int, data: SlashCommandUpdate, user: dict) -> Optional[SlashCommand]:
        """
        更新快捷指令
        """
        cmd = await session.get(SlashCommand, cmd_id)
        if not cmd:
            return None

        # 权限检查
        is_admin = user.get("role") == "admin"
        is_owner = cmd.created_by == user.get("user_name")

        if not (is_admin or is_owner):
            return None

        for key, value in data.dict().items():
            setattr(cmd, key, value)

        await session.commit()
        await session.refresh(cmd)
        return cmd

    @staticmethod
    async def delete_command(session: AsyncSession, cmd_id: int, user: dict) -> bool:
        """
        删除指令
        """
        cmd = await session.get(SlashCommand, cmd_id)
        if not cmd:
            return False
        
        # 权限检查
        is_admin = user.get("role") == "admin"
        is_owner = cmd.created_by == user.get("user_name")
        
        if not (is_admin or is_owner):
            return False
        
        await session.delete(cmd)
        await session.commit()
        return True

    @staticmethod
    async def reorder_commands(session: AsyncSession, data: SlashCommandReorderRequest, user: dict) -> bool:
        """
        批量更新用户拥有的命令的排序顺序，或者如果用户是管理员则更新排序顺序。
        """
        username = user.get("user_name")
        is_admin = user.get("role") == "admin"
        
        # 1. Collect all IDs
        ids = [item.id for item in data.items]
        
        # 2. Fetch all matching commands to verify ownership
        stmt = select(SlashCommand).where(SlashCommand.id.in_(ids))
        result = await session.execute(stmt)
        commands = {c.id: c for c in result.scalars().all()}
        
        # 3. Update orders
        for item in data.items:
            cmd = commands.get(item.id)
            if not cmd:
                continue
            
            # Check ownership (unless admin)
            if not is_admin and cmd.created_by != username:
                continue
                
            cmd.sort_order = item.sort_order
            
        await session.commit()
        return True
