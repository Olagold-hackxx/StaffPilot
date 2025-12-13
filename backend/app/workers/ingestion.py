"""
Document ingestion and processing tasks
"""
from app.workers import celery_app
from app.utils.logger import logger
from uuid import UUID
import asyncio
import io
from typing import Dict, Any
from datetime import datetime, timezone


@celery_app.task(name="process_document", bind=True, max_retries=3)
def process_document(self, document_id: str):
    """
    Process a document: extract text, chunk, generate embeddings
    
    Steps:
    1. Download document from storage
    2. Extract text (PDF, DOCX, TXT, etc.)
    3. Chunk text into manageable pieces
    4. Generate embeddings for each chunk
    5. Store embeddings (for now, just store chunks in DB)
    6. Update document status
    """
    try:
        logger.info(f"Processing document {document_id}")
        
        # Run async function in sync context
        # Create a new event loop for this task
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        async def _process():
            from app.db.session import create_worker_session_factory
            from app.models.document import Document, DocumentStatus
            from app.services.storage import get_storage
            from sqlalchemy import select
            from app.services.llm.factory import create_llm_service
            
            # Create a new session factory for this worker task
            # This ensures complete isolation from other tasks
            SessionFactory = create_worker_session_factory()
            db = SessionFactory()
            try:
                # Get document (sync DB call)
                result = db.execute(
                    select(Document).where(Document.id == UUID(document_id))
                )
                document = result.scalar_one_or_none()
                
                if not document:
                    logger.error(f"Document {document_id} not found")
                    return {"success": False, "error": "Document not found"}
                
                # Update status to processing
                document.status = DocumentStatus.PROCESSING
                # Note: processing_started_at field may not exist in model
                # If it does, uncomment: document.processing_started_at = datetime.now(timezone.utc)
                db.commit()
                
                try:
                    # Step 1: Download document from storage
                    logger.info(f"Downloading document {document_id} from storage")
                    storage = get_storage()
                    file_content = await storage.download(document.storage_key)
                    
                    # Step 2: Extract text based on file type
                    logger.info(f"Extracting text from {document.filename}")
                    extracted_text = _extract_text(file_content, document.file_type, document.filename)
                    
                    if not extracted_text:
                        raise ValueError("Failed to extract text from document")
                    
                    # Step 3: Chunk text
                    logger.info(f"Chunking text for document {document_id} (text length: {len(extracted_text)} chars)")
                    chunks = _chunk_text(extracted_text)
                    logger.info(f"Created {len(chunks)} chunks for document {document_id}")
                    
                    # Step 4: Generate embeddings for each chunk
                    logger.info(f"Generating embeddings for {len(chunks)} chunks")
                    llm_service = create_llm_service()
                    
                    chunk_embeddings = []
                    for i, chunk_text in enumerate(chunks):
                        try:
                            # generate_embeddings expects a list of texts
                            embeddings_result = await llm_service.generate_embeddings([chunk_text])
                            # Extract the first (and only) embedding from the result
                            embedding = embeddings_result[0] if embeddings_result else None
                            
                            if embedding:
                                chunk_embeddings.append({
                                    "chunk_index": i,
                                    "content": chunk_text,
                                    "embedding": embedding,
                                    "token_count": len(chunk_text.split())
                                })
                            else:
                                logger.warning(f"No embedding generated for chunk {i}")
                        except Exception as e:
                            logger.warning(f"Failed to generate embedding for chunk {i}: {str(e)}")
                            # Continue with other chunks
                    
                    # Step 5: Store chunks and embeddings in ChromaDB
                    if chunk_embeddings:
                        from app.services.vector_store import get_vector_store_service
                        vector_store = get_vector_store_service()
                        
                        vector_store.add_document_chunks(
                            tenant_id=document.tenant_id,
                            document_id=document.id,
                            chunks=chunk_embeddings,
                            assistant_id=document.assistant_id
                        )
                        logger.info(f"Stored {len(chunk_embeddings)} chunks in ChromaDB for document {document_id}")
                    
                    # Store extracted text and chunk count in DB
                    document.extracted_text = extracted_text
                    document.chunk_count = len(chunks)
                    document.embedding_count = len(chunk_embeddings)
                    document.status = DocumentStatus.COMPLETED
                    document.processed_at = datetime.now(timezone.utc)
                    
                    # Store chunk metadata
                    document.meta_data = {
                        **(document.meta_data or {}),
                        "chunks": len(chunks),
                        "embeddings_generated": len(chunk_embeddings),
                        "total_tokens": sum(c["token_count"] for c in chunk_embeddings),
                        "vector_store": "chromadb"
                    }
                    
                    db.commit()
                    db.refresh(document)
                    
                    logger.info(f"Document {document_id} processing completed: {len(chunks)} chunks, {len(chunk_embeddings)} embeddings stored in ChromaDB")
                    
                    return {
                        "success": True,
                        "document_id": document_id,
                        "chunks": len(chunks),
                        "embeddings": len(chunk_embeddings)
                    }
                
                except Exception as e:
                    logger.error(f"Error processing document {document_id}: {str(e)}")
                    document.status = DocumentStatus.FAILED
                    document.processing_error = str(e)
                    db.commit()
                    raise
            finally:
                db.close()
        
        result = loop.run_until_complete(_process())
        loop.close()
        return result
    
    except Exception as e:
        logger.error(f"Document processing failed: {str(e)}")
        raise self.retry(exc=e, countdown=60)


