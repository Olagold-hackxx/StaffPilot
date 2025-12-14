"""
Pydantic schemas for Document
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict
from datetime import datetime
from uuid import UUID
from app.models.document import DocumentStatus, DocumentType


class DocumentUploadResponse(BaseModel):
    """Response after document upload"""
    id: UUID
    filename: str
    file_type: DocumentType
    file_size: int
    status: DocumentStatus
    created_at: datetime
    meta_data: Dict = {}
    
    class Config:
        from_attributes = True


class DocumentResponse(BaseModel):
    """Full document response"""
    id: UUID
    tenant_id: UUID
    assistant_id: Optional[UUID]
    filename: str
    original_filename: str
    file_type: DocumentType
    file_size: int
    storage_url: Optional[str]
    content_preview: Optional[str]
    status: DocumentStatus
    chunk_count: int
    embedding_count: int
    processing_error: Optional[str]
    meta_data: Dict
    created_at: datetime
    updated_at: Optional[datetime]
    processed_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]
    total: int


class DocumentUpdate(BaseModel):
    assistant_id: Optional[UUID] = None
    meta_data: Optional[Dict] = None

