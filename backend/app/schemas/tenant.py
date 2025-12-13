"""
Pydantic schemas for Tenant
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Dict
from datetime import datetime
from uuid import UUID


class TenantBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: Optional[str] = Field(None, min_length=1, max_length=100)
    domain: Optional[str] = None
    brand_voice: str = "professional"
    target_audience: Optional[str] = None
    offerings: Optional[str] = None
    website_url: Optional[str] = None  # Website URL for campaigns/ads
    custom_config: Dict = {}


class TenantCreate(TenantBase):
    pass


class TenantUpdate(BaseModel):
    name: Optional[str] = None
    domain: Optional[str] = None
    brand_voice: Optional[str] = None
    target_audience: Optional[str] = None
    offerings: Optional[str] = None
    website_url: Optional[str] = None  # Website URL for campaigns/ads
    custom_config: Optional[Dict] = None


class TenantResponse(TenantBase):
    id: UUID
    subscription_status: str
    subscription_plan: str
    is_active: bool
    is_onboarded: bool
    website_url: Optional[str] = None  # Website URL for campaigns/ads
    created_at: datetime
    updated_at: Optional[datetime]
    trial_ends_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class TenantListResponse(BaseModel):
    tenants: list[TenantResponse]
    total: int

