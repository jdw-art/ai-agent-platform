"""
上下文管理模块, 用于存储和检索请求范围的上下文信息。
"""

from contextvars import ContextVar
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

# 定义一个 ContextVar 来保存请求范围的调试选项
# 结构: { "dry_run": bool, "return_raw_prompt": bool, "model_override": str, ... }
debug_context: ContextVar[Dict[str, Any]] = ContextVar("debug_context", default={})

def get_debug_option(key: str, default: Any = None) -> Any:
    """Helper to get a value from the current debug context."""
    ctx = debug_context.get()
    return ctx.get(key, default)

def set_debug_context(options: Dict[str, Any]):
    """Set the debug context for the current request."""
    debug_context.set(options or {})

# 定义一个 ContextVar 来保存当前执行 agent 的上下文
class AgentContext(BaseModel):
    agent_id: str
    agent_name: str
    dataset_ids: List[str] = Field(default_factory=list)
    engine_type: str = "LOCAL"
    engine_config: Optional[Dict[str, Any]] = None
    rag_params: Optional[Dict[str, Any]] = None
    
    # User session info for permission enforcement in tools/services
    user_id: Optional[int] = None
    conversation_id: Optional[str] = None
    is_admin: bool = False
    api_key: Optional[str] = None
    user_dimensions: Dict[str, Any] = Field(default_factory=dict)
    
    # Execution details for tracing (displayed in frontend)
    trace_logs: List[str] = Field(default_factory=list)

agent_context: ContextVar[Optional[AgentContext]] = ContextVar("agent_context", default=None)

def get_current_agent_context() -> Optional[AgentContext]:
    """Get the current agent context object."""
    return agent_context.get()

def set_agent_context(context: AgentContext):
    """Set the agent context for the current execution."""
    agent_context.set(context)

def get_current_agent_config(key: str, default: Any = None) -> Any:
    """Helper to get a value from the current agent context (for backward compatibility)."""
    ctx = agent_context.get()
    if not ctx:
        return default
    return getattr(ctx, key, default)
