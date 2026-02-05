"""
Pydantic schemas for Tenant
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Dict, List
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
    brand_colors: List[str] = []  # Array of hex color codes, e.g. ["#FF5733", "#3498DB"]


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
    brand_colors: Optional[List[str]] = None  # Array of hex color codes


class TenantResponse(TenantBase):
    id: UUID
    subscription_status: str
    subscription_plan: str
    is_active: bool
    is_onboarded: bool
    website_url: Optional[str] = None  # Website URL for campaigns/ads
    brand_colors: List[str] = []  # Array of hex color codes
    created_at: datetime
    updated_at: Optional[datetime]
    trial_ends_at: Optional[datetime]
    
    from pydantic import field_validator
    
    @field_validator('brand_colors', mode='before')
    @classmethod
    def default_brand_colors(cls, v):
        return v if v is not None else []
    
    class Config:
        from_attributes = True


class TenantListResponse(BaseModel):
    tenants: list[TenantResponse]
    total: int

