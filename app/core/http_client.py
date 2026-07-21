"""
全局 HTTP 客户端, 用于异步 HTTP 请求。
"""

import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class GlobalHttpClient:
    _client: Optional[httpx.AsyncClient] = None

    @classmethod
    async def get_client(cls) -> httpx.AsyncClient:
        if cls._client is None:
            logger.info("Initializing Global HTTP Client (Singleton)")
            # HTTP 客户端连接参数
            limits = httpx.Limits(max_keepalive_connections=20, max_connections=100)
            timeout = httpx.Timeout(30.0, connect=5.0)
            cls._client = httpx.AsyncClient(limits=limits, timeout=timeout)

        return cls._client

@classmethod
async def close(cls):
    if cls._client:
        logger.info("Closing Global HTTP Client")
        await cls._client.aclose()
        cls._client = None