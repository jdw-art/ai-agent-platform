from pydantic import BaseModel, Field
from typing import List, Optional

class ResourcePermissionBase(BaseModel):
    resource_type: str
    resource_id: str
    enabled: bool = True

class PermissionSet(BaseModel):
    """Represents a set of permissions grouped by resource type"""
    agents: List[str] = Field(default_factory=list, description="List of allowed Agent IDs")
    datasets: List[str] = Field(default_factory=list, description="List of allowed RagFlow Dataset IDs")
    apis: List[str] = Field(default_factory=list, description="List of allowed External API Routes")
    metadata: List[str] = Field(default_factory=list, description="List of allowed Metadata Dataset IDs")
    menus: List[str] = Field(default_factory=list, description="List of allowed Menu IDs")
    elements: List[str] = Field(default_factory=list, description="List of allowed Action/Element IDs")

class ResourceDetail(BaseModel):
    id: str
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None

class PermissionSetDetail(BaseModel):
    """Detailed view of permissions with names and descriptions"""
    agents: List[ResourceDetail] = Field(default_factory=list)
    datasets: List[ResourceDetail] = Field(default_factory=list)
    apis: List[ResourceDetail] = Field(default_factory=list)
    metadata: List[ResourceDetail] = Field(default_factory=list)
    menus: List[ResourceDetail] = Field(default_factory=list)
    elements: List[ResourceDetail] = Field(default_factory=list)

class UserPermissionsResponse(BaseModel):
    roles: List[str] = Field(default_factory=list, description="Assigned roles (reserved)")
    permissions: PermissionSet
    details: Optional[PermissionSetDetail] = None

class PermissionUpdate(PermissionSet):
    """Payload for updating user permissions"""
    pass
