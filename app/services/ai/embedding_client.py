"""Embedding API client for memory service (OpenAI-compatible)."""
import logging
from typing import List, Optional

import httpx

from app.services.config_service import ConfigService
from app.services.memory_config_service import MemoryConfigService

logger = logging.getLogger(__name__)

class EmbeddingClient:
    @staticmethod
    async def _resolve_credentials() -> tuple[str, str, str]:
        base_url = (await MemoryConfigService.get("memory_embedding_base_url") or "").strip()
        api_key = (await MemoryConfigService.get("memory_embedding_api_key") or "").strip()
        model = (await MemoryConfigService.get("memory_embedding_model") or "text-embedding-3-small").strip()

        if not base_url:
            base_url = (await ConfigService.get("llm_base_url") or "").strip()
        if not api_key:
            api_key = (await ConfigService.get("llm_api_key") or "").strip()
        return base_url.rstrip("/"), api_key, model

    @staticmethod
    async def embed_text(text: str) -> List[float]:
        """embedding text"""
        base_url, api_key, model = await EmbeddingClient._resolve_credentials()
        if not base_url or not api_key:
            raise RuntimeError("Embedding API 未配置：请在记忆管理中心配置 URL 与 Key")

        url = f"{base_url}/v1/embeddings" if not base_url.endswith("/embeddings") else base_url
        if "/v1/embeddings" not in url and not url.endswith("/embeddings"):
            url = f"{base_url}/v1/embeddings"

        payload = {"model": model, "input": [text]}
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        items = data.get("data") or []
        if not items:
            raise RuntimeError("Embedding API 返回空 data")
        embedding = items[0].get("embedding")
        if not embedding:
            raise RuntimeError("Embedding API 返回空 embedding")
        return [float(x) for x in embedding]

    @staticmethod
    async def get_dimensions() -> int:
        return await MemoryConfigService.get_int("memory_embedding_dimensions", 1536)