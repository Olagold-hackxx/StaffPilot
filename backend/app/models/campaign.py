"""
Campaign models - marketing campaigns and their assets
"""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, JSON, Integer, Text, Date, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.db.base import Base


class Campaign(Base):
    __tablename__ = "campaigns"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    execution_id = Column(UUID(as_uuid=True), ForeignKey("agent_executions.id"), nullable=True, index=True)
    
    # Campaign details
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    campaign_type = Column(String(50), nullable=True)  # product_launch, brand_awareness, lead_generation
    
    # NEW: Objective type (conversions, traffic, awareness, leads)
    objective_type = Column(String(50), nullable=True)
    
    # Duration
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    
    # Channels
    channels = Column(JSON, nullable=False)  # ["google_ads", "meta_ads", "email", "social"]
    
    # Budget
    total_budget = Column(Numeric(10, 2), nullable=True)
    currency = Column(String(10), default="USD")  # NEW: Currency code
    budget_allocation = Column(JSON, nullable=True)  # Per channel allocation
    spent_to_date = Column(Numeric(10, 2), default=0)
    
    # NEW: Goal metrics (JSON) - target CPA, ROAS, conversion count
    goal_metrics = Column(JSON, nullable=True)
    
    # Status
    status = Column(String(50), default="draft")  # draft, scheduled, active, paused, completed
    
    # Campaign plan (AI-generated structured JSON)
    plan = Column(JSON, nullable=True)
    
    # NEW: Product/service brief
    product_brief = Column(Text, nullable=True)
    
    # NEW: Creative preference (image, video, both)
    creative_preference = Column(String(20), default="both")
    
    # NEW: Target audience (structured JSON)
    # {countries: [], age_range: [min, max], interests: [], gender: "all|male|female"}
    target_audience = Column(JSON, nullable=True)
    
    # Performance
    metrics = Column(JSON, default={})
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    tenant = relationship("Tenant", backref="campaigns")
    execution = relationship("AgentExecution", backref="campaigns")
    assets = relationship("CampaignAsset", back_populates="campaign", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Campaign(id={self.id}, name={self.name}, status={self.status})>"



class CampaignAsset(Base):
    __tablename__ = "campaign_assets"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False, index=True)
    content_item_id = Column(UUID(as_uuid=True), ForeignKey("content_items.id"), nullable=True, index=True)
    
    # Asset details
    asset_type = Column(String(50), nullable=True)  # ad, email, social_post, landing_page
    platform = Column(String(50), nullable=True)  # google_ads, facebook, instagram, email
    
    # Platform-specific IDs
    platform_asset_id = Column(String(255), nullable=True)  # ID in the external platform
    
    # Status
    status = Column(String(50), default="draft")  # draft, scheduled, active, paused, completed
    launched_at = Column(DateTime(timezone=True), nullable=True)
    
    # Performance
    impressions = Column(Integer, default=0)
    clicks = Column(Integer, default=0)
    conversions = Column(Integer, default=0)
    spend = Column(Numeric(10, 2), default=0)
    
    # Metadata
    meta_data = Column(JSON, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    campaign = relationship("Campaign", back_populates="assets")
    content_item = relationship("ContentItem", backref="campaign_assets")
    
    def __repr__(self):
        return f"<CampaignAsset(id={self.id}, type={self.asset_type}, platform={self.platform})>"


class CampaignContext(Base):
    """
    Stores structured facts and context extracted from campaign conversations.
    This enables the chatbot to remember decisions and approved suggestions.
    """
    __tablename__ = "campaign_contexts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False, index=True)
    
    # Context data stored as key-value pairs (JSON)
    # Examples: {"target_audience": "...", "approved_headlines": [...], "brand_voice": "..."}
    context_data = Column(JSON, nullable=False, default={})
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    campaign = relationship("Campaign", backref="contexts")
    
    def __repr__(self):
        return f"<CampaignContext(id={self.id}, campaign_id={self.campaign_id})>"


class ChatTranscript(Base):
    """
    Stores chat messages within a campaign context.
    Messages can be embedded for semantic retrieval.
    """
    __tablename__ = "chat_transcripts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False, index=True)
    
    # Message details
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    
    # Embedding reference for vector search
    embedding_id = Column(String(255), nullable=True)  # Reference to vector store
    
    # Priority flag for context inclusion
    is_pinned = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    campaign = relationship("Campaign", backref="chat_transcripts")
    
    def __repr__(self):
        return f"<ChatTranscript(id={self.id}, campaign_id={self.campaign_id}, role={self.role})>"


class CreativeRequest(Base):
    """
    Tracks creative generation requests within a campaign.
    Supports both image and video creatives with status tracking.
    """
    __tablename__ = "creative_requests"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False, index=True)
    
    # Creative type
    creative_type = Column(String(20), nullable=False)  # image, video
    
    # Request parameters (JSON)
    # For images: prompt, aspect_ratio, brand_colors, headline, cta, etc.
    # For videos: storyboard, voice, music_mood, duration, etc.
    parameters = Column(JSON, nullable=False, default={})
    
    # Status
    status = Column(String(50), default="pending")  # pending, processing, completed, failed
    
    # Render job reference for async tracking
    render_job_id = Column(String(255), nullable=True)
    
    # Output files (array of URLs)
    output_files = Column(JSON, nullable=True, default=[])  # List of media URLs
    
    # Storyboard (for videos)
    storyboard = Column(JSON, nullable=True)  # Scene-by-scene breakdown
    
    # Approval status
    is_approved = Column(Boolean, default=False)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    
    # Metadata
    meta_data = Column(JSON, default={})
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    campaign = relationship("Campaign", backref="creative_requests")
    
    def __repr__(self):
        return f"<CreativeRequest(id={self.id}, campaign_id={self.campaign_id}, type={self.creative_type}, status={self.status})>"

