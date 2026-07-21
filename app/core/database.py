"""
数据库连接模块, 用于获取和管理数据库连接。
"""

from sqlalchemy import text
from typing import AsyncGenerator
from contextlib import asynccontextmanager
from app.core.orm import engine
import logging

# Configure logger
logger = logging.getLogger(__name__)

@asynccontextmanager
async def get_db_connection():
    """
    从 SQLAlchemy 引擎获取数据库连接
    使用连接池管理数据库连接
    """
    async with engine.connect() as conn:
        # 获取数据库连接
        raw_conn = await conn.get_raw_connection()

        yield raw_conn

async def init_db():
    """
    Ping 数据库连接，确保数据库连接正常
    连接池由 SQLAlchemy 引擎管理
    """
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            logger.info("✅ Database health check passed (via SQLAlchemy Engine)")
    except Exception as e:
        logger.error(f"❌ Database health check failed: {e}")
        raise

async def close_db():
    """
    关闭数据路连接
    """
    await engine.dispose()
    logger.info("✅ Database engine disposed")