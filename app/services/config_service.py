"""
配置服务模块, 用于处理配置相关的数据库操作。
"""

import logging
import os
import time
from typing import Optional, Dict, List
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.orm import AsyncSessionLocal
from app.core.redis import get_redis
from app.core.config import settings
from app.services.auth_service import AuthService

logger = logging.getLogger(__name__)

CACHE_PREFIX = "sys_config:"
CACHE_TTL = 300

class ConfigService:
    """配置服务类"""
    # get_all_from_db 的内存缓存
    _all_configs_cache: Optional[Dict[str, dict]] = None
    _all_configs_last_fetched: float = 0
    _ALL_CONFIGS_TTL = 60.0

    @staticmethod
    async def get_all_from_db() -> Dict[str, dict]:
        """
        从数据库获取所有配置项
        
        :return: 所有配置项的字典, 键为配置项名称, 值为配置项值
        不使用短期记忆缓存
        """
        if ConfigService._all_configs_cache and (time.time() - ConfigService._all_configs_last_fetched < ConfigService._ALL_CONFIGS_TTL):
            return ConfigService._all_configs_cache

        async with AsyncSessionLocal() as session:
            result = await session.execute(text("SELECT `key`, `value`, `description`, `category`, `is_secret` FROM system_configs"))
            rows = result.fetchall()
            configs = {}
            for row in rows:
                configs[row[0]] = {
                    "value": row[1],
                    "description": row[2],
                    "category": row[3],
                    "is_secret": bool(row[4])
                }

            # 更新缓存
            ConfigService._all_configs_cache = configs
            ConfigService._all_configs_last_fetched = time.time()

            return configs

    @staticmethod
    async def get(key: str, default: Optional[str] = None) -> Optional[str]:
        """
        获取配置项值
        
        :param key: 配置项名称
        :param default: 如果配置项不存在, 则返回的默认值
        :return: 配置项值, 如果不存在则返回默认值
        """
        # 1. 检查 Redis
        redis = await get_redis()
        if redis:
            cached_val = await redis.get(f"{CACHE_PREFIX}{key}")
            if cached_val is not None:
                return cached_val

        # 2. 检查 DB
        db_val = None
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    text("SELECT value FROM system_configs WHERE `key` = :key"), 
                    {"key": key}
                )
                row = result.fetchone()
                if row:
                    db_val = row[0]
                    # 缓存到 Redis
                    if redis:
                        await redis.setex(f"{CACHE_PREFIX}{key}", CACHE_TTL, db_val)
        except Exception as e:
            logger.error(f"Failed to fetch config '{key}' from DB: {e}")

        if db_val is not None and db_val != "":
            return db_val

        # 3. 返回默认值
        return default

    @staticmethod
    async def set_config(
        key: str, 
        value: str, 
        description: Optional[str] = None, 
        category: str = "general", 
        is_secret: bool = False,
        changed_by: str = "system",
        change_reason: Optional[str] = None,
        db: Optional[AsyncSession] = None
    ):
        """
        设置配置项值
        
        :param key: 配置项名称
        :param value: 配置项值
        :param description: 配置项描述
        :param category: 配置项分类
        :param is_secret: 是否为敏感配置项
        :param changed_by: 变更人
        :param change_reason: 变更原因
        :param db: 自定义数据库会话, 如果未提供则使用默认会话
        :return: None
        """
        session, is_local = await AuthService._get_session(db)
        try:
            # 1. 获取历史配置项
            result = await session.execute(
                text("SELECT value FROM system_configs WHERE `key` = :key"), 
                {"key": key}
            )
            row = result.fetchone()
            old_value = row[0] if row else None
            change_type = "UPDATE" if row else "CREATE"

            # 2. 更新配置项
            # 注意：ON DUPLICATE KEY UPDATE 是 MySQL 特有的。
            sql = """
                INSERT INTO system_configs (`key`, `value`, `description`, `category`, `is_secret`)
                VALUES (:key, :value, :description, :category, :is_secret)
                ON DUPLICATE KEY UPDATE
                    `value` = VALUES(`value`),
                    `description` = COALESCE(VALUES(`description`), system_configs.`description`),
                    `category` = COALESCE(VALUES(`category`), system_configs.`category`),
                    `is_secret` = COALESCE(VALUES(`is_secret`), system_configs.`is_secret`)
            """
            await session.execute(text(sql), {
                "key": key, 
                "value": value, 
                "description": description, 
                "category": category, 
                "is_secret": is_secret
            })

            # 3. 插入审计日志
            # 只有当配置项值发生变化或者创建时才插入审计日志
            if old_value != value:
                audit_sql = """
                    INSERT INTO system_config_history 
                    (config_key, old_value, new_value, description, changed_by, change_type)
                    VALUES (:key, :old_value, :new_value, :audit_desc, :changed_by, :change_type)
                """
                # 如果可用，请使用提供的change_reason，否则使用描述，否则使用通用
                audit_desc = change_reason or description or "Config updated via set_config"

                await session.execute(text(audit_sql), {
                    "key": key, 
                    "old_value": old_value, 
                    "new_value": value, 
                    "audit_desc": audit_desc, 
                    "changed_by": changed_by, 
                    "change_type": change_type
                })

            await session.commit()

        except Exception:
            await session.rollback()
            raise
        finally:
            if is_local:
                await session.close()

        redis = await get_redis()
        if redis:
            await redis.setex(f"{CACHE_PREFIX}{key}", CACHE_TTL, value)
            logger.info(f"Config '{key}' updated in DB and Redis. Audit log created.")

        # 刷新缓存
        ConfigService._all_configs_cache = None

        return old_value != value

    @staticmethod
    async def get_all_configs_grouped() -> Dict[str, List[dict]]:
        """
        获取所有配置项, 按分类分组
        
        :return: 配置项字典, 键为分类, 值为配置项列表
        """
        configs = await ConfigService.get_all_from_db()
        grouped = {}

        for key, data in configs.items():
            cat = data["category"]
            if cat not in grouped:
                grouped[cat] = []

            # 过滤掉敏感配置项
            display_value = data["value"]
            if data["is_secret"] and display_value:
                if len(display_value) > 8:
                    display_value = display_value[:3] + "****" + display_value[-4:]
                else:
                    display_value = "****"

            grouped[cat].append({
                "key": key,
                "value": display_value, # Masked for display
                "description": data['description'],
                "is_secret": data['is_secret']
            })

        return grouped

    @staticmethod
    async def update_config_value(
        key: str,
        value: str,
        changed_by: str = "system",
        change_reason: Optional[str] = None) -> bool:
        """
        更新配置项值
        
        :param key: 配置项名称
        :param value: 配置项值
        :param changed_by: 变更人
        :param change_reason: 变更原因
        :return: 是否有变化
        """
        # 在 session 之外初始化 old_value
        old_value = None
        async with AsyncSessionLocal() as session:
            try:
                # 1. 获取旧值
                result = await session.execute(
                    text("SELECT value FROM system_configs WHERE `key` = :key"),
                    {"key": key}
                )
                row = result.fetchone()
                old_value = row[0] if row else None

                if old_value is None:
                    # 密钥不存在，我们必须使用 set_config 但由于我们在这里处于异步上下文管理器中，
                    # 我们可能应该关闭，或者只处理这里的逻辑。 
                    # 更简单的是返回并让调用者处理，还是递归调用？ 
                    # 由于我们处于会话内部，因此调用 set_config （创建新会话）是安全的，但效率低下。 
                    # 理想情况下我们复制逻辑。但现在，我们只是在退出会话后使用递归调用吗？
                    pass

                if old_value is not None:
                    # 2. 更新值
                    await session.execute(
                        text("UPDATE system_configs SET value = :value WHERE `key` = :key"),
                        {"value": value, "key": key}
                    )

                    # 3. 审计日志
                    if old_value != value:
                        audit_sql = """
                            INSERT INTO system_config_history 
                            (config_key, old_value, new_value, description, changed_by, change_type)
                            VALUES (:key, :old_value, :value, :audit_desc, :changed_by, 'UPDATE')
                        """
                        audit_desc = change_reason or "Value updated"
                        await session.execute(text(audit_sql), {
                            "key": key, 
                            "old_value": old_value, 
                            "value": value, 
                            "audit_desc": audit_desc, 
                            "changed_by": changed_by
                        })

                    await session.commit()
            except Exception:
                await session.rollback()
                raise
        
        if old_value is None:
            # 回退策略
            return await ConfigService.set_config(key, value, changed_by=changed_by, change_reason=change_reason)

        redis = await get_redis()
        if redis:
            await redis.setex(f"{CACHE_PREFIX}{key}", CACHE_TTL, value)
            logger.info(f"Config '{key}' updated in DB and Redis. Audit log created.")

        # 刷新缓存
        ConfigService._all_configs_cache = None

        return old_value != value

    @staticmethod
    async def bulk_update(updates: List[dict], changed_by: str = "system"):
        """
        批量更新配置项值
        
        :param updates: 配置项更新列表, 每个元素为 {'key': str, 'value': str, 'change_reason': Optional[str]}
        :param changed_by: 变更人
        :return: 是否有变化
        """
        for item in updates:
            key = item.get("key")
            value = item.get("value")
            if key is not None and value is not None:
                await ConfigService.update_config_value(key, value, changed_by=changed_by, change_reason="Bulk update")

    @staticmethod
    async def get_config_history(key: str, limit: int = 59) -> List[dict]:
        """
        获取配置项变更历史
        
        :param key: 配置项名称
        :param limit: 最大返回记录数
        :return: 配置项变更历史列表
        """
        async with AsyncSessionLocal() as session:
            sql = """
                SELECT id, config_key, old_value, new_value, description, changed_by, change_type, created_at
                FROM system_config_history
                WHERE config_key = :key
                ORDER BY created_at DESC
                LIMIT :limit
            """
            result = await session.execute(text(sql), {"key": key, "limit": limit})
            rows = result.fetchall()
            
            history = []
            for r in rows:
                history.append({
                    "id": r[0],
                    "config_key": r[1],
                    "old_value": r[2],
                    "new_value": r[3],
                    "description": r[4],
                    "changed_by": r[5],
                    "change_type": r[6],
                    "created_at": r[7].strftime("%Y-%m-%d %H:%M:%S") if r[7] else ""
                })
            return history
