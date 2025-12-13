"""
RAG Service - Retrieval Augmented Generation using ChromaDB
"""
from typing import List, Dict, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import select
import asyncio
from app.models.document import Document
from app.services.llm.factory import create_llm_service
from app.services.vector_store import get_vector_store_service
from app.utils.logger import logger


class RAGService:
    """Service for RAG (Retrieval Augmented Generation)"""
    
    def __init__(self, db: Session, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.llm_service = create_llm_service()
    
    def retrieve_relevant_context(
        self,
        query: str,
        limit: int = 10,
        assistant_id: Optional[UUID] = None,
        min_similarity: float = 0.3
    ) -> List[Dict[str, str]]:
        """
        Retrieve relevant context from documents using ChromaDB
        
        Args:
            query: User query/question
            limit: Number of relevant chunks to retrieve (increased default to 10)
            assistant_id: Optional assistant ID to filter documents
            min_similarity: Minimum similarity threshold (0.0 to 1.0)
        
        Returns:
            List of relevant document chunks with metadata
        """
        try:
            # Generate embedding for query (async LLM call wrapped in sync)
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            query_embeddings_result = loop.run_until_complete(
                self.llm_service.generate_embeddings([query])
            )
            query_embedding = query_embeddings_result[0] if query_embeddings_result else None
            
            if not query_embedding:
                logger.warning("Failed to generate query embedding")
                return []
            
            # Search ChromaDB
            vector_store = get_vector_store_service()
            results = vector_store.search(
                tenant_id=self.tenant_id,
                query_embedding=query_embedding,
                limit=limit,
                assistant_id=assistant_id,
                min_similarity=min_similarity
            )
            
            if not results:
                logger.info(f"No relevant chunks found for tenant {self.tenant_id} (assistant_id={assistant_id}, min_similarity={min_similarity})")
                return []
            
            # Get document filenames for source attribution (sync DB call)
            document_ids = {r["metadata"].get("document_id") for r in results if r["metadata"].get("document_id")}
            filename_map = {}
            
            if document_ids:
                from app.models.document import DocumentStatus
                docs_query = select(Document).where(
                    Document.tenant_id == self.tenant_id,
                    Document.id.in_([UUID(doc_id) for doc_id in document_ids if doc_id]),
                    Document.status == DocumentStatus.COMPLETED
                )
                docs_result = self.db.execute(docs_query)
                docs = docs_result.scalars().all()
                filename_map = {str(doc.id): doc.filename for doc in docs}
            
            # Format results
            formatted_chunks = []
            for result in results:
                metadata = result["metadata"]
                document_id = metadata.get("document_id", "")
                
                formatted_chunks.append({
                    "content": result["content"],
                    "source": filename_map.get(document_id, "Unknown"),
                    "document_id": document_id,
                    "chunk_index": metadata.get("chunk_index", 0),
                    "similarity": result.get("similarity", 0.0)
                })
            
            logger.info(f"Retrieved {len(formatted_chunks)} relevant chunks from ChromaDB (min_similarity={min_similarity})")
            return formatted_chunks
            
        except Exception as e:
            logger.error(f"RAG retrieval error: {str(e)}", exc_info=True)
            return []
    
    
    def get_context_for_content_creation(
        self,
        user_request: str,
        assistant_id: Optional[UUID] = None
    ) -> str:
        """
        Get formatted context string for content creation
        
        Args:
            user_request: User's content request
            assistant_id: Optional assistant ID
        
        Returns:
            Formatted context string with relevant information
        """
        relevant_chunks = self.retrieve_relevant_context(
            query=user_request,
            limit=5,
            assistant_id=assistant_id
        )
        
        if not relevant_chunks:
            return ""
        
        context_parts = ["RELEVANT CONTEXT FROM KNOWLEDGE BASE:"]
        for i, chunk in enumerate(relevant_chunks, 1):
            context_parts.append(
                f"\n[{i}] Source: {chunk['source']}\n"
                f"Content: {chunk['content'][:500]}..."
            )
        
        return "\n".join(context_parts)

