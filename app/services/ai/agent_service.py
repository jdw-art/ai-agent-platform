import json
import logging
import time
import uuid
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional, AsyncGenerator

from app.schemas.agent import AgentExecutionStep, ChatConfig
from app.services.ai.agent_manager import AgentManagerService
from app.services.ai.audit import AuditManager
from app.services.ai.config import AgentConfigProvider
from app.services.ai.context_manager import AgentContextManager
from app.services.ai.dispatcher import AgentDispatcher
from app.services.ai.memory_service import memory_service
from app.services.ai.agent_prompts import AgentServicePrompts
from app.services.ai.executors.common import extract_tokens_from_message
from app.services.ai.runtime.agentscope.compat import HumanMessage, SystemMessage
from app.core.orm import AsyncSessionLocal

logger = logging.getLogger(__name__)

AWAITING_RESUME_STATUSES = frozenset({"awaiting_permission", "awaiting_external_execution"})

def _accumulate_stream_content(full: str, chunk: Dict[str, Any]) -> str:
    """
    合并 SSE chunk 到会话正文，retraction 表示用新正文整体替换
    """
    if chunk.get("type") == "retraction":
        return str(chunk.get("content") or "")
    if "content" in chunk:
        return full + str(chunk["content"])
    return full

class AgentService:
    """
    用于 AI 代理交互的统一编排器。 
    现在重构为将执行委托给专门的执行器。
    """

    async def generate_greesting(self) -> str:
        """生成欢迎语"""
        return AgentServicePrompts.GREETING