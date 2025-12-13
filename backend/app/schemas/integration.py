"""
Pydantic schemas for social media integrations
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID


class SocialIntegrationResponse(BaseModel):
    """Social integration response"""
    id: UUID
    tenant_id: UUID
    assistant_id: Optional[UUID]
    platform: str
    platform_user_id: str
    platform_username: Optional[str]
    platform_name: Optional[str]
    profile_data: Dict[str, Any]
    pages: List[Dict] = []
    organizations: List[Dict] = []
    is_active: bool
    is_verified: bool
    default_page_id: Optional[str] = None  # ID of the default page/organization
    oauth1_configured: Optional[bool] = None  # For Twitter: whether OAuth 1.0a is configured for media uploads
    created_at: datetime
    updated_at: Optional[datetime]
    last_used_at: Optional[datetime]
    
    class Config:
        from_attributes = True
    
    @classmethod
    def from_orm(cls, obj):
        """Custom from_orm to extract default_page_id and oauth1_configured from meta_data"""
        meta_data = obj.meta_data or {}
        oauth1_configured = None
        if obj.platform == "twitter":
            # Check if OAuth 1.0a tokens are configured
            oauth1_configured = meta_data.get("oauth1_configured", False) or bool(
                meta_data.get("oauth1_token") and meta_data.get("oauth1_token_secret")
            )
        
        data = {
            "id": obj.id,
            "tenant_id": obj.tenant_id,
            "assistant_id": obj.assistant_id,
            "platform": obj.platform,
            "platform_user_id": obj.platform_user_id,
            "platform_username": obj.platform_username,
            "platform_name": obj.platform_name,
            "profile_data": obj.profile_data or {},
            "pages": obj.pages or [],
            "organizations": obj.organizations or [],
            "is_active": obj.is_active,
            "is_verified": obj.is_verified,
            "default_page_id": meta_data.get("default_page_id"),
            "oauth1_configured": oauth1_configured,
            "created_at": obj.created_at,
            "updated_at": obj.updated_at,
            "last_used_at": obj.last_used_at,
        }
        return cls(**data)


class SocialIntegrationListResponse(BaseModel):
    """List of social integrations"""
    integrations: List[SocialIntegrationResponse]
    total: int


class IntegrationStatusResponse(BaseModel):
    """Integration status for a platform"""
    platform: str
    is_connected: bool
    integration_id: Optional[UUID] = None
    platform_username: Optional[str] = None
    platform_name: Optional[str] = None
    connected_at: Optional[datetime] = None
    is_active: bool = True


class PlatformStatusListResponse(BaseModel):
    """List of platform connection statuses"""
    platforms: List[IntegrationStatusResponse]
    total_connected: int


class DisconnectIntegrationRequest(BaseModel):
    """Request to disconnect an integration"""
    integration_id: UUID


class SetDefaultPageRequest(BaseModel):
    """Request to set default page/organization"""
    page_id: str = Field(..., description="Page or Organization ID to set as default")

