import logging
from pyexpat import model
import select
from typing import Optional, Dict
from app.core.context import get_debug_option
from app.core.orm import AsyncSessionLocal
from app.models.ai_model import AIModel
from app.schemas.agent import ChatConfig
from app.core.llm.client import get_llm
from app.services.config_service import ConfigService

logger = logging.getLogger(__name__)

class AgentConfigProvider:
    """
    处理 Agent 的 LLM 实例和环境配置
    """

    @staticmethod
    async def get_configured_llm(
        streaming: bool = True,
        config: Optional[ChatConfig] = None,
        model_override: Optional[str] = None,
        temp_override: Optional[float] = None
    ):
        """
        基于系统配置实例化 AgentScope LLM，指定 Agent 重写，或 runtime 重写
        优先级：
        1. 运行时覆盖（来自工具运行时配置的 model_override/temp_override）
        2. 调试选项（用户会话调试）
        3. 代理配置（ChatConfig）
        4. 系统默认设置
        """

        # 从 DB 获取动态配置
        llm_config = await ConfigService.get_all_from_db()

        def get_val(key, default):
            return llm_config.get(key, {}).get("value") or default

        # 检查 Debug 上下文
        # 1. 模型名
        debug_model = get_debug_option("model")

        if model_override:
            model = model_override
        elif debug_model:
            model = debug_model
        elif config and config.model_name:
            model = config.model_name
        else:
            model = get_val("llm_model_name", "gpt-5.4")

        # 2. 温度
        debug_temp = get_debug_option("temperature")

        if temp_override is not None:
            temperature = temp_override
        elif debug_temp is not None:
            temperature = float(debug_temp)
        elif config and config.temperature is not None:
            temperature = float(config.temperature)
        else:
            temp_str = get_val("llm_temperature", None)
            temperature = float(temp_str) if temp_str is not None else 0.0

        api_key = get_val("llm_api_key", None)
        base_url = get_val("llm_base_url", None)

        # 3. 模型管理注册表查找
        # 如果选定的“模型”字符串与 ai_models 表中的条目相对应，
        # 则使用其特定的凭据（如果可用）。
        # 这允许为每个模型设置 API 密钥/BaseURL。
        try:
            from app.core.orm import AsyncSessionLocal
            from app.models.ai_model import AIModel
            from sqlalchemy import select, or_

            async with AsyncSessionLocal() as session:
                # 根据模型名和ID查找有效的model
                stmt = select(AIModel).where(
                    AIModel.is_active == True,
                    or_(AIModel.model_id == model, AIModel.name == model)
                )
                result = await session.execute(stmt)
                ai_model = result.scalars().first()

                if ai_model:
                    # 获取已注册的模型，检查是否需要重写 API 密钥/BaseURL
                    if ai_model.api_key:
                        api_key = ai_model.api_key
                    if ai_model.base_url:
                        base_url = ai_model.api_base_url

                    # 将模型字符串更新为提供者所需的实际 model_id
                    #（例如用户选择“My GPT4”，充当“gpt-4o”）
                    model = ai_model.model_id
        except Exception as e:
            logger.warning(f"Failed to lookup model registry: {e}")

        return get_llm(
            streaming=streaming,
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=temperature
        )

    @staticmethod
    async def get_synthesis_llm(
        streaming: bool = True, 
        config: Optional[ChatConfig] = None
    ):
        """
        专门为综合（最终响应）阶段实例化 LLM。
        回退逻辑：
        1. 综合阶段专用配置（synthesis_model_name）
        2. 主代理配置（model_name）
        3. 系统默认值
        """
        if config and config.synthesis_model_name:
            # 使用合成特定的覆盖
            return await AgentConfigProvider.get_configured_llm(
                streaming=streaming,
                config=config,
                model_override=config.synthesis_model_name,
                temp_override=config.synthesis_temperature
            )

        # 回退到主模型
        return await AgentConfigProvider.get_configured_llm(
            streaming=streaming,
            config=config
        )

    @staticmethod
    async def get_fallback_llm(
        streaming: bool = True,
        config: Optional[ChatConfig] = None,
        exclude_model: Optional[str] = None
    ):
        """
        回退到默认模型
        """
        try:
            llm_config = await ConfigService.get_all_from_db()
        except Exception:
            llm_config = {}

        def get_val(key, default=None):
            return llm_config.get(key, {}).get("value") or default

        candidate = get_val("llm_model_name")
        if not candidate or (exclude_model and candidate == exclude_model):
            return None
        try:
            return await AgentConfigProvider.get_configured_llm(
                streaming=streaming,
                config=config,
                model_override=candidate,
            )
        except Exception:
            return None

    @staticmethod
    async def _generate_dataset_menu_content(user_id: Optional[int] = None, is_admin: bool = False) -> str:
        """
        从数据库生成数据集菜单字符串的内部方法，按权限和状态进行过滤
        """
        menu = "Available Datasets (Look for Table terms to find relevant data):\n"
        try:
            from app.core.orm import AsyncSessionLocal
            from app.models.metadata import MetaDataset
            from app.services.metadata_service import MetadataService
            from sqlalchemy.orm import selectinload

            async with AsyncSessionLocal() as session:
                # 使用 MetadataService.search_datasets 进行权限和状态过滤 (status=1 为启用)
                datasets = await MetadataService.search_datasets(
                    session,
                    query=None,
                    user_id=user_id,
                    is_admin=is_admin,
                    status=1 # 仅限启用状态
                )
                if not datasets:
                    return menu + f"  (No datasets datasets available)"
                else:
                    for ds in datasets:
                        name = getattr(ds, "name", "unknown")
                        desc = getattr(ds, "description", "No description")
                        tags = getattr(ds, "tags", [])

                        # 提取表信息
                        table_terms = []
                        # search_datasets 返回的对象可能没有预加载 tables，视情况处理
                        if hasattr(ds, "tables") and ds.tables:
                            for tbl in ds.tables:
                                term = getattr(tbl, "term", tbl.physical_name)
                                table_terms.append(term)

                        tag_str = f" [{', '.join(tags)}]" if isinstance(tags, list) and tags else ""
                        menu += f"- Dataset: {name}{tag_str}\n  Description: {desc}\n"
                        if table_terms:
                            menu += f"  Includes Tables: {', '.join(table_terms)}\n"
                        menu += "\n"
                    return menu
        except Exception as e:
            logger.error(f"Failed to load dataset menu internally: {e}")
            return menu + f"  (System Error: Failed to load dataset menu)"

    @staticmethod
    async def get_dataset_menu(user_id: Optional[int] = None, is_admin: bool = False) -> str:
        """
        获取已授权的数据集以辅助 LLM 推理。每个用户通过 Redis 缓存。
        """
        from app.core.redis import get_redis
        redis = await get_redis()
        
        # 1. Try Cache (按用户隔离，admin 共享一个 key)
        cache_key = f"agent:dataset_menu:{'admin' if is_admin else user_id or 'anon'}"
        try:
            if redis:
                cached_menu = await redis.get(cache_key)
                if cached_menu:
                    return cached_menu
        except Exception as e:
            logger.warning(f"Redis error for dataset menu: {e}")

        # 2. Cache Miss: Fetch from DB
        content = await AgentConfigProvider._generate_dataset_menu_content(user_id, is_admin)

        # 3. Save to Cache (TTL: 10 mins)
        try:
            if redis:
                await redis.set(cache_key, content, ex=600)
        except Exception as e:
            logger.warning(f"Redis set error: {e}")
        
        return content

    @staticmethod
    async def refresh_dataset_menu():
        """
        Force regenerate the dataset menu and update Redis cache.
        Should be called when datasets or tables are modified.
        """
        from app.core.redis import get_redis
        try:
            content = await AgentConfigProvider._generate_dataset_menu_content()
            redis = await get_redis()
            if redis:
                await redis.set("agent:dataset_menu", content, ex=600)
                logger.info("Dataset menu cache refreshed.")
        except Exception as e:
            logger.error(f"Failed to refresh dataset menu cache: {e}")