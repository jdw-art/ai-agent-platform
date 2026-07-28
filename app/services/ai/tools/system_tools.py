"""
系统工具集，包括 URL 校验、任务管理、通知工具等。
"""

import logging
import httpx
import json
import ipaddress
import socket
import pytz
from datetime import datetime
from urllib.parse import urlparse
from app.services.ai.tools.tool_compat import tool
from app.services.ai.tools.task_manager_tools import (
    create_recurring_task, get_my_tasks, cancel_task, 
    start_task, pause_task, run_task_manually
)
from app.services.ai.tools.notification_tools import send_dingtalk_message

logger = logging.getLogger(__name__)

def validate_url(url: str) -> bool:
    """
    通过阻止内部 IP 地址范围来验证 URL 以防止 SSRF 攻击。
    如果安全则返回 True，如果不安全则引发 ValueError。
    """
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            raise ValueError("Invalid URL: missing hostname")

        # Resolve hostname to IP
        try:
            ip_str = socket.gethostbyname(hostname)
        except socket.gaierror:
            # If we can't resolve it, it might be unreachable, but strict SSRF usually implies blocking it.
            # However, for a general tool, if it doesn't resolve, httpx will fail anyway.
            # But to be safe against DNS rebinding, we should resolve here.
            raise ValueError(f"Could not resolve hostname: {hostname}")

        ip = ipaddress.ip_address(ip_str)

        # Block loopback, private, link-local, multicast
        # Note: 198.18.0.0/15 is considered private by some python versions but is often used by
        # transparent proxies or benchmarking. We allow it to support tools like httpbin.org
        is_benchmark = ip in ipaddress.ip_network('198.18.0.0/15')

        if not is_benchmark and (ip.is_loopback or 
            ip.is_private or 
            ip.is_link_local or 
            ip.is_multicast):
            raise ValueError(f"Access to internal/private IP {ip_str} ({hostname}) is restricted.")
            
        return True
    except Exception as e:
        logger.warning(f"URL Validation Failed: {e}")
        raise e

@tool
async def system_http_request(method: str, url: str, headers: dict = None, body: dict = None, params: dict = None) -> str:
    """
    向外部 API 执行通用 HTTP 请求。
    参数：
    - method：HTTP 方法（GET、POST、PUT、DELETE、PATCH）。
    - url：要请求的完整 URL。
    - headers：可选的 HTTP 标头字典。
    - body：可选的 JSON 请求体字典（用于 POST/PUT 请求）。
    - params：可选的查询参数字典。
    """
    try:
        # Security Check
        validate_url(url)
        
        method = method.upper()
        if headers is None:
            headers = {}
        # Set a default User-Agent if not present
        if "User-Agent" not in headers and "user-agent" not in headers:
            headers["User-Agent"] = "Yunshu-AI-Agent/1.0"

        timeout = 30.0
        
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            logger.info(f"[SystemTool] {method} {url} Params={params}")
            
            if method == "GET":
                response = await client.get(url, params=params, headers=headers)
            elif method in ["POST", "PUT", "PATCH", "DELETE"]:
                response = await client.request(method, url, json=body, params=params, headers=headers)
            else:
                return f"Error: Unsupported method {method}"

            # Try to return JSON if possible, else text
            try:
                data = response.json()
                return json.dumps(data, ensure_ascii=False)
            except:
                return response.text[:10000] # Truncate generic text responses to avoid context overflow

    except Exception as e:
        return f"Error executing request: {str(e)}"

@tool
def get_current_time(timezone: str = "Asia/Shanghai") -> str:
    """
    获取当前系统时间。
    
    参数：
    - timezone：可选的时间区字符串（例如 'UTC'、'Asia/Shanghai'）。默认值为 'Asia/Shanghai'。
    
    返回：
    - 当前系统时间的字符串表示，格式为 "YYYY-MM-DD HH:MM:SS 星期X"。
    """
    try:
        if timezone:
            tz = pytz.timezone(timezone)
            now = datetime.now(tz)
        else:
            now = datetime.now()
        
        # Add Chinese weekday
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        weekday_str = weekdays[now.weekday()]
        
        return now.strftime(f"%Y-%m-%d %H:%M:%S {weekday_str} %Z%z")
    except Exception as e:
        return f"Error getting time: {str(e)}"


SYSTEM_IMPLICIT_TOOLS = [
    get_current_time, create_recurring_task, get_my_tasks, 
    cancel_task, start_task, pause_task, run_task_manually
]
