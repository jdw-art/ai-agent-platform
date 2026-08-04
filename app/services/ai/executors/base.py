from abc import ABC, abstractmethod
import time
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

from app.schemas.agent import AgentExecutionStep, ChatConfig

class BaseExecutor(ABC):
    """
    基础执行器，定义了执行器的基本接口
    """
    def __init__(
        self,
        config: ChatConfig,
        trace_id: str,
        trace_buffer: List[AgentExecutionStep],
        debug_options: Dict[str, Any] = None,
        user_info: Optional[Dict[str, Any]] = None,
        conversation_id: Optional[str] = None,
        permission_options: Dict[str, Any] = None,
    ):
        """初始化执行器"""
        self.config = config
        self.trace_id = trace_id
        self.trace_buffer = trace_buffer
        self.debug_options = debug_options or {}
        self.permission_options = permission_options or {}
        self.user_info = user_info
        self.conversation_id = conversation_id
        self.step_counter = 0

    @abstractmethod
    async def execute(
        self,
        history: List[Dict[str, str]]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """主执行器循环，必须生成与 SSE 兼容的字典"""
        pass

    def _increment_step(self) -> int:
        self.step_counter += 1
        return self.step_counter

    def record_llm_token_usage(
        self,
        *,
        prompt_tokens: int,
        completion_tokens: int,
        event_type: str = "model_call",
        model: str | None = None,
        tool_name: str | None = None,
        execution_time_ms: float | None = None,
    ) -> None:
        """记录 LLM API 调用的 token 使用情况到 trace_buffer，用于后续审计"""
        prompt_tokens = int(prompt_tokens or 0)
        completion_tokens = int(completion_tokens or 0)
        if prompt_tokens <= 0 and completion_tokens <= 0:
            return
        self._increment_step()
        self.trace_buffer.append(
            AgentExecutionStep(
                step_number=self.step_counter,
                event_type=event_type,
                agent_name=self.config.agent_name,
                model=model,
                temperature=float(self.config.temperature or 0),
                tool_name=tool_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                execution_time_ms=execution_time_ms,
                timestamp=datetime.now(),
            )
        )

    def _record_agent_scope_model_call(
        self,
        event: Any,
        *,
        state: Dict[str, Any],
        native_model: Any
    ) -> None:
        """记录 AgentScope 模型调用的 token 使用情况到 trace_buffer，用于后续审计"""
        reply_id = str(getattr(event, "reply_id", "") or "")
        started_at = state.get("model_call_started_at", {}).get(reply_id, time.time())
        self.record_llm_token_usage(
            prompt_tokens=int(getattr(event, "input_tokens", 0) or 0),
            completion_tokens=int(getattr(event, "output_tokens", 0) or 0),
            event_type="model_call",
            model=str(
                getattr(event, "model_name", "")
                or getattr(native_model, "model", self.config.model_name)
                or ""
            ),
            tool_name="agentscope_model_call",
            execution_time_ms=(time.time() - started_at) * 1000,
        )
