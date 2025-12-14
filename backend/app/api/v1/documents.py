"""
Document API routes
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID
from app.db.session import get_db
from app.dependencies import get_current_user, get_current_tenant
from app.models.user import User
from app.models.tenant import Tenant
from app.schemas.document import DocumentUploadResponse, DocumentResponse, DocumentListResponse, DocumentUpdate
from app.services.document_service import DocumentService
from app.models.document import DocumentStatus

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    assistant_id: Optional[UUID] = Form(None),
    required_type: Optional[str] = Form(None),
    current_tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload a document for processing"""
    service = DocumentService(db)
    
    document = await service.upload_document(
        tenant_id=current_tenant.id,
        file=file.file,
        filename=file.filename,
        assistant_id=assistant_id,
        uploaded_by=current_user.id,
        required_type=required_type
    )
    
    return document


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    assistant_id: Optional[UUID] = None,
    status: Optional[DocumentStatus] = None,
    limit: int = 50,
    offset: int = 0,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """List documents for current tenant"""
    service = DocumentService(db)
    documents, total = await service.list_documents(
        tenant_id=current_tenant.id,
        assistant_id=assistant_id,
        status=status,
        limit=limit,
        offset=offset
    )
    return DocumentListResponse(documents=documents, total=total)


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """Get document by ID"""
    service = DocumentService(db)
    document = await service.get_document(
        document_id=document_id,
        tenant_id=current_tenant.id
    )
    return document


@router.get("/{document_id}/download")
async def download_document(
    document_id: UUID,
    expires_in: int = 3600,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """Get download URL for document"""
    service = DocumentService(db)
    url = await service.get_document_url(
        document_id=document_id,
        tenant_id=current_tenant.id,
        expires_in=expires_in
    )
    return {"url": url}


@router.patch("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: UUID,
    document_data: DocumentUpdate,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """Update document metadata"""
    service = DocumentService(db)
    document = await service.get_document(
        document_id=document_id,
        tenant_id=current_tenant.id
    )
    
    update_data = document_data.model_dump(exclude_unset=True)
    if "meta_data" in update_data:
        document.meta_data = update_data["meta_data"]
    if "assistant_id" in update_data:
        document.assistant_id = update_data["assistant_id"]
    
    await db.commit()
    await db.refresh(document)
    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """Delete document"""
    service = DocumentService(db)
    await service.delete_document(
        document_id=document_id,
        tenant_id=current_tenant.id
    )
    return None

