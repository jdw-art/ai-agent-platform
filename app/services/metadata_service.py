"""
元数据服务
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update, or_, cast, String, Integer, func
from sqlalchemy.orm import selectinload
from typing import List, Optional, Dict, Any
import asyncio
import yaml
import logging
from app.models.metadata import MetaDataset, MetaTable, MetaColumn, MetaMetric, MetaRelationship
from app.services.ai.config import AgentConfigProvider
from app.services.changelog_service import ChangelogService


logger = logging.getLogger(__name__)

