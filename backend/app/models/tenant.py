"""
Tenant model - represents a business/organization using StaffPilot
"""
from sqlalchemy import Column, String, Boolean, DateTime, JSON, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from datetime import datetime
import uuid
from app.db.base import Base


class Tenant(Base):
    __tablename__ = "tenants"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    domain = Column(String(255), nullable=True)
    
    # Subscription & Billing
    subscription_status = Column(String(50), default="trial")  # trial, active, cancelled, expired
    subscription_plan = Column(String(50), default="starter")  # starter, professional, enterprise
    stripe_customer_id = Column(String(255), nullable=True)
    stripe_subscription_id = Column(String(255), nullable=True)
    
    # Configuration
    brand_voice = Column(String(100), default="professional")
    target_audience = Column(Text, nullable=True)
    offerings = Column(Text, nullable=True)
    website_url = Column(String(500), nullable=True)  # Website URL for links in content/campaigns
    custom_config = Column(JSON, default={})
    
    # Google Drive Integration
    google_drive_tokens = Column(JSON, nullable=True)  # OAuth tokens for Drive access
    
    # Status
    is_active = Column(Boolean, default=True)
    is_onboarded = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)
    
    def __repr__(self):
        return f"<Tenant(id={self.id}, name={self.name}, slug={self.slug})>"

