"""
知识工具：用于查询知识库中的信息
"""

import ast
import logging
import json
import re
from app.services.ai.tools.tool_compat import tool
from typing import Any, Optional, List, Union
from app.services.ai.ragflow_client import RagFlowClient
from app.services.config_service import ConfigService
from app.services.metadata_rag_service import MetadataRagService

logger = logging.getLogger(__name__)

from app.core.context import get_current_agent_config, get_current_agent_context
from app.core.orm import AsyncSessionLocal
from app.services.permission_service import PermissionService

# 32 位 hex，与 RAGFlow dataset id 常见格式一致
_DATASET_ID_RE = re.compile(r"^[a-fA-F0-9]{32}$")

def normalize_dataset_ids(raw: Union[str, List[Any], None]) -> List[str]:
    """
    将工具参数 / 配置中的 dataset_ids 规范为纯 ID 列表
    兼容：逗号分隔、JSON 数组、Python 单引号列表、多余引号与方括号
    """
    if raw is None:
        return []

    items: List[Any]
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        if text.startswith("["):
            parsed: Any = None
            try:
                parsed = ast.literal_eval(text)
            except (ValueError, SyntaxError):
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    parsed = None
            items = parsed if isinstance(parsed, list) else [text]
        else:
            items = text.split(",")
    else:
        items = [raw]

    result: List[str] = []
    for item in items:
        token = str(item).strip().strip("[]\"' \t")
        if not token:
            continue
        if _DATASET_ID_RE.match(token):
            result.append(token)
            continue
        # 从混杂字符串中提取合法 ID（如 LLM 传入带括号的整段）
        for match in _DATASET_ID_RE.findall(token):
            if match not in result:
                result.append(match)

    return result

