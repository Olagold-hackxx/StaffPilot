"""
Document model - represents documents uploaded for RAG ingestion
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, Text, Integer, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
import enum
from app.db.base import Base


class DocumentStatus(str, enum.Enum):
    """Document processing status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentType(str, enum.Enum):
    """Document types"""
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    MD = "markdown"
    HTML = "html"
    CSV = "csv"
    JSON = "json"
    OTHER = "other"
    AI_GENERATED = "ai_generated"  # For Quick Setup AI-generated knowledge chunks


class Document(Base):
    __tablename__ = "documents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    assistant_id = Column(UUID(as_uuid=True), ForeignKey("assistants.id"), nullable=True, index=True)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    
    # File information
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_type = Column(Enum(DocumentType), nullable=False)
    file_size = Column(Integer, nullable=False)  # Size in bytes
    storage_key = Column(String(500), nullable=False)  # S3 key or local path
    storage_url = Column(String(500), nullable=True)  # Public/signed URL
    
    # Content
    content_preview = Column(Text, nullable=True)  # First 500 chars
    extracted_text = Column(Text, nullable=True)  # Full extracted text
    meta_data = Column(JSON, default={})  # File metadata (pages, author, etc.)
    
    # Processing
    status = Column(Enum(DocumentStatus), default=DocumentStatus.PENDING)
    chunk_count = Column(Integer, default=0)  # Number of chunks created
    embedding_count = Column(Integer, default=0)  # Number of embeddings generated
    processing_error = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    tenant = relationship("Tenant", backref="documents")
    assistant = relationship("Assistant", backref="documents")
    
    def __repr__(self):
        return f"<Document(id={self.id}, filename={self.filename}, status={self.status})>"

