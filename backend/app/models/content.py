"""
Content Items model - tracks generated content items
"""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, JSON, Integer, Text, BigInteger, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.db.base import Base


class ContentItem(Base):
    __tablename__ = "content_items"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    execution_id = Column(UUID(as_uuid=True), ForeignKey("agent_executions.id"), nullable=True, index=True)
    
    # Content details
    content_type = Column(String(50), nullable=False)  # social_post, ad_copy, email, video_script, blog_post
    platform = Column(String(50), nullable=True)  # facebook, instagram, linkedin, twitter, tiktok
    title = Column(String(500), nullable=True)
    content = Column(Text, nullable=False)
    
    # Optimization
    hashtags = Column(JSON, default=[])
    mentions = Column(JSON, default=[])
    character_count = Column(Integer, nullable=True)
    
    # Publishing
    publish_status = Column(String(50), default="draft")  # draft, scheduled, published, failed
    scheduled_for = Column(DateTime(timezone=True), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    platform_post_id = Column(String(255), nullable=True)  # ID from the external platform
    
    # Assets
    images = Column(JSON, default=[])  # Associated image URLs
    videos = Column(JSON, default=[])  # Associated video URLs
    
    # Performance tracking
    impressions = Column(Integer, default=0)
    reach = Column(Integer, default=0)
    engagements = Column(Integer, default=0)
    clicks = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    
    # Metadata
    meta_data = Column(JSON, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    tenant = relationship("Tenant", backref="content_items")
    execution = relationship("AgentExecution", backref="content_items")
    
    def __repr__(self):
        return f"<ContentItem(id={self.id}, type={self.content_type}, platform={self.platform})>"


class ScheduledPost(Base):
    """Scheduled content posts for periodic publishing"""
    __tablename__ = "scheduled_posts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    assistant_id = Column(UUID(as_uuid=True), ForeignKey("assistants.id"), nullable=False, index=True)
    capability_id = Column(UUID(as_uuid=True), ForeignKey("capabilities.id"), nullable=True, index=True)
    
    # Schedule configuration
    name = Column(String(255), nullable=False)  # User-friendly name for the schedule
    schedule_type = Column(String(50), nullable=False)  # one_time, daily, weekly, monthly
    schedule_config = Column(JSON, nullable=False)  # Schedule-specific configuration
    
    # Content generation request
    request = Column(Text, nullable=False)  # The content request/prompt
    platforms = Column(JSON, default=[])  # List of platforms to post to
    include_images = Column(Boolean, default=False)
    include_video = Column(Boolean, default=False)
    requires_approval = Column(Boolean, default=False)  # If true, content waits for manual approval before publishing
    
    # Schedule timing
    start_date = Column(DateTime(timezone=True), nullable=False)  # When to start the schedule
    end_date = Column(DateTime(timezone=True), nullable=True)  # Optional end date
    next_run_at = Column(DateTime(timezone=True), nullable=False, index=True)  # Next scheduled execution
    last_run_at = Column(DateTime(timezone=True), nullable=True)  # Last execution time
    
    # Status
    is_active = Column(Boolean, default=True, index=True)  # Whether the schedule is active
    status = Column(String(50), default="active")  # active, paused, completed, failed
    
    # Execution tracking
    total_runs = Column(Integer, default=0)  # Total number of times executed
    successful_runs = Column(Integer, default=0)  # Number of successful executions
    failed_runs = Column(Integer, default=0)  # Number of failed executions
    
    # Metadata
    meta_data = Column(JSON, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    
    # Relationships
    tenant = relationship("Tenant", backref="scheduled_posts")
    assistant = relationship("Assistant", backref="scheduled_posts")
    capability = relationship("Capability", backref="scheduled_posts")
    
    def __repr__(self):
        return f"<ScheduledPost(id={self.id}, name={self.name}, schedule_type={self.schedule_type}, next_run_at={self.next_run_at})>"

