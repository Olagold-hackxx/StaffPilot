"""
Document service - handles document upload and processing
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional, BinaryIO
from uuid import UUID
from datetime import datetime
import uuid
from app.models.document import Document, DocumentStatus, DocumentType
from app.models.tenant import Tenant
from app.services.storage import get_storage
from app.utils.errors import TenantNotFoundError, DocumentNotFoundError, ValidationError
from app.utils.logger import logger


class DocumentService:
    """Service for handling documents"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.storage = get_storage()
    
    def _get_file_type(self, filename: str) -> DocumentType:
        """Determine file type from filename"""
        ext = filename.lower().split('.')[-1]
        type_map = {
            'pdf': DocumentType.PDF,
            'docx': DocumentType.DOCX,
            'txt': DocumentType.TXT,
            'md': DocumentType.MD,
            'markdown': DocumentType.MD,
            'html': DocumentType.HTML,
            'htm': DocumentType.HTML,
            'csv': DocumentType.CSV,
            'json': DocumentType.JSON,
        }
        return type_map.get(ext, DocumentType.OTHER)
    
    async def upload_document(
        self,
        tenant_id: UUID,
        file: BinaryIO,
        filename: str,
        assistant_id: Optional[UUID] = None,
        uploaded_by: Optional[UUID] = None,
        required_type: Optional[str] = None
    ) -> Document:
        """Upload a document"""
        # Verify tenant exists
        result = await self.db.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        tenant = result.scalar_one_or_none()
        
        if not tenant:
            raise TenantNotFoundError(str(tenant_id))
        
        # Determine file type
        file_type = self._get_file_type(filename)
        
        # Validate file type - only allow txt, md, pdf, docx
        allowed_types = [DocumentType.TXT, DocumentType.MD, DocumentType.PDF, DocumentType.DOCX]
        if file_type not in allowed_types:
            raise ValidationError(
                f"File type '{file_type.value}' is not allowed. Only TXT, MD, PDF, and DOCX files are supported."
            )
        
        # Read file content
        file.seek(0)
        file_content = file.read()
        file_size = len(file_content)
        
        # Generate storage key
        storage_key = f"tenants/{tenant_id}/documents/{uuid.uuid4()}/{filename}"
        
        # Upload to storage
        file.seek(0)  # Reset file pointer
        content_type = f"application/{file_type.value}"
        storage_url = await self.storage.upload(
            key=storage_key,
            file=file,
            content_type=content_type
        )
        
        # Prepare metadata
        meta_data = {}
        if required_type:
            meta_data["required_type"] = required_type
            meta_data["document_category"] = "required"
        
        # Create document record
        document = Document(
            tenant_id=tenant_id,
            assistant_id=assistant_id,
            uploaded_by=uploaded_by,
            filename=filename,
            original_filename=filename,
            file_type=file_type,
            file_size=file_size,
            storage_key=storage_key,
            storage_url=storage_url,
            content_preview=file_content[:500].decode('utf-8', errors='ignore').replace('\x00', '') if file_type in [DocumentType.TXT, DocumentType.MD, DocumentType.HTML, DocumentType.CSV, DocumentType.JSON] else None,
            meta_data=meta_data,
            status=DocumentStatus.PENDING
        )
        
        self.db.add(document)
        await self.db.commit()
        await self.db.refresh(document)
        
        logger.info(f"Uploaded document {document.id} for tenant {tenant_id}")
        
        # Trigger background processing task
        from app.workers.ingestion import process_document
        process_document.delay(str(document.id))
        
        return document
    
    async def get_document(
        self,
        document_id: UUID,
        tenant_id: UUID
    ) -> Document:
        """Get document by ID"""
        result = await self.db.execute(
            select(Document).where(
                Document.id == document_id,
                Document.tenant_id == tenant_id
            )
        )
        document = result.scalar_one_or_none()
        
        if not document:
            raise DocumentNotFoundError(str(document_id))
        
        return document
    
    async def list_documents(
        self,
        tenant_id: UUID,
        assistant_id: Optional[UUID] = None,
        status: Optional[DocumentStatus] = None,
        limit: int = 50,
        offset: int = 0
    ) -> tuple[List[Document], int]:
        """List documents for a tenant"""
        query = select(Document).where(Document.tenant_id == tenant_id)
        
        if assistant_id:
            query = query.where(Document.assistant_id == assistant_id)
        
        if status:
            query = query.where(Document.status == status)
        
        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        count_result = await self.db.execute(count_query)
        total = count_result.scalar_one()
        
        # Get documents
        query = query.order_by(Document.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(query)
        documents = result.scalars().all()
        
        return list(documents), total
    
    async def delete_document(
        self,
        document_id: UUID,
        tenant_id: UUID
    ) -> bool:
        """Delete a document"""
        document = await self.get_document(document_id, tenant_id)
        
        # Delete from ChromaDB
        try:
            from app.services.vector_store import get_vector_store_service
            vector_store = get_vector_store_service()
            vector_store.delete_document_chunks(
                tenant_id=tenant_id,
                document_id=document_id,
                assistant_id=document.assistant_id
            )
            logger.info(f"Deleted chunks from ChromaDB for document {document_id}")
        except Exception as e:
            logger.warning(f"Failed to delete chunks from ChromaDB: {str(e)}")
            # Continue with other deletions
        
        # Delete from storage
        try:
            await self.storage.delete(document.storage_key)
        except Exception as e:
            logger.warning(f"Failed to delete document from storage: {str(e)}")
            # Continue with database deletion even if storage deletion fails
        
        # Delete from database
        # Use the same pattern as integration_service
        # In SQLAlchemy 2.0 async, delete() is available on the session
        await self.db.delete(document)
        await self.db.commit()
        
        logger.info(f"Deleted document {document_id} for tenant {tenant_id}")
        return True
    
    async def get_document_url(
        self,
        document_id: UUID,
        tenant_id: UUID,
        expires_in: int = 3600
    ) -> str:
        """Get signed URL for document"""
        document = await self.get_document(document_id, tenant_id)
        return await self.storage.get_url(document.storage_key, expires_in)

