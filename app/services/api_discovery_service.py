"""
API 发现服务
"""

from typing import List, Dict, Any
from fastapi import FastAPI
from fastapi.routing import APIRoute

class ApiDiscoveryService:
    @staticmethod
    def get_v1_api_resources(app: FastAPI) -> List[Dict[str, Any]]:
        """
        扫描 FastAPI 应用程序，查找可用作权限资源的 V1 端点。
        
        返回一个包含 V1 端点资源的列表，每个资源包含 id、名称、描述、组、方法和路径:
        [
            {
                "id": "POST:/api/v1/chat/completions",
                "name": "Chat Completions",
                "description": "Send a chat message...",
                "group": "Chat"
            },
            ...
        ]
        """
        resources = []
        
        # Sort routes by path for consistent ordering
        # Filter for APIRoute to access methods, path, summary etc.
        routes = [r for r in app.routes if isinstance(r, APIRoute)]
        routes.sort(key=lambda r: r.path)

        for route in routes:
            if route.path.startswith("/api/v1"):
                for method in route.methods:
                    if method in ["HEAD", "OPTIONS"]:
                        continue
                        
                    resource_id = f"{method}:{route.path}"
                    # Use summary as primary name, fallback to function name
                    name = route.summary or route.name.replace("_", " ").title()
                    description = route.description or ""
                    # Use first tag as group
                    group = route.tags[0] if route.tags else "General"
                    
                    resources.append({
                        "id": resource_id,
                        "name": name,
                        "description": description,
                        "group": group,
                        "method": method,
                        "path": route.path
                    })
                    
        return resources
