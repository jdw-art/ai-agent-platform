"""记忆服务"""
import json
import logging
from typing import List, Dict, Any, Optional
from app.core.redis import get_redis

logger = logging.getLogger(__name__)

class MemoryService:
    """
    在 Redis 中管理会话历史
    使用 Redis List 存储 JSON 化的 message
    """
    KEY_PREFIX = "conversation"
    HISTORY_SUFFIX = "history"
    DATA_RESULT_SUFFIX = "last_data_result"

    def __init__(self, max_history_turns: int = 50, ttl: int = 604800):
        """
        初始化记忆服务
        :param max_history_turns: 最大历史轮数
        :param ttl: 过期时间（秒）
        """
        self.max_history_turns = max_history_turns
        self.ttl = ttl

    def _get_key(self, user_id: str, conversation_id: str) -> str:
        """
        获取会话历史键
        :param user_id: 用户 ID
        :param conversation_id: 会话 ID
        :return: 会话历史键
        Format: conversation:{user_id}:{conversation_id}:history
        """
        # 确保 user_id 是字符串并处理潜在的 None （回退到“匿名”或错误？）
        # 为了安全起见，如果 user_id 丢失，我们可能会失败，但为了向后兼容
        # 通过宽松的验证系统，我们可以保护 str 转换。
        uid = str(user_id) if user_id else "anonymous" 
        return f"{self.KEY_PREFIX}:{uid}:{conversation_id}:{self.HISTORY_SUFFIX}"

    def _get_data_result_key(self, user_id: str, conversation_id: str) -> str:
        uid = str(user_id) if user_id else "anonymous"
        return f"{self.KEY_PREFIX}:{uid}:{conversation_id}:{self.DATA_RESULT_SUFFIX}"

    async def get_history(self, user_id: str, conversation_id: str, limit: Optional[int] = None, offset: int = 0) -> List[Dict[str, str]]:
        """
        从 Redis 中检索历史记录，并支持分页。
        offset=0 表示检索最新消息。
        :param user_id: 用户 ID
        :param conversation_id: 会话 ID
        :param limit: 最大返回条数
        :param offset: 偏移量
        :return: 会话历史列表
        """
        redis = await get_redis()
        if not redis:
            return []

        key = self._get_key(user_id, conversation_id)
        # 获取所有的历史记录
        data = await redis.lrange(key, 0, -1)
        logger.info(f"[MemoryService] Fetching history for key: {key}. Total items: {len(data)}, Limit: {limit}, Offset: {offset}")
        
        history = []
        for item in data:
            try:
                history.append(json.loads(item))
            except Exception as e:
                logger.error(f"Failed to parse history item: {item}. Error: {e}")

        # 执行分页
        if limit:
            start_idx = len(history) - (offset + limit)
            end_idx = len(history) - offset

            # 边界检查
            if start_idx >= end_idx:
                return []

            history = history[start_idx:end_idx]

        return history

    async def add_message(
        self,
        user_id: str,
        conversation_id: str,
        role: str, content: str,
        trace_id: Optional[str] = None,
        files: Optional[List[Dict[str, Any]]] = None,
        agent_name: Optional[str] = None,
        prompt_tokens: Optional[int] = 0,
        completion_tokens: Optional[int] = 0
    ):
        """
        添加一条消息到会话历史
        支持 trace_id, attachment files, 和 token 统计信息

        agent_name: 处理该轮的智能体，仅对 role="assistant" 生效
        用于后续路由的会话粘性（让追问沿用上一轮智能体）
        """
        redis = await get_redis()
        if not redis:
            logger.warning("[MemoryService] Redis client not available for add_message")
            return

        from datetime import datetime
        key = self._get_key(user_id, conversation_id)
        # 扩展消息体，包含 trace_id 和 files
        message = {
            "role": role, 
            "content": content,
            "trace_id": trace_id,
            "timestamp": datetime.now().isoformat()
        }
        if files:
            message["files"] = files
        if agent_name:
            message["agent_name"] = agent_name
        message["prompt_tokens"] = int(prompt_tokens or 0)
        message["completion_tokens"] = int(completion_tokens or 0)

        # push to list
        try:
            val = json.dumps(message, ensure_ascii=False)
            async with redis.pipeline() as pipe:
                await pipe.rpush(key, val)
                await pipe.ltrim(key, -self.max_history_len, -1)
                await pipe.expire(key, self.ttl)
                await pipe.execute()
            logger.info(f"[MemoryService] Added message to key: {key}. TraceID: {trace_id}")
        except Exception as e:
            logger.error(f"[MemoryService] Failed to add message to key {key}: {e}")

    async def get_last_data_result(self, user_id: str, conversation_id: str) -> Optional[Dict[str, Any]]:
        """
        检索最新的结构化 SQL 结果，以用于后续分析/图表请求
        :param user_id: 用户 ID
        :param conversation_id: 会话 ID
        :return: 最新的结构化 SQL 结果
        """
        redis = await get_redis()
        if not redis:
            return None
        
        key = self._get_data_result_key(user_id, conversation_id)
        try:
            raw = await redis.get(key)
            if not raw:
                return None
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else None
        except Exception as e:
            logger.error(f"[MemoryService] Failed to get last data result from key {key}: {e}")
            return None

    async def set_last_data_result(self, user_id: str, conversation_id: str, data_result: Dict[str, Any]):
        """
        设置最新的结构化 SQL 结果，以用于后续分析/图表请求
        :param user_id: 用户 ID
        :param conversation_id: 会话 ID
        :param data_result: 最新的结构化 SQL 结果
        """
        redis = await get_redis()
        if not redis:
            logger.warning("[MemoryService] Redis client not available for set_last_data_result")
            return
        
        key = self._get_data_result_key(user_id, conversation_id)
        try:
            await redis.setex(key, self.ttl, json.dumps(payload, ensure_ascii=False))
            logger.info(f"[MemoryService] Stored last data result for key: {key}")
        except Exception as e:
            logger.error(f"[MemoryService] Failed to set last data result for key {key}: {e}")

    async def clear_history(self, user_id: str, conversation_id: str):
        """
        清除会话历史
        :param user_id: 用户 ID
        :param conversation_id: 会话 ID
        """
        redis = await get_redis()
        if not redis:
            return
        key = self._get_key(user_id, conversation_id)
        logger.info(f"[MemoryService] Clearing history for key: {key}")
        await redis.delete(key)
        await redis.delete(self._get_data_result_key(user_id, conversation_id))

    async def delete_session_memory(self, user_id: str, conversation_id: str):
        """
        删除 LIST 历史记录和可选的摘要索引文档
        :param user_id: 用户 ID
        :param conversation_id: 会话 ID
        :return: 是否删除成功
        """
        redis = await get_redis()
        if not redis:
            return False
        key = self._get_key(user_id, conversation_id)
        logger.info(f"[MemoryService] Deleting session memory for key: {key}")
        await redis.delete(key)
        await redis.delete(self._get_data_result_key(user_id, conversation_id))
        return True

    async def history_exists(self, user_id: str, conversation_id: str) -> bool:
        redis = await get_redis()
        if not redis:
            return False
        return bool(await redis.exists(self._get_key(user_id, conversation_id)))

