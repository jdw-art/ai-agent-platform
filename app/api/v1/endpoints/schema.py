import logging
from fastapi import APIRouter, Depends, HTTPException, Body
from app.api.portal.endpoints.audit import is_admin
from app.core.config import settings
from app.core.orm import get_db_session
from app.core.dependencies import verify_v1_api_access
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()

from app.schemas.response import StandardResponse

class SchemaRequest(BaseModel):
    query: Optional[str] = Field(None, description="检索关键词", example="销售数据")

class SchemaHit(BaseModel):
    id: int = Field(..., description="数据集ID")
    name: str = Field(..., description="数据集名称")
    display_name: str = Field(..., description="中文显示名")

class SchemaResponse(BaseModel):
    schema_context: str = Field(..., description="YAML格式的Schema定义")
    hits: List[SchemaHit] = Field(..., description="命中的数据集列表")
    provider: str = Field(..., description="元数据提供方 (local/ragflow)")
    logs: List[str] = Field(default=[], description="执行过程日志")

@router.post("/schema", 
    response_model=StandardResponse[SchemaResponse],
    summary="检索元数据 Schema",
    description="统一 Schema 检索接口 (Gateway)。根据系统配置 (metadata_provider) 路由请求到 Local Service 或 RAGFlow。"
)
async def get_database_schema(
    request: SchemaRequest,
    conn: AsyncSession = Depends(get_db_session),
    current_user: dict = Depends(verify_v1_api_access)
):
    """
    统一 Schema 检索接口 (Gateway)。
    根据系统配置 (metadata_provider) 路由请求到 Local Service 或 RAGFlow。
    """
    from app.services.config_service import ConfigService
    from app.services.metadata_service import MetadataService
    from app.core.context import get_current_agent_context

    trace_logs = []

    provider = await ConfigService.get("metadata_provider", default="local")
    msg = f"[Metadata Gateway] Routing request to provider: {provider.upper()}"
    logger.info(msg)
    trace_logs.append(msg)

    # 处理用户上下文
    # 优先级：1. 从依赖中获取
    user_id = int(current_user.get("user_id")) if current_user.get("user_id") else None
    is_admin = current_user.get("role") == "admin"

    # 优先级2. 从 Agent 上下文获取
    ctx = get_current_agent_context()
    if ctx and ctx.user_id:
        # 如果在代理上下文中运行（除非内部调用，否则对于此特定端点不太可能），则依赖上下文。
        user_id = ctx.user_id
        is_admin = ctx.is_admin

    trace_logs.append(f"User Context: user_id={user_id}, is_admin={is_admin}")

    # 1. RAGFlow
    if provider == "ragflow":
        from app.services.ai.ragflow_client import RagFlowClient

        # 打印 RAGFlow 配置
        rag_url = await ConfigService.get("ragflow_api_url")

        # 加载参数
        threshold = float(await ConfigService.get("ragflow_similarity_threshold") or 0.2)
        weight = float(await ConfigService.get("ragflow_vector_weight") or 0.3)
        top_k = 5 # Adjusted from 10 to 5

        trace_logs.append(f"RAGFlow Endpoint: {rag_url}")
        trace_logs.append(f"Params: threshold={threshold}, weight={weight}, top_k={top_k}")

        # A. 获取所有已授权数据集
        authorized_datasets = await MetadataService.search_datasets(
            conn, 
            status=1, 
            user_id=user_id, 
            is_admin=is_admin
        )
        rag_ids = [ds.rag_dataset_id for ds in authorized_datasets if ds.rag_dataset_id]
        trace_logs.append(f"Authorized Datasets: {len(authorized_datasets)} found. RAG IDs: {len(rag_ids)}")

        if not rag_ids:
            return StandardResponse(data=SchemaResponse(
                schema_context="[System] No authorized RAG metadata found.",
                hits=[],
                provider="ragflow",
                logs=trace_logs
            ))

        # B. 从 RAGFlow 检索
        from app.services.metadata_rag_service import MetadataRagService, MetadataServiceUnavailableError
        client = RagFlowClient()
        query = request.query or "lastest schema"
        msg = f"[Metadata Gateway] RAG Retrieval Query: '{query}' on {len(rag_ids)} IDs."
        logger.info(msg)
        trace_logs.append(msg)

        try:
            chunks, r_logs = await MetadataRagService.retrieve_with_retry(
                client,
                query, 
                rag_ids, 
                top_k=top_k,
                threshold=threshold,
                weight=weight
            )
        except MetadataServiceUnavailableError as e:
            logger.error(f"[Metadata Gateway] RAGFlow unavailable: {e}")
            trace_logs.append(f"RAGFlow service unavailable, aborted without retry: {e}")
            raise HTTPException(
                status_code=503,
                detail="元数据检索服务（RAGFlow）暂时不可用，请稍后重试或联系管理员。"
            )
        trace_logs.extend(r_logs)

        if not chunks:
            trace_logs.append("RAGFlow returned 0 chunks (after potential retries).")
            return StandardResponse(data=SchemaResponse(
                schema_context="[System] No relevant knowledge found in RAGFlow metadata.",
                hits=[],
                provider="ragflow",
                logs=trace_logs
            ))

        # C. 格式化数据
        trace_logs.append(f"RAGFlow returned {len(chunks)} chunks.")
        context_parts = []
        for i, chunk in enumerate(chunks):
            sim = chunk.get('similarity', 0)
            doc_name = chunk.get('doc_name', 'unknown')
            trace_logs.append(f"Hit #{i+1}: {doc_name} (Sim: {sim:.2f})")
            context_parts.append(f"--- Source: {doc_name} (Sim: {sim:.2f}) ---\n{chunk['content']}")
            
        return StandardResponse(data=SchemaResponse(
            schema_context="\n\n".join(context_parts),
            hits=[SchemaHit(id=0, name="rag_hit", display_name="RAG Results")],
            provider="ragflow",
            logs=trace_logs
        ))

    # 2. 本地数据库
    found_datasets = []

    if request.query:
        # 根据字符串查询
        trace_logs.append(f"Searching local datasets with query: '{request.query}'")
        found_datasets = await MetadataService.search_datasets(conn, request.query)
        trace_logs.append(f"Found {len(found_datasets)} datasets.")


    if not found_datasets:
        return StandardResponse(data=SchemaResponse(
            schema_context="[System] No relevant metadata found. Please refine your query.",
            hits=[],
            provider="local",
            logs=trace_logs
        ))

    yaml_outputs = []
    hits = []
    for ds in found_datasets:
        yaml_text = await MetadataService.export_dataset_yaml(conn, ds, id)
        yaml_outputs.append(yaml_text)
        hits.append(SchemaHit(id=ds.id, name=ds.name, display_name=ds.display_name))

    final_context = "\n---\n".join(yaml_outputs)
    return StandardResponse(data=SchemaResponse(
        schema_context=final_context,
        hits=hits,
        provider="local",
        logs=trace_logs
    ))