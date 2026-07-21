"""
访问日志中间件, 用于记录和分析 API 请求。
"""

import time
import uuid
import json
import asyncio
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from app.core import database
from typing import Optional

from app.services.audit_service import AuditService

class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. 路径过滤，仅保留 log / api / requests
        if not request.url.path.startswith("/api"):
            return await call_next(request)

        # 2. Trace ID
        trace_id = request.headers.get("X-Trace-Id") or str(uuid.uuid4())
        request.state.trace_id = trace_id

        start_time = time.time()

        # 3. 处理请求 & 获取响应体
        request_body_str = None
        try:
            content_type = request.headers.get("content-type", "")
            content_length = request.headers.get("content-length")
            
            # 只捕获 JSON/Text，跳过大文件或未知类型
            if ("application/json" in content_type or "text/" in content_type) and \
               (not content_length or int(content_length) < 102400): # 100KB limit
                body_bytes = await request.body()
                request_body_str = body_bytes.decode("utf-8", errors="ignore")
                # 如果仍然太长则截断（双重安全）
                if len(request_body_str) > 10000:
                    request_body_str = request_body_str[:10000] + "...(truncated)"
        except Exception as e:
            request_body_str = "<error capturing body>"

        response_body_chunks = []

        try:
            response = await call_next(request)
        except Exception as e:
            # Re-raise to let exception handlers catch it
            raise e

        # 将 TraceID 添加到响应头
        response.headers["X-Trace-Id"] = trace_id

        # 封装 body 以捕获审核日志
        async def body_iterator(actual_iterator):
            async for chunk in actual_iterator:
                if len(response_body_chunks) * 4096 < 10240: # limit to 10KB
                     response_body_chunks.append(chunk)
                yield chunk

        original_iterator = response.body_iterator
        response.body_iterator = body_iterator(original_iterator)

        # 4. 异步入队
        # 我们定义了一个响应后回调函数，稍后会调用它。
        async def perform_logging():
            process_time = (time.time() - start_time) * 1000 # ms
            
            # Reconstruct response body
            full_body = b"".join(response_body_chunks)
            response_body = ""
            if full_body:
                try:
                    response_body = full_body.decode('utf-8', errors='ignore') if len(full_body) < 10240 else f"<too large: {len(full_body)}>"
                except:
                    response_body = "<binary>"

            user_name = getattr(request.state, "user", {}).get("user_name") if hasattr(request.state, "user") else None
            
            await AuditService.log_request_data(
                trace_id=trace_id,
                user_name=user_name,
                endpoint=request.url.path,
                method=request.method,
                status_code=response.status_code,
                process_time_ms=process_time,
                client_ip=request.client.host if request.client else None,
                request_params=request_body_str or request.query_params.__str__(),
                response_body=response_body
            )

        # 使用 asyncio.create_task 确保即使客户端断开连接它也能运行
        # 或者如果我们希望 starlette 的后台任务成为请求生命周期的一部分，则可以使用它。 
        # 考虑到我们想要最大的性能，只要我们不泄漏，create_task 就可以了。 
        # 实际上，为了安全和FastAPI标准，我们将坚持使用BackgroundTask
        # 但内容只是一个简单的队列。
        from starlette.background import BackgroundTask
        response.background = BackgroundTask(perform_logging)
            
        return response