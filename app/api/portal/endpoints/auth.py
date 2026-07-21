from fastapi import APIRouter, Depends, HTTPException, status, Response, Header
from typing import Optional
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import require_api_key
from app.core.orm import get_db_session
from app.services.auth_service import AuthService

