from fastapi import APIRouter, Depends, HTTPException, Body
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from app.core.dependencies import require_admin, require_permission
from app.core.config import settings
from app.core import redis
from app.services.config_service import ConfigService
from app.schemas.system_config import ConfigHistoryItem
import logging
import asyncio
import traceback

router = APIRouter()

@router.get("/configs/{key}/history", response_model=List[ConfigHistoryItem])
async def get_config_history(
    key: str,
    limit: int = 50,
    user: Dict = Depends(require_permission("menu", "menu:system:config"))
):
    """
    Get history for a specific config key.
    """
    try:
        return await ConfigService.get_config_history(key, limit)
    except Exception as e:
        logging.error(f"Failed to fetch config history for {key}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class ConnectionTestResponse(BaseModel):
    status: str
    message: str
    logs: List[str]

# ... (Previous test-connection and redis routes remain unchanged)

@router.post("/test-connection/{component}", response_model=ConnectionTestResponse)
async def test_connection(
    component: str,
    user: Dict = Depends(require_permission("element", "element:system:config_save"))
):
    """
    Test connection to infrastructure components (Redis) with detailed logs.
    """
    logs = []
    status = "failed"
    message = ""

    def log(msg: str):
        logs.append(msg)
        logging.info(f"[SystemCheck] {msg}")

    try:
        if component == "redis":
            log(f"Target: Redis ({settings.REDIS_HOST}:{settings.REDIS_PORT})")
            log(f"DB: {settings.REDIS_DB}, Enabled: {settings.REDIS_ENABLE}")
            
            if not settings.REDIS_ENABLE:
                log("Redis is disabled in configuration.")
                status = "skipped"
                message = "Redis is disabled."
            else:
                log("Getting Redis client...")
                r = await redis.get_redis()
                if not r:
                     # Attempt to init if not ready (though lifespan should have done it)
                     log("Redis client not ready, attempting initialization...")
                     await redis.init_redis()
                     r = await redis.get_redis()
                
                if not r:
                    raise Exception("Failed to initialize Redis client")

                log("Executing: PING")
                result = await r.ping()
                log(f"PING Result: {result}")
                
                status = "success"
                message = "Redis connection successful."

        elif component == "chatbi_kb":
            log("Target: ChatBI RAGFlow KB (chatbi-example-meta)")
            log("Ensuring KB initialization (Auto-create if not exists)...")
            from app.services.chatbi_example_service import ExampleService
            kb_id = await ExampleService.ensure_chatbi_sample_kb_id()
            log(f"Successfully ensured KB. ID: {kb_id}")
            
            # Verify connectivity to RAGFlow by listing documents
            from app.services.ai.ragflow_client import RagFlowClient
            client = RagFlowClient()
            log("Testing connection to RAGFlow by listing documents...")
            docs = await client.list_documents(kb_id, page_size=5)
            log(f"Successfully connected. Found {len(docs)} documents in dataset.")
            
            status = "success"
            message = f"ChatBI KB connection successful. ID: {kb_id}"

        else:
            raise HTTPException(status_code=400, detail=f"Unknown component: {component}")

    except HTTPException:
        # Re-raise HTTP exceptions to be handled by FastAPI's exception handlers
        raise
    except Exception as e:
        log(f"❌ Error: {str(e)}")
        log(f"Traceback: {traceback.format_exc()}")
        status = "error"
        message = f"Connection failed: {str(e)}"

    return ConnectionTestResponse(
        status=status,
        message=message,
        logs=logs
    )

class RedisKeysResponse(BaseModel):
    count: int
    keys: List[str]

@router.post("/redis/keys", response_model=RedisKeysResponse)
async def get_redis_keys(
    user: Dict = Depends(require_permission("element", "element:system:config_save"))
):
    """
    Get Redis total key count and list all keys.
    """
    try:
        if not settings.REDIS_ENABLE:
             raise HTTPException(status_code=400, detail="Redis is disabled")
             
        r = await redis.get_redis()
        if not r:
            await redis.init_redis()
            r = await redis.get_redis()
            
        if not r:
             raise HTTPException(status_code=500, detail="Redis client not available")

        # Get count
        count = await r.dbsize()
        
        # Get keys (using KEYS * as requested, careful in prod)
        keys = await r.keys("*")
        # keys are already decoded because decode_responses=True in app.core.redis
        
        return RedisKeysResponse(count=count, keys=keys)
        
    except Exception as e:
        logging.error(f"Failed to scan redis keys: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/redis/flush")
async def flush_redis_keys(
    user: Dict = Depends(require_permission("element", "element:system:config_save"))
):
    """
    Clear all keys in the current Redis database.
    """
    try:
        if not settings.REDIS_ENABLE:
             raise HTTPException(status_code=400, detail="Redis is disabled")
             
        r = await redis.get_redis()
        if not r:
            await redis.init_redis()
            r = await redis.get_redis()
            
        if not r:
             raise HTTPException(status_code=500, detail="Redis client not available")

        # Intelligent Flush: Preserve conversation history
        # Instead of flushdb(), we scan and delete selective keys
        cursor = '0'
        deleted_count = 0
        preserved_count = 0
        
        while cursor != 0:
            cursor, keys = await r.scan(cursor=cursor, match='*', count=1000)
            if keys:
                keys_to_delete = []
                for key in keys:
                    # Check if key should be preserved
                    # Pattern: conversation:{user_id}:{conversation_id}:history
                    if key.startswith("conversation:"):
                        preserved_count += 1
                    else:
                        keys_to_delete.append(key)
                
                if keys_to_delete:
                    await r.delete(*keys_to_delete)
                    deleted_count += len(keys_to_delete)

        logging.info(f"Redis cleanup by {user.get('user_name')}: Deleted {deleted_count}, Preserved {preserved_count} conversation keys.")
        return {
            "status": "success", 
            "message": f"Cleaned {deleted_count} keys. Preserved {preserved_count} conversation histories."
        }
        
    except Exception as e:
        logging.error(f"Failed to flush redis keys: {e}")
# --- Redis Browser Endpoints ---

class RedisKeyListItem(BaseModel):
    name: str
    type: str

class RedisKeyListResponse(BaseModel):
    count: int
    keys: List[RedisKeyListItem]

@router.get("/redis/keys-list", response_model=RedisKeyListResponse)
async def list_redis_keys(
    pattern: str = "*",
    user: Dict = Depends(require_permission("element", "element:system:config_save"))
):
    """
    List Redis keys matching a pattern, along with their data type.
    """
    try:
        if not settings.REDIS_ENABLE:
            raise HTTPException(status_code=400, detail="Redis is disabled")
            
        r = await redis.get_redis()
        if not r:
            await redis.init_redis()
            r = await redis.get_redis()
            
        if not r:
            raise HTTPException(status_code=500, detail="Redis client not available")

        # Use SCAN to scan matched keys safely
        keys = []
        cursor = '0'
        
        # Limit to 5000 keys maximum to prevent OOM
        while len(keys) < 5000:
            cursor, batch = await r.scan(cursor=cursor, match=pattern, count=1000)
            keys.extend(batch)
            if cursor == 0 or int(cursor) == 0:
                break
                
        # Fetch types
        results = []
        for key in keys[:5000]:
            k_type = await r.type(key)
            results.append(RedisKeyListItem(name=key, type=k_type))
            
        return RedisKeyListResponse(count=len(results), keys=results)
        
    except Exception as e:
        logging.error(f"Failed to list redis keys: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class RedisKeyDetailResponse(BaseModel):
    name: str
    type: str
    ttl: int
    value: Any

@router.get("/redis/key-detail", response_model=RedisKeyDetailResponse)
async def get_redis_key_detail(
    key: str,
    user: Dict = Depends(require_permission("element", "element:system:config_save"))
):
    """
    Get detailed value and metadata of a specific Redis key.
    """
    try:
        if not settings.REDIS_ENABLE:
            raise HTTPException(status_code=400, detail="Redis is disabled")
            
        r = await redis.get_redis()
        if not r:
            await redis.init_redis()
            r = await redis.get_redis()
            
        if not r:
            raise HTTPException(status_code=500, detail="Redis client not available")

        # Verify key exists
        exists = await r.exists(key)
        if not exists:
            raise HTTPException(status_code=404, detail="Key not found")

        # Get type & ttl
        k_type = await r.type(key)
        ttl = await r.ttl(key)

        # Retrieve value based on type
        value = None
        if k_type == "string":
            value = await r.get(key)
        elif k_type == "hash":
            # 使用 binary 客户端读取，防止含 embedding 等二进制字段时 UnicodeDecodeError
            r_binary = await redis.get_redis_binary()
            raw_hash = await r_binary.hgetall(key)
            value = {}
            for field_bytes, val_bytes in raw_hash.items():
                # 字段名解码
                try:
                    field_str = field_bytes.decode("utf-8") if isinstance(field_bytes, bytes) else field_bytes
                except Exception:
                    field_str = f"<binary-key: {len(field_bytes)} bytes>"
                # 字段值解码
                if isinstance(val_bytes, bytes):
                    try:
                        value[field_str] = val_bytes.decode("utf-8")
                    except Exception:
                        value[field_str] = f"<binary: {len(val_bytes)} bytes>"
                else:
                    value[field_str] = val_bytes
        elif k_type == "list":
            value = await r.lrange(key, 0, -1)
        elif k_type == "set":
            value = list(await r.smembers(key))
        elif k_type == "zset":
            zset_data = await r.zrange(key, 0, -1, withscores=True)
            # Format as [{"member": m, "score": s}]
            value = [{"member": m, "score": s} for m, s in zset_data]
        else:
            value = f"(Unsupported type: {k_type})"

        return RedisKeyDetailResponse(name=key, type=k_type, ttl=ttl, value=value)

    except HTTPException as he:
        raise he
    except Exception as e:
        logging.error(f"Failed to get redis key detail for {key}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/redis/key")
async def delete_redis_key(
    key: str,
    user: Dict = Depends(require_permission("element", "element:system:config_save"))
):
    """
    Delete a specific key from Redis.
    """
    try:
        if not settings.REDIS_ENABLE:
            raise HTTPException(status_code=400, detail="Redis is disabled")
            
        r = await redis.get_redis()
        if not r:
            await redis.init_redis()
            r = await redis.get_redis()
            
        if not r:
            raise HTTPException(status_code=500, detail="Redis client not available")

        deleted = await r.delete(key)
        if not deleted:
            raise HTTPException(status_code=404, detail="Key not found or already deleted")

        return {"status": "success", "message": f"Key '{key}' deleted successfully."}

    except HTTPException as he:
        raise he
    except Exception as e:
        logging.error(f"Failed to delete redis key {key}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- New Configuration Endpoints ---

class ConfigItem(BaseModel):
    key: str
    value: str
    description: Optional[str] = None
    is_secret: bool = False

class ConfigUpdateRequest(BaseModel):
    updates: List[ConfigItem]

@router.get("/configs", response_model=Dict[str, List[Dict[str, Any]]])
async def get_system_configs(
    user: Dict = Depends(require_permission("menu", "menu:system:config"))
):
    """
    Get all system configurations grouped by category.
    Sensitive values are masked.
    """
    try:
        return await ConfigService.get_all_configs_grouped()
    except Exception as e:
        logging.error(f"Failed to get configs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/configs")
async def update_system_configs(
    request: ConfigUpdateRequest,
    user: Dict = Depends(require_permission("element", "element:system:config_save"))
):
    """
    Bulk update system configurations.
    """
    try:
        updates = [item.dict() for item in request.updates]
        # Pass the username to the service for audit logging
        await ConfigService.bulk_update(updates, changed_by=user.get("user_name", "admin"))
        return {"status": "success", "message": "Configurations updated successfully."}
    except Exception as e:
        logging.error(f"Failed to update configs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- Log & Partition Management Endpoints (Admin Only) ---

from app.core.orm import get_db_session
from sqlalchemy.ext.asyncio import AsyncSession

class LogConfigUpdateRequest(BaseModel):
    audit_log_retention_days: int

@router.get("/logs/config")
async def get_logs_config(
    user: Dict = Depends(require_admin)
):
    """
    Get audit log retention configuration days.
    """
    retention = await ConfigService.get("audit_log_retention_days", default="90")
    return {"audit_log_retention_days": int(retention) if retention.isdigit() else 90}

@router.post("/logs/config")
async def update_logs_config(
    payload: LogConfigUpdateRequest,
    user: Dict = Depends(require_admin)
):
    """
    Update log retention days configuration.
    """
    days = payload.audit_log_retention_days
    if days <= 0 or days > 3650:
        raise HTTPException(status_code=400, detail="日志保留天数必须在 1 到 3650 之间")
    
    await ConfigService.update_config_value(
        "audit_log_retention_days", 
        str(days), 
        changed_by=user.get("user_name", "admin"),
        change_reason="Update via Log Management Tab"
    )
    return {"status": "success", "message": "配置更新成功"}

@router.get("/logs/partitions")
async def get_logs_partitions(
    user: Dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Get MySQL physical partition lists for audit and trace logs.
    """
    from app.services.partition_service import PartitionService
    try:
        partitions = await PartitionService.get_partition_status(db)
        return partitions
    except Exception as e:
        logging.error(f"Failed to fetch partitions: {e}")
        raise HTTPException(status_code=500, detail=f"获取分区状态失败: {str(e)}")

@router.post("/logs/cleanup")
async def manual_cleanup_logs(
    user: Dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Manually trigger cleanup of expired audit and trace logs.
    """
    from app.services.partition_service import PartitionService
    retention_str = await ConfigService.get("audit_log_retention_days", default="90")
    try:
        retention_days = int(retention_str)
    except (ValueError, TypeError):
        retention_days = 90
        
    try:
        res = await PartitionService.prune_expired_logs(db, retention_days)
        return res
    except Exception as e:
        logging.error(f"Failed to cleanup logs: {e}")
        raise HTTPException(status_code=500, detail=f"清理历史日志失败: {str(e)}")

