from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime


class DbConnectionConfigCreate(BaseModel):
    """创建连接配置请求体"""
    name: str
    db_type: str
    host: str
    port: int
    db_user: str
    password: str
    database_name: str
    description: str = ""


class DbConnectionConfigResponse(DbConnectionConfigCreate):
    """连接配置响应体（密码不回传）"""
    id: int
    created_by: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DbConnectionConfigSafeResponse(BaseModel):
    """前端用响应体，密码脱敏"""
    id: int
    name: str
    db_type: str
    host: str
    port: int
    db_user: str
    password: str  # 回传明文，供前端填充表单（历史连接一键填充）
    database_name: str
    description: str = ""
    created_by: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
