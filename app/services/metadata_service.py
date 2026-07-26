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

class MetadataService:
    """
    元数据服务
    """

    @staticmethod
    async def get_datasets(db: AsyncSession) -> List[MetaDataset]:
        """获取数据集"""
        stmt = select(MetaDataset).options(
            selectinload(MetaDataset.tables),
            selectinload(MetaDataset.metrics)
        )
        result = await db.execute(stmt)
        datasets = result.scalars().all()

        # 数量统计
        for ds in datasets:
            ds.table_count = len(ds.tables)
            ds.metric_count = len(ds.metrics)
            # 关系计数：关系并非直接存在于数据集中，而是派生自表
            # 在循环中执行此操作可能会很耗时。对于列表视图，或许我们可以跳过或执行单独的计数查询？
            # 或者假设我们只需要列表视图的表/指标计数？
            # 请求要求“卡片上的数字标签：表计数、指标计数、关系计数”。
            # 因此我们需要它。让我们分别快速查询或进行优化。
            # 优化：获取此数据集的所有表 ID

            table_ids = [t.id for t in ds.tables]
            ds.relationship_count = 0
            if table_ids:
                # 我们需要一种同步方法，或者在循环中使用 await。循环中使用 await 对于 N<50 的数据集来说是可以接受的。
                # 但是 SQLAlchemy 对象在异步会话中……
                # 更好的办法：预先获取所有关系，或者使用计数查询。
                rel_count_stmt = select(func.count(MetaRelationship.id)).where(
                    (MetaRelationship.source_table_id.in_(table_ids)) |
                    (MetaRelationship.target_table_id.in_(table_ids))
                )
                # 如果直接返回列表，我们就无法在同步迭代中使用 await。
                # 我们需要将结构改为异步循环。
                pass

        for ds in datasets:
            ds.table_count = len(ds.tables)
            ds.metric_count = len(ds.metrics)

            table_ids = [t.id for t in ds.tables]
            if table_ids:
                rel_count_stmt = select(func.count(MetaRelationship.id)).where(
                    (MetaRelationship.source_table_id.in_(table_ids)) |
                    (MetaRelationship.target_table_id.in_(table_ids))
                )
                rel_count = await db.scalar(rel_count_stmt)
                ds.relationship_count = rel_count or 0
            else:
                ds.relationship_count = 0

        return datasets

    @staticmethod
    async def get_dataset_by_id(
        db: AsyncSession,
        dataset_id: int,
        user_id: Optional[int] = None,
        is_admin: bool = False
    ) -> Optional[MetaDataset]:
        """根据id获取可用数据集"""
        stmt = select(MetaDataset).where(MetaDataset.id == dataset_id)

        # 1. 权限检查
        if not is_admin and user_id is not None:
            from app.models.permission import ResourcePermission, UserRoleRelation

            # 子查询，找到用户的 role ids
            user_roles_stmt = select(UserRoleRelation.role_id).where(UserRoleRelation.user_id == user_id)

            # 子查询，检查当前用户是否有该数据集的权限
            permitted_stmt = select(ResourcePermission.id).where(
                ResourcePermission.resource_type == 'metadata',
                ResourcePermission.resource_id == str(dataset_id),
                ResourcePermission.enabled == True,
                or_(
                    ResourcePermission.user_id == user_id,
                    ResourcePermission.role_id.in_(user_roles_stmt)
                )
            )

            # 过滤
            stmt = stmt.where(permitted_stmt.exists())

        result = await db.execute(
            stmt.options(
                selectinload(MetaDataset.tables).selectinload(MetaTable.columns),
                selectinload(MetaDataset.metrics)
            )
        )

        ds = result.scalar_one_or_none()

        if ds:
            # 手动填充关系
            ds.relationships = await MetadataService.get_relationships_by_dataset(db, dataset_id)
            
            # Populate counts
            ds.table_count = len(ds.tables)
            ds.metric_count = len(ds.metrics)
            ds.relationship_count = len(ds.relationships)

        return ds

    @staticmethod
    async def search_datasets(
        db: AsyncSession, 
        keyword: Optional[str] = None, # Changed param name to match usage, or keep as 'query'? Original was 'keyword' in this file but 'query' in others. Let's align with call usage. data_api calls with `query=dataset_name` passed to `search_datasets(..., query=...)`. Wait, data_api calls `search_datasets(session, query=dataset_name, ...)`. The signature in data_api call is `query`. The signature in this file was `keyword`.
        # Let's standardize on `query` to match the caller in data_api.py update.
        query: Optional[str] = None,
        status: int = 1,
        user_id: Optional[int] = None,
        is_admin: bool = False
    ):
        """查询数据集"""
        stmt = select(MetaDataset).where(MetaDataset.status == status)

        # 1. 权限过滤
        if not is_admin and user_id is not None:
            from app.models.permission import ResourcePermission, UserRoleRelation

            # 子查询，找到用户的 role ids
            user_roles_stmt = select(UserRoleRelation.role_id).where(UserRoleRelation.user_id == user_id)

            # 子查询，检查当前用户是否有该数据集的权限
            permitted_ids_stmt = select(cast(ResourcePermission.resource_id, Integer)).where(
                ResourcePermission.resource_type == 'metadata',
                ResourcePermission.enabled == True,
                or_(
                    ResourcePermission.user_id == user_id,
                    ResourcePermission.role_id.in_(user_roles_stmt)
                )
            )

            # 过滤
            stmt = stmt.where(MetaDataset.id.in_(permitted_ids_stmt))

        # 2. 搜索过滤
        if query:
            stmt = stmt.where(or_(
                MetaDataset.name.ilike(f"%{query}%"),
                MetaDataset.display_name.ilike(f"%{query}%")
            ))

        # Pre-load tables to avoid DetachedInstanceError in external loops
        stmt = stmt.options(selectinload(MetaDataset.tables))
            
        result = await db.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_dataset_by_name(db: AsyncSession, name: str) -> Optional[MetaDataset]:
        result = await db.execute(
            select(MetaDataset).where(MetaDataset.name == name)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def _mark_dataset_as_modified(db: AsyncSession, dataset_id: int):
        """
        标记数据集为“带同步”状态（3）
        仅当前状态不是“同步中”（1）时才更新
        """
        # 查找当前状态
        stmt = select(MetaDataset.rag_sync_status).where(MetaDataset.id == dataset_id)
        current_status = await db.scalar(stmt)
        
        if current_status != 1:
            query = update(MetaDataset).where(MetaDataset.id == dataset_id).values(rag_sync_status=3)
            await db.execute(query)
            # 注意：调用者负责最后的 commit

    @staticmethod
    async def create_dataset(
        db: AsyncSession,
        data: dict,
        user_id: Optional[int] = None,
        user_name: Optional[str] = None,
        reason: Optional[str] = None
    ) -> MetaDataset:
        """
        创建数据集
        """
        dataset = MetaDataset(**data)
        db.add(dataset)
        await db.flush()  # 获取ID但不提交

        # 记录变更日志
        new_data = {
            "id": dataset.id,
            "name": dataset.name,
            "display_name": dataset.display_name,
            "description": dataset.description,
            "tags": dataset.tags,
            "data_source": dataset.data_source,
            "status": dataset.status
        }

        await ChangelogService.log_change(
            db=db,
            resource_type="dataset",
            resource_id=str(dataset.id),
            operation="create",
            user_id=user_id,
            user_name=user_name,
            new_data=new_data,
            reason=reason
        )

        await db.commit()
        await db.refresh(dataset)
        await AgentConfigProvider.refresh_dataset_menu()
        return dataset

    @staticmethod
    async def update_dataset(
        db: AsyncSession,
        dataset_id: int,
        data: dict,
        user_id: Optional[int] = None,
        user_name: Optional[str] = None,
        reason: Optional[str] = None
    ) -> MetaDataset:
        """
        更新数据集
        """
        # 获取更新前的数据
        old_dataset = await MetadataService.get_dataset_by_id(db, dataset_id, is_admin=True)
        old_data = None
        if old_dataset:
            old_data = {
                "id": old_dataset.id,
                "name": old_dataset.name,
                "display_name": old_dataset.display_name,
                "description": old_dataset.description,
                "tags": old_dataset.tags,
                "data_source": old_dataset.data_source,
                "status": old_dataset.status
            }
        
        query = update(MetaDataset).where(MetaDataset.id == dataset_id).values(**data)
        await db.execute(query)
        await MetadataService._mark_dataset_as_modified(db, dataset_id)
        
        # 记录变更日志
        new_dataset = await MetadataService.get_dataset_by_id(db, dataset_id, is_admin=True)
        if new_dataset and old_data:
            new_data = {
                "id": new_dataset.id,
                "name": new_dataset.name,
                "display_name": new_dataset.display_name,
                "description": new_dataset.description,
                "tags": new_dataset.tags,
                "data_source": new_dataset.data_source,
                "status": new_dataset.status
            }
            await ChangelogService.log_change(
                db=db,
                resource_type="dataset",
                resource_id=str(dataset_id),
                operation="update",
                user_id=user_id,
                user_name=user_name,
                old_data=old_data,
                new_data=new_data,
                reason=reason
            )
        
        await db.commit()
        return await MetadataService.get_dataset_by_id(db, dataset_id, is_admin=True)

    @staticmethod
    async def delete_dataset(
        db: AsyncSession,
        dataset_id: int,
        user_id: Optional[int] = None,
        user_name: Optional[str] = None,
        reason: Optional[str] = None
    ):
        """
        删除数据集
        """
        # 1. 检查数据集是否存在
        old_dataset = await MetadataService.get_dataset_by_id(db, dataset_id, is_admin=True)
        old_data = None
        if old_dataset:
            old_data = {
                "id": old_dataset.id,
                "name": old_dataset.name,
                "display_name": old_dataset.display_name,
                "description": old_dataset.description,
                "tags": old_dataset.tags,
                "data_source": old_dataset.data_source,
                "status": old_dataset.status
            }

        # 2. 获取 RAG id
        result = await db.execute(select(MetaDataset.rag_dataset_id).where(MetaDataset.id == dataset_id))
        rag_kb_id = result.scalar_one_or_none()

        # 3. 删除
        query = delete(MetaDataset).where(MetaDataset.id == dataset_id)
        await db.execute(query)

        # 4. 记录变更日志
        if old_data:
            await ChangelogService.log_change(
                db=db,
                resource_type="dataset",
                resource_id=str(dataset_id),
                operation="delete",
                user_id=user_id,
                user_name=user_name,
                old_data=old_data,
                reason=reason
            )
        
        await db.commit()
        await AgentConfigProvider.refresh_dataset_menu()

        # 5. 同步删除 RAGFlow KB
        if rag_kb_id:
            from app.services.metadata_rag_service import MetadataRagService
            asyncio.create_task(MetadataRagService.delete_rag_dataset(rag_kb_id))

    # --- Table/Column CRUD (Simplified for now) ---
    @staticmethod
    async def save_table_metadata(db: AsyncSession, dataset_id: int, table_data: dict, user_id: Optional[int] = None, user_name: Optional[str] = None, reason: Optional[str] = None) -> MetaTable:
        """
        保存或更新表元数据
        table_data expects: 
        {
          "physical_name": "res_room",
          "term": "机房表",
          "columns": [...]
        }
        """
        # 1. 检查表是否存在
        result = await db.execute(
            select(MetaTable).where(
                MetaTable.dataset_id == dataset_id,
                MetaTable.physical_name == table_data['physical_name']
            )
        )
        existing_table = result.scalar_one_or_none()
        
        # 2. 获取旧数据用于变更日志
        old_data = None
        operation = "create"
        if existing_table:
            operation = "update"
            # 加载旧表数据，包含列
            old_table_result = await db.execute(
                select(MetaTable)
                .options(selectinload(MetaTable.columns))
                .where(MetaTable.id == existing_table.id)
            )
            old_table_with_cols = old_table_result.scalar_one()
            
            old_data = {
                "physical_name": old_table_with_cols.physical_name,
                "term": old_table_with_cols.term,
                "description": old_table_with_cols.description,
                "synonyms": old_table_with_cols.synonyms,
                "columns": [
                    {
                        "physical_name": col.physical_name,
                        "term": col.term,
                        "type": col.type,
                        "description": col.description,
                        "enums": col.enums,
                        "synonyms": col.synonyms
                    }
                    for col in old_table_with_cols.columns
                ]
            }
        
        if existing_table:
            # Update Table
            existing_table.term = table_data.get('term', existing_table.term)
            existing_table.description = table_data.get('description', existing_table.description)
            existing_table.synonyms = table_data.get('synonyms', existing_table.synonyms)
        else:
            # Create Table
            existing_table = MetaTable(
                dataset_id=dataset_id,
                physical_name=table_data['physical_name'],
                term=table_data.get('term', table_data['physical_name']),
                description=table_data.get('description', ''),
                synonyms=table_data.get('synonyms', [])
            )
            db.add(existing_table)
            await db.flush() # flush to get ID
            
        # 2. Handle Columns (Upsert + Delete stale)
        incoming_col_names = [col['physical_name'] for col in table_data.get('columns', [])]
        
        # Delete columns that are NOT in the incoming list
        delete_stmt = delete(MetaColumn).where(
            MetaColumn.table_id == existing_table.id,
            MetaColumn.physical_name.not_in(incoming_col_names)
        )
        await db.execute(delete_stmt)

        current_cols = table_data.get('columns', [])
        for col_data in current_cols:
             result_col = await db.execute(
                 select(MetaColumn).where(
                     MetaColumn.table_id == existing_table.id,
                     MetaColumn.physical_name == col_data['physical_name']
                 )
             )
             existing_col = result_col.scalar_one_or_none()
             
             if existing_col:
                 # Update
                 existing_col.term = col_data.get('term', existing_col.term)
                 existing_col.description = col_data.get('description', existing_col.description)
                 existing_col.enums = col_data.get('enums', existing_col.enums)
                 existing_col.synonyms = col_data.get('synonyms', existing_col.synonyms)
             else:
                 # Create
                 new_col = MetaColumn(
                     table_id=existing_table.id,
                     physical_name=col_data['physical_name'],
                     term=col_data.get('term', col_data['physical_name']),
                     type=col_data.get('type', 'String'),
                     description=col_data.get('description', ''),
                     enums=col_data.get('enums', []),
                     synonyms=col_data.get('synonyms', [])
                 )
                 db.add(new_col)
        
        await MetadataService._mark_dataset_as_modified(db, dataset_id)
        
        # 3. Record changelog for table operation
        new_data = {
            "physical_name": existing_table.physical_name,
            "term": existing_table.term,
            "description": existing_table.description,
            "synonyms": existing_table.synonyms,
            "columns": table_data.get('columns', [])
        }
        
        await ChangelogService.log_change(
            db=db,
            resource_type="table",
            resource_id=f"{dataset_id}:{existing_table.physical_name}",
            operation=operation,
            user_id=user_id,
            user_name=user_name,
            old_data=old_data,
            new_data=new_data,
            reason=reason or f"{operation}表 {existing_table.physical_name}"
        )
        
        await db.commit()
        # Reload with columns
        result = await db.execute(
            select(MetaTable)
            .options(selectinload(MetaTable.columns))
            .where(MetaTable.id == existing_table.id)
        )
        await AgentConfigProvider.refresh_dataset_menu()
        return result.scalar_one()

    @staticmethod
    async def delete_table_metadata(db: AsyncSession, dataset_id: int, table_name: str, user_id: Optional[int] = None, user_name: Optional[str] = None, reason: Optional[str] = None):
        """
        删除表元数据
        table_name: 表物理名称
        user_id: 用户ID
        user_name: 用户名称
        reason: 操作原因
        """
        # 1. Get old data BEFORE delete
        old_table_result = await db.execute(
            select(MetaTable)
            .options(selectinload(MetaTable.columns))
            .where(MetaTable.dataset_id == dataset_id, MetaTable.physical_name == table_name)
        )
        old_table = old_table_result.scalar_one_or_none()
        old_data = None
        table_id_str = table_name
        if old_table:
            table_id_str = f"{dataset_id}:{old_table.physical_name}"
            old_data = {
                "physical_name": old_table.physical_name,
                "term": old_table.term,
                "description": old_table.description,
                "synonyms": old_table.synonyms,
                "columns": [
                    {"physical_name": col.physical_name, "term": col.term, "type": col.type}
                    for col in old_table.columns
                ]
            }

        # 2. Delete
        query = delete(MetaTable).where(
            MetaTable.dataset_id == dataset_id,
            MetaTable.physical_name == table_name
        )
        await db.execute(query)
        await MetadataService._mark_dataset_as_modified(db, dataset_id)

        # 3. Record changelog
        if old_data:
            await ChangelogService.log_change(
                db=db,
                resource_type="table",
                resource_id=table_id_str,
                operation="delete",
                user_id=user_id,
                user_name=user_name,
                old_data=old_data,
                reason=reason or f"删除表 {table_name}"
            )

        await db.commit()
        await AgentConfigProvider.refresh_dataset_menu()


    # --- Metrics CRUD ---

    @staticmethod
    async def create_metric(db: AsyncSession, dataset_id: int, data: dict, user_id: Optional[int] = None, user_name: Optional[str] = None, reason: Optional[str] = None) -> MetaMetric:
        """
        创建指标元数据
        data expects: 
        {
            "name": "room_count",
            "display_name": "房间数量",
            "description": "房间数量",
            "calculation_logic": "SUM(room_count)",
            "unit": "个"
        }
        user_id: 用户ID
        user_name: 用户名称
        reason: 操作原因
        """
        # Check uniqueness and handle Upsert
        result = await db.execute(
            select(MetaMetric).where(
                MetaMetric.dataset_id == dataset_id,
                MetaMetric.name == data['name']
            )
        )
        existing_metric = result.scalar_one_or_none()
        
        if existing_metric:
            # Update Existing
            logger.info(f"Metric '{data['name']}' already exists in dataset {dataset_id}. Updating fields.")
            existing_metric.display_name = data.get('display_name', existing_metric.display_name)
            existing_metric.description = data.get('description', existing_metric.description)
            existing_metric.calculation_logic = data.get('calculation_logic', existing_metric.calculation_logic)
            existing_metric.unit = data.get('unit', existing_metric.unit)
            existing_metric.updated_at = datetime.now()
            await MetadataService._mark_dataset_as_modified(db, dataset_id)
            await db.commit()
            await db.refresh(existing_metric)
            return existing_metric

        # Create New
        metric = MetaMetric(dataset_id=dataset_id, **data)
        db.add(metric)
        await MetadataService._mark_dataset_as_modified(db, dataset_id)
        
        # Record changelog for metric creation
        new_data = {
            "name": metric.name,
            "display_name": metric.display_name,
            "description": metric.description,
            "calculation_logic": metric.calculation_logic,
            "unit": metric.unit
        }
        
        await ChangelogService.log_change(
            db=db,
            resource_type="metric",
            resource_id=str(metric.name),
            operation="create",
            user_id=user_id,
            user_name=user_name,
            new_data=new_data,
            reason=reason or f"创建指标 {metric.name}"
        )
        
        await db.commit()
        await db.refresh(metric)
        return metric

    @staticmethod
    async def get_metrics_by_dataset(db: AsyncSession, dataset_id: int) -> List[MetaMetric]:
        result = await db.execute(
            select(MetaMetric).where(MetaMetric.dataset_id == dataset_id)
        )
        return result.scalars().all()

    @staticmethod
    async def update_metric(db: AsyncSession, metric_id: int, data: dict, user_id: Optional[int] = None, user_name: Optional[str] = None, reason: Optional[str] = None) -> Optional[MetaMetric]:
        # Need dataset_id to mark modified
        res = await db.execute(select(MetaMetric.dataset_id).where(MetaMetric.id == metric_id))
        dataset_id = res.scalar_one_or_none()

        query = update(MetaMetric).where(MetaMetric.id == metric_id).values(**data)
        await db.execute(query)
        
        # Record changelog for metric update
        # Get old data before update
        old_metric_result = await db.execute(select(MetaMetric).where(MetaMetric.id == metric_id))
        old_metric = old_metric_result.scalar_one_or_none()
        
        if old_metric and dataset_id:
            old_data = {
                "name": old_metric.name,
                "display_name": old_metric.display_name,
                "description": old_metric.description,
                "calculation_logic": old_metric.calculation_logic,
                "unit": old_metric.unit
            }
            
            new_data = {
                "name": data.get('name', old_metric.name),
                "display_name": data.get('display_name', old_metric.display_name),
                "description": data.get('description', old_metric.description),
                "calculation_logic": data.get('calculation_logic', old_metric.calculation_logic),
                "unit": data.get('unit', old_metric.unit)
            }
            
            await ChangelogService.log_change(
                db=db,
                resource_type="metric",
                resource_id=str(old_metric.name),
                operation="update",
                user_id=user_id,
                user_name=user_name,
                old_data=old_data,
                new_data=new_data,
                reason=reason or f"更新指标 {old_metric.name}"
            )
        
        if dataset_id:
            await MetadataService._mark_dataset_as_modified(db, dataset_id)
            
        await db.commit()
        
        result = await db.execute(select(MetaMetric).where(MetaMetric.id == metric_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def delete_metric(db: AsyncSession, metric_id: int, user_id: Optional[int] = None, user_name: Optional[str] = None, reason: Optional[str] = None):
        # 1. Get old data BEFORE delete
        old_metric_result = await db.execute(select(MetaMetric).where(MetaMetric.id == metric_id))
        old_metric = old_metric_result.scalar_one_or_none()

        res = await db.execute(select(MetaMetric.dataset_id).where(MetaMetric.id == metric_id))
        dataset_id = res.scalar_one_or_none()

        # 2. Delete
        query = delete(MetaMetric).where(MetaMetric.id == metric_id)
        await db.execute(query)

        # 3. Record changelog (old_metric was fetched BEFORE delete)
        if old_metric:
            old_data = {
                "name": old_metric.name,
                "display_name": old_metric.display_name,
                "description": old_metric.description,
                "calculation_logic": old_metric.calculation_logic,
                "unit": old_metric.unit
            }
            await ChangelogService.log_change(
                db=db,
                resource_type="metric",
                resource_id=str(old_metric.name),
                operation="delete",
                user_id=user_id,
                user_name=user_name,
                old_data=old_data,
                reason=reason or f"删除指标 {old_metric.name}"
            )

        if dataset_id:
            await MetadataService._mark_dataset_as_modified(db, dataset_id)

        await db.commit()

    # --- Relationships CRUD ---

    @staticmethod
    async def create_relationship(db: AsyncSession, dataset_id: int, data: dict, user_id: Optional[int] = None, user_name: Optional[str] = None, reason: Optional[str] = None) -> MetaRelationship:
        rel = MetaRelationship(**data)
        db.add(rel)
        await db.flush()  # 先 flush 获取自增 ID，避免 changelog resource_id 为 None
        await MetadataService._mark_dataset_as_modified(db, dataset_id)
        
        # Record changelog for relationship creation
        new_data = {
            "source_table_id": rel.source_table_id,
            "target_table_id": rel.target_table_id,
            "join_condition": rel.join_condition,
            "join_type": rel.join_type,
            "description": rel.description
        }
        
        await ChangelogService.log_change(
            db=db,
            resource_type="relationship",
            resource_id=str(rel.id),
            operation="create",
            user_id=user_id,
            user_name=user_name,
            new_data=new_data,
            reason=reason or f"创建关系 {rel.source_table_id}->{rel.target_table_id}"
        )
        
        await db.commit()
        await db.refresh(rel)
        return rel

    @staticmethod
    async def get_relationships_by_dataset(db: AsyncSession, dataset_id: int) -> List[MetaRelationship]:
        # Find all relationships where source OR target table belongs to this dataset
        # This requires a JOIN
        
        # 1. Get Table IDs in this dataset
        stmt = select(MetaTable.id).where(MetaTable.dataset_id == dataset_id)
        result = await db.execute(stmt)
        table_ids = result.scalars().all()
        
        if not table_ids:
            return []
            
        # 2. Find relations
        stmt = select(MetaRelationship).where(
            (MetaRelationship.source_table_id.in_(table_ids)) | 
            (MetaRelationship.target_table_id.in_(table_ids))
        )
        result = await db.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def update_relationship(db: AsyncSession, rel_id: int, data: dict, user_id: Optional[int] = None, user_name: Optional[str] = None, reason: Optional[str] = None) -> Optional[MetaRelationship]:
        # Find dataset_id and old data
        res = await db.execute(
            select(MetaTable.dataset_id)
            .join(MetaRelationship, MetaTable.id == MetaRelationship.source_table_id)
            .where(MetaRelationship.id == rel_id)
        )
        dataset_id = res.scalar_one_or_none()

        # Get old data BEFORE update
        old_rel_result = await db.execute(select(MetaRelationship).where(MetaRelationship.id == rel_id))
        old_rel = old_rel_result.scalar_one_or_none()
        old_data = None
        if old_rel:
            old_data = {
                "source_table_id": old_rel.source_table_id,
                "target_table_id": old_rel.target_table_id,
                "join_condition": old_rel.join_condition,
                "join_type": old_rel.join_type,
                "description": old_rel.description
            }

        query = update(MetaRelationship).where(MetaRelationship.id == rel_id).values(**data)
        await db.execute(query)

        # Record changelog
        if old_data:
            new_data = {
                "source_table_id": data.get("source_table_id", old_rel.source_table_id),
                "target_table_id": data.get("target_table_id", old_rel.target_table_id),
                "join_condition": data.get("join_condition", old_rel.join_condition),
                "join_type": data.get("join_type", old_rel.join_type),
                "description": data.get("description", old_rel.description)
            }
            await ChangelogService.log_change(
                db=db,
                resource_type="relationship",
                resource_id=str(rel_id),
                operation="update",
                user_id=user_id,
                user_name=user_name,
                old_data=old_data,
                new_data=new_data,
                reason=reason or f"更新关系 {rel_id}"
            )

        if dataset_id:
            await MetadataService._mark_dataset_as_modified(db, dataset_id)

        await db.commit()

        result = await db.execute(select(MetaRelationship).where(MetaRelationship.id == rel_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def delete_relationship(db: AsyncSession, rel_id: int, user_id: Optional[int] = None, user_name: Optional[str] = None, reason: Optional[str] = None):
        # 1. Get old data and dataset_id BEFORE delete
        res = await db.execute(
            select(MetaTable.dataset_id)
            .join(MetaRelationship, MetaTable.id == MetaRelationship.source_table_id)
            .where(MetaRelationship.id == rel_id)
        )
        dataset_id = res.scalar_one_or_none()

        old_rel_result = await db.execute(select(MetaRelationship).where(MetaRelationship.id == rel_id))
        old_rel = old_rel_result.scalar_one_or_none()

        # 2. Delete
        query = delete(MetaRelationship).where(MetaRelationship.id == rel_id)
        await db.execute(query)

        # 3. Record changelog
        if old_rel:
            old_data = {
                "source_table_id": old_rel.source_table_id,
                "target_table_id": old_rel.target_table_id,
                "join_condition": old_rel.join_condition,
                "join_type": old_rel.join_type,
                "description": old_rel.description
            }
            await ChangelogService.log_change(
                db=db,
                resource_type="relationship",
                resource_id=str(rel_id),
                operation="delete",
                user_id=user_id,
                user_name=user_name,
                old_data=old_data,
                reason=reason or f"删除关系 {rel_id}"
            )

        if dataset_id:
            await MetadataService._mark_dataset_as_modified(db, dataset_id)

        await db.commit()

    # --- YAML Export Logic ---

    @staticmethod
    async def export_dataset_yaml(db: AsyncSession, dataset_id: int) -> str:
        """
        Export the entire dataset as a YAML string formatted for LLM/RAG.
        """
        from app.services.config_service import ConfigService

        dataset = await MetadataService.get_dataset_by_id(db, dataset_id, is_admin=True)
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found")
            
        # Determine Data Source ID
        # 1. Use dataset specific source
        # 2. Fallback to system default
        ds_source = dataset.data_source
        if not ds_source:
            ds_source = await ConfigService.get("external_sql_data_source", default="default_clickhouse")

        # Transform to Dict structure
        data_out = {
            "dataset": dataset.name,
            "data_source": ds_source, # Explicitly tell LLM which DB ID to use
            "description": dataset.description or "",
            "tables": []
        }
        
        for table in dataset.tables:
            # Skip disabled tables
            if hasattr(table, "status") and table.status != 1:
                continue

            tbl_out = {
                "name": table.physical_name,
                "term": table.term,
                "description": table.description or "",
                "synonyms": table.synonyms or [],
                "columns": []
            }
            
            for col in table.columns:
                col_out = {
                    "name": col.physical_name,
                    "term": col.term,
                    "description": col.description or "",
                    "type": col.type
                }
                if col.enums:
                    col_out["enums"] = col.enums
                
                # Add Primary Key indicator
                if hasattr(col, "is_primary") and col.is_primary == 1:
                    col_out["pk"] = True

                # Only add if important
                tbl_out["columns"].append(col_out)
                
            data_out["tables"].append(tbl_out)
            
        # Add Metrics
        if hasattr(dataset, 'metrics') and dataset.metrics:
            data_out["metrics"] = []
            for m in dataset.metrics:
                data_out["metrics"].append({
                    "name": m.name,
                    "display_name": m.display_name,
                    "description": m.description or "",
                    "calculation": m.calculation_logic,
                    "unit": m.unit or ""
                })

        # Add Relationships
        if hasattr(dataset, 'relationships') and dataset.relationships:
             data_out["relationships"] = []
             # Need to resolve table names for better readability in YAML? 
             # Or just IDs? LLM prefers names usually.
             # The relationship object loaded via selectinload might have table objects if defined in model.
             # Let's check model... Relationship has `source_table` and `target_table` relationships.
             # We need to make sure they are loaded.
             pass 
             
             # Actually, simpler approach:
             # get_dataset_by_id loads (dataset.metrics) and (dataset.relationships).
             # But dataset.relationships isn't a direct relationship on MetaDataset model?
             # Wait, app/models/metadata.py: "dataset = relationship('MetaDataset', back_populates='metrics')" on Metric.
             # Does Dataset have `relationships`? 
             # Let's check `app/models/metadata.py` content from previous step.
             # `MetaRelationship` links Tables. `MetaDataset` does NOT typically have a direct `relationships` field unless added.
             # So `dataset.relationships` above might fail if model isn't updated.
             
             # CORRECTION: We should fetch relationships separately or assume they are not on dataset object directly.
             # Let's fetch them using the logic we just wrote `get_relationships_by_dataset`.
             # But here we are inside `export_dataset_yaml`.
             
             # Correct Logic:
             # Fetch all relationships involving tables in this dataset.
             # Since we have `dataset.tables`, we can collect table IDs.
             table_ids = [t.id for t in dataset.tables]
             if table_ids:
                 stmt = select(MetaRelationship).options(
                     selectinload(MetaRelationship.source_table),
                     selectinload(MetaRelationship.target_table)
                 ).where(
                     (MetaRelationship.source_table_id.in_(table_ids)) | 
                     (MetaRelationship.target_table_id.in_(table_ids))
                 )
                 rel_res = await db.execute(stmt)
                 rels = rel_res.scalars().all()
                 
                 if rels:
                     data_out["relationships"] = []
                     for r in rels:
                         data_out["relationships"].append({
                             "source": r.source_table.physical_name if r.source_table else str(r.source_table_id),
                             "target": r.target_table.physical_name if r.target_table else str(r.target_table_id),
                             "type": r.join_type,
                             "condition": r.join_condition,
                             "description": r.description or ""
                         })
            
        # Dump to YAML
        return yaml.dump(data_out, allow_unicode=True, sort_keys=False)

