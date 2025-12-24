"""
Brand Assets model - stores reusable images/videos for AI content generation
"""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, JSON, Integer, Text, BigInteger
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.db.base import Base


class BrandAsset(Base):
    """
    Stores brand assets (images, videos) that can be used as references
    for AI image/video generation with Gemini/Veo.
    """
    __tablename__ = "brand_assets"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=True, index=True)  # Optional - can be tenant-wide
    
    # Asset identity
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    asset_type = Column(String(50), nullable=False)  # "image", "video"
    source = Column(String(50), default="upload")  # "upload", "google_drive"
    
    # Storage
    url = Column(String(1024), nullable=False)  # Cloud storage URL
    thumbnail_url = Column(String(1024), nullable=True)  # For videos
    external_id = Column(String(255), nullable=True)  # Google Drive file ID if imported
    
    # File metadata
    file_name = Column(String(255), nullable=True)
    file_size = Column(BigInteger, nullable=True)  # bytes
    mime_type = Column(String(100), nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    duration = Column(Integer, nullable=True)  # For videos, in seconds
    
    # Usage tracking
    usage_count = Column(Integer, default=0)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    
    # Status
    is_active = Column(Boolean, default=True)
    meta_data = Column(JSON, default={})
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    
    # Relationships
    tenant = relationship("Tenant", backref="brand_assets")
    campaign = relationship("Campaign", backref="brand_assets")
    
    def __repr__(self):
        return f"<BrandAsset(id={self.id}, name={self.name}, type={self.asset_type})>"