memory_service = MemoryService()

class LongTermMemoryService:
    """
    管理长期记忆
    使用 Redis HASH 来存储用户偏好、核心事实和配置文件。 
    关键模式：yunshu:agent:ltm:{user_id}
    """
    KEY_PREFIX = "yunshu:agent:ltm"

    def _get_key(self, user_id: str) -> str:
        uid = str(user_id) if user_id else "anonymous"
        return f"{self.KEY_PREFIX}:{uid}"

    async def update_preference(self, user_id: str, key: str, value: str) -> bool:
        """
        存储或更新用户的特定长期偏好/事实
        :param user_id: 用户 ID
        :param key: 偏好/事实的键
        :param value: 偏好/事实的值
        :return: 是否成功更新
        """
        redis = await get_redis()
        if not redis:
            logger.warning("[LTM] Redis client not available for update_preference")
            return False
        
        redis_key = self._get_key(user_id)
        try:
            await redis.hset(redis_key, key, value)
            logger.info(f"[LTM] Updated key '{key}' for user '{user_id}' in Redis.")
            return True
        except Exception as e:
            logger.error(f"[LTM] Failed to update preference for key {key}: {e}")
            return False

    async def fetch_memory(self, user_id: str) -> Dict[str, str]:
        """
        检索用户的特定长期偏好/事实
        :param user_id: 用户 ID
        :return: 偏好/事实的字典
        """
        redis = await get_redis()
        if not redis:
            logger.warning("[LTM] Redis client not available for fetch_memory")
            return {}

        redis_key = self._get_key(user_id)
        try:
            data = await redis.hgetall(redis_key)
            if not data:
                return {}

            result = {}
            for k, v in data.items():
                k_str = k.decode("utf-8") if isinstance(k, bytes) else str(k)
                v_str = v.decode("utf-8") if isinstance(v, bytes) else str(v)
                result[k_str] = v_str
            return result
        except Exception as e:
            logger.error(f"[LTM] Failed to fetch memory for user {user_id}: {e}")
            return {}
    
    async def delete_preference(self, user_id: str, key: str) -> bool:
        """
        Delete a specific long-term preference/fact for a user.
        """
        redis = await get_redis()
        if not redis:
            logger.warning("[LTM] Redis client not available for delete_preference")
            return False

        redis_key = self._get_key(user_id)
        try:
            await redis.hdel(redis_key, key)
            logger.info(f"[LTM] Deleted key '{key}' for user '{user_id}' in Redis.")
            return True
        except Exception as e:
            logger.error(f"[LTM] Failed to delete preference for key {key}: {e}")
            return False

ltm_service = LongTermMemoryService()
