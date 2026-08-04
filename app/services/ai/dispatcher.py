"""根据配置和意图，将 agent 执行任务分派给相应的执行器"""

import logging
from typing import List, Dict, Any, Optional
from app.schemas.agent import AgentExecutionStep, ChatConfig
from app.services.ai.turn_classifier import (
    SharedTurn,
    TurnType,
    adapt_classification_for_agent,
    attach_turn_classification,
    resolve_turn_for_session,
    turn_type_label,
)
from app.services.ai.executors.base import BaseExecutor
from app.services.ai.executors.data_executor import DataQueryExecutor
from app.services.ai.executors.assistant_executor import AssistantExecutor
from app.services.ai.executors.knowledge_executor import KnowledgeExecutor
from app.services.ai.executors.rag_executor import RAGExecutor
from app.services.ai.executors.openclaw_executor import OpenClawExecutor