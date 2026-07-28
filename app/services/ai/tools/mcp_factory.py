import json
import logging
from typing import Dict, Any
from pydantic import create_model, Field
from app.services.ai.tools.tool_compat import StructuredTool
from app.models.mcp import McpToolCache
from app.services.ai.tools.mcp_client import McpClientService

logger = logging.getLogger(__name__)

class McpToolFactory:
    def create_tool(tool_record: McpToolCache) -> StructuredTool:
        """从缓存的 MCP 工具记录创建运行时 StructuredTool 兼容的包装器"""
        # 1. 从 MCP 中解析 JSON schema
        schema_def = json.loads(tool_record.parameter_schema or "{}")
        properties = schema_def.get("properties", {})
        required_fields = set(schema_def.get("required", []))

        fields = {}
        for param_name, param_def in properties.items():
            p_type = str
            type_str = param_def.get("type", "string")
            if type_str == "integer": p_type = int
            elif type_str == "boolean": p_type = bool
            elif type_str == "number": p_type = float

            p_desc = param_def.get("description", "")
            p_default = ... if param_name in required_fields else param_def.get("default", None)
            
            fields[param_name] = (p_type, Field(default=p_default, description=p_desc))

        # 创建动态 Pydantic 模型
        args_schema = create_model(f"Mcp_{tool_record.tool_name.replace(':', '_')}Args", **fields)

        # 2. 定义执行逻辑
        async def _execute(**kwargs) -> str:
            # 提取 raw tool name
            # 全名： "server_name:raw_tool_name"
            if ":" in tool_record.tool_name:
                raw_name = tool_record.tool_name.split(":", 1)[1]
            else:
                raw_name = tool_record.tool_name

            return await McpClientService.call_remote_tool(
                server_id=tool_record.server_id,
                tool_name=raw_name,
                arguments=kwargs
            )

        _execute.__doc__ = tool_record.tool_description or f"MCP tool: {tool_record.tool_name}"
        
        # Tool name should ideally be our full name to avoid collisions
        return StructuredTool.from_function(
            func=None,
            coroutine=_execute,
            name=tool_record.tool_name,
            description=tool_record.tool_description or "",
            args_schema=args_schema
        )