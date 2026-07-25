"""
Agent 管理器
"""
import logging
import uuid
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update, or_
from sqlalchemy.orm import selectinload
from app.models.agent import AIAgent, AIAgentVersion
from app.schemas.agent import ChatConfig, AIAgentBase, AIAgentVersionBase
import json

logger = logging.getLogger(__name__)

class AgentManagerService:
    """
    Agent 管理器
    """

    @staticmethod
    async def get_active_agent_config(
        session: AsyncSession,
        agent_id: Optional[str] = None,
        agent_name: Optional[str] = None
    ) -> Optional[ChatConfig]:
        """
        获取活动的 Agent 配置

        - 对于本地：使用最新发布的版本。
        - 对于 RAGFLOW：使用代理的主配置（不需要本地版本）。
        """
        try:
            # 1. 首先获取 Agent 基础记录
            stmt = select(AIAgent)
            if agent_id:
                stmt = stmt.where(AIAgent.id == agent_id, AIAgent.name == agent_name)
            elif agent_name:
                stmt = stmt.where(AIAgent.name == agent_name)
            else:
                stmt = stmt.where(AIAgent.name == 'chat-bi')

            result = await session.execute(stmt)
            agent = result.scalar_one_or_none()

            if not agent:
                logger.warning(f"No agent found for id={agent_id}, name={agent_name}")
                return None

            if not agent.is_enabled:
                logger.warning(f"Agent {agent.name} is disabled.")
                return None

            # 2. 处理 RAGFLOW 和 OPENCLAW 引擎（绕过版本控制）
            if agent.engine_type in ['RAGFLOW', 'OPENCLAW']:
                return ChatConfig(
                    agent_id=agent.id,
                    agent_name=agent.name,
                    agent_display_name=agent.display_name or agent.name,
                    agent_version="managed",
                    model_name=agent.engine_config.get("model", "OpenClaw-Remote") if agent.engine_type == 'OPENCLAW' else "RAGFlow-Remote",
                    temperature=0.0,
                    system_prompt=f"[Managed by {agent.engine_type}]",
                    tools=[],
                    capabilities=agent.capabilities or [],
                    engine_type=agent.engine_type,
                    engine_config=agent.engine_config
                )

            # 3. 处理本地引擎（需要最新发布版本）
            query = select(AIAgentVersion).where(
                AIAgentVersion.agent_id == agent.id,
                AIAgentVersion.status == 'PUBLISHED'
            ).order_by(AIAgentVersion.version_number.desc()).limit(1)

            v_res = await session.execute(query)
            version = v_res.scalar_one_or_none()

            if not version:
                logger.warning(f"No published version found for local agent {agent.name}")
                return None
            
            # 处理 tools
            tools_list = version.tools
            if isinstance(tools_list, str):
                try:
                    tools_list = json.loads(tools_list)
                except:
                    tools_list = []

            return ChatConfig(
                agent_id=agent.id,
                agent_name=agent.name,
                agent_display_name=agent.display_name or agent.name,
                agent_version=f"v{version.version_number}",
                model_name=version.model_name,
                temperature=version.temperature,
                synthesis_model_name=version.synthesis_model_name,
                synthesis_temperature=version.synthesis_temperature,
                system_prompt=version.system_prompt,
                tools=tools_list or [],
                capabilities=agent.capabilities or [],
                engine_type=agent.engine_type,
                engine_config=agent.engine_config
            )

        except Exception as e:
            logger.error(f"Error fetching agent config: {e}", exc_info=True)
            return None

    @staticmethod
    async def get_version_config(
        session: AsyncSession,
        version_id: str
    ) -> Optional[ChatConfig]:
        """
        获取指定版本 ID 的配置。
        如果 version_id 与 AIAgent ID 匹配且为 RAGFLOW 模式，则返回托管配置。
        """
        try:
            # 1. 首先获取版本字段
            query = select(AIAgentVersion).join(AIAgent).options(selectinload(AIAgentVersion.agent)).where(AIAgentVersion.id == version_id)
            result = await session.execute(query)
            version = result.scalar_one_or_none()

            if version:
                tools_list = version.tools
                if isinstance(tools_list, str):
                    try:
                        tools_list = json.loads(tools_list)
                    except:
                        tools_list = []

                return ChatConfig(
                    agent_id=version.agent_id,
                    agent_name=version.agent.name,
                    agent_display_name=version.agent.display_name or version.agent.name,
                    agent_version=f"v{version.version_number}",
                    model_name=version.model_name,
                    temperature=version.temperature,
                    synthesis_model_name=version.synthesis_model_name,
                    synthesis_temperature=version.synthesis_temperature,
                    system_prompt=version.system_prompt,
                    tools=tools_list or [],
                    capabilities=version.agent.capabilities or [],
                    engine_type=version.agent.engine_type,
                    engine_config=version.agent.engine_config
                )

            # 2. 回退：检查 version_id 是否确实是代理 ID（用于 RAGFlow 快捷方式）
            agent_query = select(AIAgent).where(AIAgent.id == version_id)
            a_res = await session.execute(agent_query)
            agent = a_res.scalar_one_or_none()

            if agent and agent.engine_type == 'RAGFLOW':
                return await AgentManagerService.get_active_agent_config(session, agent_id=agent.id)

            return None
        except Exception as e:
            logger.error(f"Error fetching version config: {e}", exc_info=True)
            return None


    @staticmethod
    async def list_agents(session: AsyncSession, user: Any = None) -> List[Any]:
        """
        根据用户可见性列出所有可用 agent 列表
        如果用户是管理员，返回所有 agent。
        否则，返回用户可见的 agent。
        """
        # 1. 获取agent（根据 sort_order DESC, 之后是 system）
        query = select(AIAgent).order_by(AIAgent.sort_order.desc(), AIAgent.is_system.desc(), AIAgent.display_name)
        result = await session.execute(query)
        agents = result.scalars().all()

        # 判断用户信息
        is_admin = user.get('role', '') == 'admin' if isinstance(user, dict) else getattr(user, 'role', '') == 'admin'
        username = user.get('user_name', '') if isinstance(user, dict) else getattr(user, 'user_name', '')
        user_id = user.get('user_id', user.get('id', '')) if isinstance(user, dict) else getattr(user, 'id', '')

        # 2. 获取执行次数
        from app.models.audit import AgentExecutionHistory
        from sqlalchemy import func

        count_query = select(AgentExecutionHistory.agent_id, func.count(AgentExecutionHistory.id))

        # 根据用户角色过滤
        if not is_admin and user_id:
            count_query = count_query.where(AgentExecutionHistory.user_id == user_id)

        count_query = count_query.group_by(AgentExecutionHistory.agent_id)
        count_res = await session.execute(count_query)
        counts = dict(count_res.fetchall())

        # 判断可见性和可编辑性
        visible_agents = []

        for agent in agents:
            # 可见性检查（当前全部可见，但可编辑性不同）

            # 可编辑性检查
            is_owner = agent.created_by == username
            agent.is_editable = True if is_admin or is_owner or (not agent.created_by and is_admin) else False

            # 特殊情况：system agent 对普通用户只读
            if agent.is_system and not is_admin:
                agent.is_editable = False

            # 设置执行次数
            agent.execution_count = counts.get(agent.id, 0)

            visible_agents.append(agent)

        return visible_agents

    @staticmethod
    async def list_allowed_agents(session: AsyncSession, user: Any = None, keyword: Optional[str] = None) -> List[Any]:
        """
        查询有权限 EXECUTE/CHAT 的 agent 列表
        - Admin: All
        - User: System Agents + Owned Agents + Permitted Agents
        """
        if not user:
            return []

        # User Info extraction
        if isinstance(user, dict):
            is_admin = user.get('role', '') == 'admin'
            username = user.get('user_name', '')
            user_id = user.get('user_id', user.get('id', ''))
        else:
            is_admin = getattr(user, 'role', '') == 'admin'
            username = getattr(user, 'user_name', '')
            user_id = getattr(user, 'id', '')

        stmt = select(AIAgent).where(AIAgent.is_enabled == True)

        if not is_admin:
            # Normal User Logic
            from app.services.permission_service import PermissionService
            perm_service = PermissionService(session)
            try:
                uid_int = int(user_id)
                perms = await perm_service.get_user_permissions(uid_int)
                allowed_ids = perms.permissions.agents
            except (ValueError, TypeError):
                allowed_ids = []

            from sqlalchemy import and_
            stmt = stmt.where(
                or_(
                    and_(AIAgent.is_system == True, AIAgent.id.in_(allowed_ids)),
                    and_(AIAgent.is_system == False, AIAgent.created_by == username)
                )
            )
        
        # Keyword Filter
        if keyword:
            stmt = stmt.where(or_(
                AIAgent.name.ilike(f"%{keyword}%"),
                AIAgent.display_name.ilike(f"%{keyword}%")
            ))

        # Sort: sort_order DESC, then System first (desc), then Alphabetical
        stmt = stmt.order_by(AIAgent.sort_order.desc(), AIAgent.is_system.desc(), AIAgent.display_name)

        return (await session.execute(stmt)).scalars().all()

    @staticmethod
    async def create_agent(session: AsyncSession, data: AIAgentBase, user: Any = None) -> AIAgent:
        """
        创建一个新 agent 元数据条目
        - 管理员可以创建所有 agent
        - 普通用户只能创建非系统 agent
        """
        if isinstance(user, dict):
            created_by = user.get('user_name')
            is_admin = user.get('role', '') == 'admin'
        else:
            created_by = getattr(user, 'user_name', None) if user else None
            is_admin = user and getattr(user, 'role', '') == 'admin'
        
        # 检查 agent 是否已存在
        existing_query = select(AIAgent).where(AIAgent.name == data.name)
        result = await session.execute(existing_query)
        if result.scalar_one_or_none():
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail=f"Agent with ID/Name '{data.name}' already exists.")

        agent = AIAgent(
            id=str(uuid.uuid4()),
            name=data.name,
            display_name=data.display_name,
            description=data.description,
            avatar_url=data.avatar_url,
            capabilities=data.capabilities,
            is_system=data.is_system if is_admin and data.is_system is not None else False,
            sort_order=data.sort_order if data.sort_order is not None else 0,
            is_enabled=data.is_enabled if data.is_enabled is not None else True,
            created_by=created_by,
            engine_type=data.engine_type,
            engine_config=data.engine_config
        )
        session.add(agent)
        await session.commit()
        await session.refresh(agent)
        
        # 无效缓存
        from app.services.ai.router_service import router_service
        router_service.invalidate_cache()
        
        return agent

    @staticmethod
    async def update_agent(session: AsyncSession, agent_id: str, data: AIAgentBase, user: Any = None) -> Optional[AIAgent]:
        """
        更新一个已存在的 agent 元数据条目
        - 管理员可以更新所有 agent
        - 普通用户只能更新自己创建的 agent
        """
        agent = await session.get(AIAgent, agent_id)
        if not agent:
            return None
            
        # Permission Check
        if isinstance(user, dict):
            is_admin = user.get('role', '') == 'admin'
            username = user.get('user_name', '')
        else:
            is_admin = user and getattr(user, 'role', '') == 'admin'
            username = user and getattr(user, 'user_name', '')
            
        if not is_admin and agent.created_by and agent.created_by != username:
            return None # Or raise Forbidden in Endpoint
        
        # System Agent Check
        if agent.is_system and not is_admin:
            return None

        agent.name = data.name
        agent.display_name = data.display_name
        agent.description = data.description
        agent.avatar_url = data.avatar_url
        agent.capabilities = data.capabilities
        agent.sort_order = data.sort_order if data.sort_order is not None else agent.sort_order
        
        if is_admin and data.is_system is not None:
            agent.is_system = data.is_system
            
        if data.is_enabled is not None:
            agent.is_enabled = data.is_enabled
        
        # Update Engine Config
        if data.engine_type:
            agent.engine_type = data.engine_type
        if data.engine_config is not None:
            agent.engine_config = data.engine_config
        
        await session.commit()
        await session.refresh(agent)
        
        # Invalidate Router Cache
        from app.services.ai.router_service import router_service
        router_service.invalidate_cache()
        
        return agent

    @staticmethod
    async def delete_agent(session: AsyncSession, agent_id: str, user: Any = None) -> bool:
        """
        删除 agent，系统级 agent 不能被删除
        """
        agent = await session.get(AIAgent, agent_id)
        if not agent or agent.is_system:
            return False

        # Permission Check
        if isinstance(user, dict):
            is_admin = user.get('role', '') == 'admin'
            username = user.get('user_name', '')
        else:
            is_admin = user and getattr(user, 'role', '') == 'admin'
            username = user and getattr(user, 'user_name', '')
            
        if not is_admin and agent.created_by and agent.created_by != username:
            return False

        await session.delete(agent)
        await session.commit()
        
        # Invalidate Router Cache
        from app.services.ai.router_service import router_service
        router_service.invalidate_cache()
        
        return True

    @staticmethod
    async def get_agent_versions(session: AsyncSession, agent_id: str, user: Any = None) -> List[AIAgentVersion]:
        """
        获取指定 agent 的所有版本（检查可见性）
        """
        agent = await session.get(AIAgent, agent_id)
        if not agent:
            return []

        # Permission Check (Visibility)
        # All users can see versions of all agents (read-only), but we could restrict if needed.
        # Currently, consistent with metadata, we allow viewing.
        
        query = select(AIAgentVersion).where(AIAgentVersion.agent_id == agent_id).order_by(AIAgentVersion.version_number.desc())
        result = await session.execute(query)
        return result.scalars().all()

    @staticmethod
    def _normalize_tools_for_db(tools: List[Any]) -> List[Any]:
        """
        将 ToolConfigItem 对象转换为普通字典，用于数据库存储
        """
        if not tools:
            return []
        
        normalized = []
        for item in tools:
            if hasattr(item, "dict"): # Pydantic v1
                normalized.append(item.dict(exclude_none=True))
            elif hasattr(item, "model_dump"): # Pydantic v2
                normalized.append(item.model_dump(exclude_none=True))
            else:
                normalized.append(item)
        return normalized

    @staticmethod
    async def create_agent_version(session: AsyncSession, agent_id: str, data: AIAgentVersionBase, user: Any = None) -> Optional[AIAgentVersion]:
        """
        创建 agent 的新版本（检查所有权）
        """
        agent = await session.get(AIAgent, agent_id)
        if not agent:
            return None

        # Permission Check
        if isinstance(user, dict):
            is_admin = user.get('role', '') == 'admin'
            username = user.get('user_name', '')
        else:
            is_admin = user and getattr(user, 'role', '') == 'admin'
            username = user and getattr(user, 'user_name', '')

        if not is_admin and agent.created_by and agent.created_by != username:
            return None # Forbidden

        # 确定下一个版本号
        query = select(AIAgentVersion.version_number).where(AIAgentVersion.agent_id == agent_id).order_by(AIAgentVersion.version_number.desc()).limit(1)
        prev_result = await session.execute(query)
        prev_v = prev_result.scalar_one_or_none()
        next_v = (prev_v or 0) + 1
        
        version = AIAgentVersion(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            version_number=next_v,
            model_name=data.model_name,
            temperature=data.temperature,
            synthesis_model_name=data.synthesis_model_name,
            synthesis_temperature=data.synthesis_temperature,
            system_prompt=data.system_prompt,
            tools=AgentManagerService._normalize_tools_for_db(data.tools),
            status="DRAFT",
            comment=data.comment
        )
        session.add(version)
        await session.commit()
        await session.refresh(version)
        return version

    @staticmethod
    async def update_agent_version(session: AsyncSession, agent_id: str, version_id: str, data: AIAgentVersionBase, user: Any = None) -> Optional[AIAgentVersion]:
        """
        更新指定 DRAFT 版本（检查所有权）
        """
        agent = await session.get(AIAgent, agent_id)
        version = await session.get(AIAgentVersion, version_id)
        if not agent or not version:
            return None
            
        # 只有 DRAFT 版本可以被修改
        if version.status != "DRAFT":
            return None

        # Permission Check
        if isinstance(user, dict):
            is_admin = user.get('role', '') == 'admin'
            username = user.get('user_name', '')
        else:
            is_admin = user and getattr(user, 'role', '') == 'admin'
            username = user and getattr(user, 'user_name', '')

        if not is_admin and agent.created_by and agent.created_by != username:
            return None # Forbidden

        # Update fields
        version.model_name = data.model_name or version.model_name
        version.temperature = data.temperature if data.temperature is not None else version.temperature
        version.synthesis_model_name = data.synthesis_model_name
        version.synthesis_temperature = data.synthesis_temperature
        version.system_prompt = data.system_prompt
        version.tools = AgentManagerService._normalize_tools_for_db(data.tools)
        version.comment = data.comment or version.comment
        
        await session.commit()
        await session.refresh(version)
        return version

    @staticmethod
    async def publish_version(session: AsyncSession, agent_id: str, version_id: str, user: Any = None) -> bool:
        """
        发布指定版本（检查所有权）
        """
        agent = await session.get(AIAgent, agent_id)
        if not agent:
            return False

        # Permission Check
        if isinstance(user, dict):
            is_admin = user.get('role', '') == 'admin'
            username = user.get('user_name', '')
        else:
            is_admin = user and getattr(user, 'role', '') == 'admin'
            username = user and getattr(user, 'user_name', '')

        if not is_admin and agent.created_by and agent.created_by != username:
            return False # Forbidden

        # 1. 归档当前 agent 版本的所有已发布版本
        await session.execute(
            update(AIAgentVersion)
            .where(AIAgentVersion.agent_id == agent_id, AIAgentVersion.status == 'PUBLISHED')
            .values(status='ARCHIVED')
        )
        
        # 2. 设置目标版本为已发布
        await session.execute(
            update(AIAgentVersion)
            .where(AIAgentVersion.id == version_id)
            .values(status='PUBLISHED')
        )
        
        await session.commit()
        return True

    @staticmethod
    async def delete_version(session: AsyncSession, agent_id: str, version_id: str, user: Any = None) -> bool:
        """删除指定版本 (only DRAFT or ARCHIVED)"""
        agent = await session.get(AIAgent, agent_id)
        version = await session.get(AIAgentVersion, version_id)
        
        if not agent or not version:
            return False
            
        # Cannot delete PUBLISHED version
        if version.status == "PUBLISHED":
            return False

        # Permission Check
        if isinstance(user, dict):
            is_admin = user.get('role', '') == 'admin'
            username = user.get('user_name', '')
        else:
            is_admin = user and getattr(user, 'role', '') == 'admin'
            username = user and getattr(user, 'user_name', '')

        if not is_admin and agent.created_by and agent.created_by != username:
            return False # Forbidden

        await session.delete(version)
        await session.commit()
        return True