def _extract_text(file_content: bytes, file_type, filename: str = "") -> str:
    """Extract text from document based on file type"""
    try:
        if file_type.value == "txt" or file_type.value == "md":
            return file_content.decode('utf-8', errors='ignore')
        
        elif file_type.value == "pdf":
            try:
                import PyPDF2
                pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_content))
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                return text
            except ImportError:
                logger.warning("PyPDF2 not installed, cannot extract PDF text")
                return ""
            except Exception as e:
                logger.error(f"PDF extraction error: {str(e)}")
                return ""
        
        elif file_type.value == "docx":
            try:
                from docx import Document as DocxDocument
                doc = DocxDocument(io.BytesIO(file_content))
                text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
                return text
            except ImportError:
                logger.warning("python-docx not installed, cannot extract DOCX text")
                return ""
            except Exception as e:
                logger.error(f"DOCX extraction error: {str(e)}")
                return ""
       
        
        else:
            # Try to decode as text
            return file_content.decode('utf-8', errors='ignore')
    
    except Exception as e:
        logger.error(f"Text extraction error: {str(e)}")
        return ""


def _chunk_text(text: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> list[str]:
    """Split text into chunks with optimized algorithm for large texts"""
    if not text:
        return []
    
    # For very large texts, use a more efficient approach
    text_length = len(text)
    if text_length > 1000000:  # 1MB of text
        logger.info(f"Large text detected ({text_length} chars), using optimized chunking")
    
    chunks = []
    start = 0
    max_iterations = (text_length // chunk_size) + 100  # Safety limit
    iteration = 0
    
    while start < text_length and iteration < max_iterations:
        iteration += 1
        end = min(start + chunk_size, text_length)
        
        # For the last chunk, just take everything
        if end >= text_length:
            chunk = text[start:].strip()
            if chunk:  # Only add non-empty chunks
                chunks.append(chunk)
            break
        
        chunk = text[start:end]
        
        # Try to break at sentence boundary (only if we're not at the end)
        if end < text_length:
            # Look for sentence endings, prioritizing newlines and periods
            best_break = -1
            for punct in ['.\n', '.\n\n', '!\n', '?\n', '. ', '! ', '? ', '\n\n', '\n']:
                last_punct = chunk.rfind(punct)
                if last_punct > chunk_size * 0.5:  # Only break if we're past halfway
                    if last_punct > best_break:
                        best_break = last_punct + len(punct)
            
            if best_break > 0:
                chunk = chunk[:best_break].strip()
                end = start + best_break
            else:
                # If no good break point, try to break at word boundary
                last_space = chunk.rfind(' ')
                if last_space > chunk_size * 0.7:  # Only if we're past 70% of chunk size
                    chunk = chunk[:last_space].strip()
                    end = start + last_space + 1
        
        if chunk.strip():  # Only add non-empty chunks
            chunks.append(chunk.strip())
        
        # Move start position with overlap
        start = max(start + 1, end - chunk_overlap)
    
    if iteration >= max_iterations:
        logger.warning(f"Chunking reached max iterations ({max_iterations}), text may be too large or malformed")
    
    logger.info(f"Chunking complete: {len(chunks)} chunks created from {text_length} chars")
    return chunks


@celery_app.task(name="generate_embeddings", bind=True, max_retries=3)
def generate_embeddings(self, chunk_id: str, text: str):
    """
    Generate embeddings for a text chunk
    
    Args:
        chunk_id: Chunk identifier
        text: Text to generate embeddings for
    
    Returns:
        Dictionary with embedding vector
    """
    try:
        logger.info(f"Generating embeddings for chunk {chunk_id}")
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def _generate():
            from app.services.llm.factory import create_llm_service
            
            llm_service = create_llm_service()
            embedding = await llm_service.generate_embeddings(text)
            
            return {
                "success": True,
                "chunk_id": chunk_id,
                "embedding": embedding,
                "dimension": len(embedding) if embedding else 0
            }
        
        result = loop.run_until_complete(_generate())
        loop.close()
        return result
    
    except Exception as e:
        logger.error(f"Embedding generation failed: {str(e)}")
        raise self.retry(exc=e, countdown=30)
