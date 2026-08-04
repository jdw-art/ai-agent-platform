"""
长期记忆工具
"""

import logging
import json
from app.services.ai.tools.tool_compat import tool
from app.services.ai.memory_service import ltm_service

logger = logging.getLogger(__name__)

@tool
async def update_user_preference(user_id: str, key: str, value: str) -> str:
    """
    持久化用户偏好、行为习惯或关于用户的核心事实，以 Key-Value 的形式异步写入到 Redis 长期记忆哈希中

    :param user_id: 用户 ID
    :param key: 偏好键
    :param value: 偏好值
    :return: 确认消息
    """
    try:
        success = await ltm_service.update_preference(user_id, key, value)
        if success:
            return f"成功持久化保存用户偏好记忆！已记录 '{key}': '{value}'。"
        else:
            return "提示：保存记忆失败，可能是 Redis 服务不可用。"
    except Exception as e:
        return f"持久化记忆操作异常: {str(e)}"

@tool
async def fetch_user_long_term_memory(user_id: str) -> str:
    """
    主动查询并拉取当前用户在 Redis 长期记忆哈希中的所有偏好、行为习惯或核心事实

    :param user_id: 用户 ID
    :return: 所有偏好、行为习惯或核心事实的 JSON 字符串
    """
    try:
        data = await ltm_service.fetch_memory(user_id)
        if not data:
            return "当前用户没有任何长期记忆或事实偏好记录。"

        return f"查询到用户的长期记忆：\n```json\n{json.dumps(data, ensure_ascii=False, indent=2)}\n```"
    except Exception as e:
        return f"检索长期记忆操作异常: {str(e)}"

@tool
async def delete_user_preference(user_id: str, key: str) -> str:
    """
    删除用户偏好记忆中的指定键值对

    :param user_id: 用户 ID
    :param key: 偏好键
    :return: 确认消息
    """
    try:
        success = await ltm_service.delete_preference(user_id, key)
        if success:
            return f"成功删除用户偏好记忆！已删除 '{key}'。"
        else:
            return "提示：删除记忆失败，可能是 Redis 服务不可用。"
    except Exception as e:
        return f"删除记忆操作异常: {str(e)}"