@tool
async def search_knowledge_base(query: str, dataset_ids: Optional[str] = None) -> str:
    """
    在知识库 (RAGFlow) 中搜索文档、手册和法规

    参数：
    - query: 搜索查询
    - dataset_ids: 可选，指定要搜索的 RAGFlow 数据集 ID 列表

    返回：
    - 搜索结果的 JSON 字符串
    """
    client = RagFlowClient()

    logger.info(f"[KnowledgeTool] Called with query='{query}', explicit_ids='{dataset_ids}'")

    # 1. 处理 dataset_ids 参数
    target_datasets: List[str] = []

    if dataset_ids:
        target_datasets = normalize_dataset_ids(dataset_ids)
        logger.info(f"[KnowledgeTool] Used explicit dataset_ids (normalized): {target_datasets}")
    else:
        context_datasets = get_current_agent_config("dataset_ids")
        if context_datasets:
            target_datasets = normalize_dataset_ids(context_datasets)

        if not target_datasets:
            default_ids_str = await ConfigService.get("ragflow_dataset_ids")
            if default_ids_str:
                target_datasets = normalize_dataset_ids(default_ids_str)
            logger.info(f"[KnowledgeTool] Fallback to system default: {target_datasets}")

    if dataset_ids and not target_datasets:
        return (
            "[Tool Error] Invalid dataset_ids. Use a plain 32-char ID, "
            "comma-separated IDs, or a single-quoted list like "
            "['4525d66cec7111f0a3d00242ac120006'] — do not use [\"...\"]."
        )

    if not target_datasets:
        logger.warning("[KnowledgeTool] No datasets configured.")
        return "[System Warning] No knowledge base datasets configured. Please contact admin to set 'ragflow_dataset_ids'."

    ctx = get_current_agent_context()
    if ctx and ctx.user_id and not ctx.is_admin:
        user_name = (ctx.user_dimensions or {}).get("user_name")
        async with AsyncSessionLocal() as session:
            perm = PermissionService(session)
            before = list(target_datasets)
            target_datasets = await perm.filter_knowledge_dataset_ids(
                int(ctx.user_id),
                user_name,
                target_datasets,
            )
            denied = [d for d in before if d not in target_datasets]
            if denied:
                logger.warning(
                    "[KnowledgeTool] Removed datasets without permission: %s",
                    denied,
                )

        if not target_datasets:
            return (
                "[Tool Error] No permission to search the requested knowledge base. "
                "You may only use datasets assigned to you or created by yourself."
            )

    # 2. 处理参数（阈值和权重）
    # 优先级：Agent Engine Config > System Config > Hardcoded Default

    # 默认值
    threshold = 0.2
    vector_weight = 0.3

    # 从 Agent 上下文中获取
    engine_config = get_current_agent_config("engine_config")

    # 检查上下文中是否有engine_config（如果是简单的本地代理，则可能为空）
    # 'get_current_agent_config' 帮助器可能只返回顶级键。
    # 让我们检查一下上下文是如何工作的。通常我们存储特定的密钥。
    # 如果没有找到，我们可以尝试获取agent_id并查找，但如果设置正确，上下文应该有它。
    # 假设“engine_config”可能不在简化上下文字典中。
    # 但是，'dataset_ids' 在那里。我们再看一下agent_service.py 'set_agent_context'。

    # 重新读取agent_service.py：set_agent_context({...}) 设置：agent_id、agent_name、dataset_ids、engine_type。
    # 它没有设置完整的engine_config！所以我们不能直接从上下文中获取它，除非我们改变agent_service。
    # 但是，我们可以先读取系统配置。

    # 为了在不改变太多上下文结构的情况下获得特定于代理的阈值，我们可以：
    # A) 更改 agent_service.py 以将它们注入上下文中。
    # B) （更干净的分离的首选）如果需要的话获取配置？不，上下文是最好的。

    # 现在假设我首先依赖系统配置默认值，
    # 如果我更改agent_service，我将查找注入的变量。
    # 等等，计划说：“从当前代理的engine_config中读取......”。

    # 让我们看看 get_current_agent_config 的实现或用法。
    # 由于我无法在不看到“context.py”的情况下轻松修改它，因此我将更新“agent_service.py”以注入这些值。
    # 或者，我现在会尝试从系统配置中获取它们，并稍后更新agent_service。

    # 首先获取系统配置默认值
    sys_threshold = await ConfigService.get("ragflow_similarity_threshold")
    sys_weight = await ConfigService.get("ragflow_vector_weight")

    if sys_threshold:
        try:
            threshold = float(sys_threshold)
        except:
            pass

    if sys_weight:
        try:
            vector_weight = float(sys_weight)
        except:
            pass

    # 现在检查 Agent 配置
    agent_threshold = get_current_agent_config("ragflow_threshold")
    agent_weight = get_current_agent_config("ragflow_vector_weight")

    if agent_threshold is not None:
         try:
             threshold = float(agent_threshold)
         except:
             pass

    if agent_weight is not None:
         try:
             vector_weight = float(agent_weight)
         except:
             pass

    logger.info(f"[KnowledgeTool] Using params: threshold={threshold}, vector_weight={vector_weight}")

    try:
        chunks = await client.retrieve(
            query,
            target_datasets,
            similarity_threshold=threshold,
            vector_similarity_weight=vector_weight
        )

        if not chunks:
            return "No relevant information found in the knowledge base."

        # --- [新增：内联引用流程] ---
        # 1. 为代码块分配顺序 ID，以便于 LLM 引用
        # 2. 为 LLM 编写清晰的提示说明
        formatted_context = "I found the following information in the knowledge base. Please provide a detailed answer based ON THESE DOCUMENTS ONLY. \n"
        formatted_context += "CRITICAL: For every statement you make based on a document, append its reference as [ID:n] at the end of the sentence.\n\n"

        for i, chunk in enumerate(chunks):
            ref_id = str(i + 1)
            # Inject the simple ID into the chunk object so frontend can match it later
            chunk["id"] = ref_id

            doc_name = chunk.get("doc_name") or chunk.get("document_name") or "Unknown Document"
            content = chunk.get("content", "").strip()

            formatted_context += f"--- [ID:{ref_id}] Source: {doc_name} ---\n{content}\n\n"

        # 返回一个结构化的 JSON 字符串。执行器将对其进行解包。
        # 'content' 是 LLM 将看到的内容。
        # 'citations' 是前端的元数据。
        result = {
            "content": formatted_context,
            "citations": chunks
        }
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        err_msg = str(e)
        logger.error(f"Knowledge Search Failed: {e}", exc_info=True)
        if MetadataRagService._is_service_unavailable(err_msg):
            return MetadataRagService.knowledge_unavailable_hint(err_msg)
        return f"[Tool Error] Failed to search knowledge base: {err_msg}"