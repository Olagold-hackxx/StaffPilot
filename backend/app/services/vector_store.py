"""
Vector Store Service using ChromaDB
"""
import os
import hashlib
import logging

# Disable ChromaDB telemetry BEFORE importing chromadb
# Force set these environment variables to ensure telemetry is disabled
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_TELEMETRY_DISABLED"] = "1"
# Also disable posthog telemetry (used by ChromaDB)
os.environ["POSTHOG_DISABLED"] = "1"

# Suppress ChromaDB telemetry error logs
logging.getLogger("chromadb.telemetry").setLevel(logging.CRITICAL)
logging.getLogger("chromadb.telemetry.product").setLevel(logging.CRITICAL)
logging.getLogger("posthog").setLevel(logging.CRITICAL)

import chromadb
from chromadb.config import Settings as ChromaSettings
from typing import List, Dict, Optional
from uuid import UUID
from app.config import settings
from app.utils.logger import logger


class VectorStoreService:
    """Service for managing vector embeddings in ChromaDB"""
    
    def __init__(self):
        """Initialize ChromaDB client - supports both local and HTTP modes"""
        # Check if HTTP mode is configured (for production with separate services)
        if settings.CHROMA_HTTP_HOST:
            # Use HTTP client for connecting to remote ChromaDB server
            logger.info(f"Connecting to ChromaDB server at {settings.CHROMA_HTTP_HOST}:{settings.CHROMA_HTTP_PORT}")
            self.client = chromadb.HttpClient(
                host=settings.CHROMA_HTTP_HOST,
                port=settings.CHROMA_HTTP_PORT,
                settings=ChromaSettings(
                    anonymized_telemetry=False,
                )
            )
            self.mode = "http"
        else:
            # Use local persistent client
            self.db_path = settings.CHROMA_DB_PATH
            # Ensure directory exists
            os.makedirs(self.db_path, exist_ok=True)
            
            logger.info(f"Using local ChromaDB at {self.db_path}")
            self.client = chromadb.PersistentClient(
                path=self.db_path,
                settings=ChromaSettings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            self.mode = "local"
    
    def get_collection(self, tenant_id: UUID, assistant_id: Optional[UUID] = None) -> chromadb.Collection:
        """
        Get or create a collection for a tenant/assistant
        
        Args:
            tenant_id: Tenant UUID
            assistant_id: Optional assistant UUID
        
        Returns:
            ChromaDB Collection
        """
        # ChromaDB collection names must:
        # - Be 3-63 characters
        # - Start and end with alphanumeric
        # - Contain only alphanumeric, underscores, or hyphens
        # - No consecutive periods
        # - Not be a valid IPv4 address
        # UUIDs contain hyphens, so we'll use a hash-based collection name to ensure it meets ChromaDB requirements
        if assistant_id:
            # Combine tenant and assistant IDs, hash them, and use first 32 chars
            combined = f"{tenant_id}_{assistant_id}"
            collection_hash = hashlib.md5(combined.encode()).hexdigest()
            collection_name = f"t_{collection_hash}_a"
        else:
            # Hash tenant ID
            tenant_str = str(tenant_id).replace("-", "")
            collection_hash = hashlib.md5(tenant_str.encode()).hexdigest()
            collection_name = f"t_{collection_hash}"
        
        try:
            collection = self.client.get_collection(name=collection_name)
        except Exception as e:
            error_msg = str(e).lower()
            # Check if this is a collection name validation error (likely from old collection format)
            # Don't try to list collections here as that might trigger the same error
            if "expected collection name" in error_msg or "invalid" in error_msg:
                logger.warning(f"ChromaDB collection name validation error (likely from old collection): {str(e)[:200]}. Creating new collection with hash-based name.")
            
            # Collection doesn't exist or had invalid name, create it
            # ChromaDB doesn't allow None values in metadata, use empty string instead
            try:
                collection = self.client.create_collection(
                    name=collection_name,
                    metadata={"tenant_id": str(tenant_id), "assistant_id": str(assistant_id) if assistant_id else ""}
                )
            except Exception as create_error:
                # If creation fails, log the error and re-raise with context
                create_error_msg = str(create_error).lower()
                if "expected collection name" in create_error_msg:
                    logger.error(f"Collection name '{collection_name}' still fails validation. This should not happen with hash-based names. Hash: {collection_hash[:16]}...")
                raise ValueError(f"Failed to create ChromaDB collection '{collection_name}': {str(create_error)}") from create_error
        
        return collection
    
    def add_document_chunks(
        self,
        tenant_id: UUID,
        document_id: UUID,
        chunks: List[Dict[str, any]],
        assistant_id: Optional[UUID] = None
    ) -> bool:
        """
        Add document chunks with embeddings to ChromaDB
        
        Args:
            tenant_id: Tenant UUID
            document_id: Document UUID
            chunks: List of chunk dicts with keys: chunk_index, content, embedding
            assistant_id: Optional assistant UUID
        
        Returns:
            True if successful
        """
        try:
            collection = self.get_collection(tenant_id, assistant_id)
            
            # Prepare data for ChromaDB
            ids = []
            embeddings = []
            documents = []
            metadatas = []
            
            for chunk in chunks:
                chunk_id = f"{document_id}_{chunk['chunk_index']}"
                ids.append(chunk_id)
                embeddings.append(chunk['embedding'])
                documents.append(chunk['content'])
                # ChromaDB doesn't allow None values in metadata - ensure all values are strings, ints, floats, or bools
                metadata = {
                    "document_id": str(document_id),
                    "chunk_index": int(chunk.get('chunk_index', 0)),
                    "tenant_id": str(tenant_id),
                    "assistant_id": str(assistant_id) if assistant_id else ""
                }
                # Add token_count if available (must be int or float, not None)
                if 'token_count' in chunk and chunk['token_count'] is not None:
                    metadata["token_count"] = int(chunk['token_count'])
                metadatas.append(metadata)
            
            # Add to collection
            collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to add chunks to ChromaDB: {str(e)}")
            raise
    
    def delete_document_chunks(
        self,
        tenant_id: UUID,
        document_id: UUID,
        assistant_id: Optional[UUID] = None
    ) -> bool:
        """
        Delete all chunks for a document from ChromaDB
        
        Args:
            tenant_id: Tenant UUID
            document_id: Document UUID
            assistant_id: Optional assistant UUID
        
        Returns:
            True if successful
        """
        try:
            collection = self.get_collection(tenant_id, assistant_id)
            
            # Get all chunks for this document
            results = collection.get(
                where={"document_id": str(document_id)}
            )
            
            if results['ids']:
                collection.delete(ids=results['ids'])
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete chunks from ChromaDB: {str(e)}")
            raise
    
    def search(
        self,
        tenant_id: UUID,
        query_embedding: List[float],
        limit: int = 10,
        assistant_id: Optional[UUID] = None,
        min_similarity: float = 0.0,
        where: Optional[Dict] = None
    ) -> List[Dict]:
        """
        Search for similar chunks using query embedding
        
        When assistant_id is provided, searches both:
        1. Assistant-specific collection (if assistant_id is set)
        2. General tenant collection (documents without assistant_id)
        
        This ensures documents uploaded without an assistant_id are still found.
        
        Args:
            tenant_id: Tenant UUID
            query_embedding: Query embedding vector
            limit: Number of results to return
            assistant_id: Optional assistant UUID
            min_similarity: Minimum similarity score (0.0 to 1.0)
            where: Optional metadata filter
        
        Returns:
            List of matching chunks with metadata
        """
        # Define error pattern for invalid collection names
        INVALID_COLLECTION_NAME_PATTERNS = ["expected collection name", "invalid", "collection name"]
        all_chunks = []
        
        try:
            # If assistant_id is provided, search both assistant-specific and general collections
            collections_to_search = []
            
            if assistant_id:
                # Search assistant-specific collection
                try:
                    assistant_collection = self.get_collection(tenant_id, assistant_id)
                    collections_to_search.append(("assistant", assistant_collection))
                except Exception as ve:
                    error_msg = str(ve).lower()
                    if not any(pattern in error_msg for pattern in INVALID_COLLECTION_NAME_PATTERNS):
                        logger.warning(f"Failed to get assistant collection: {str(ve)[:200]}")
            
            # Always search general tenant collection (documents without assistant_id)
            try:
                general_collection = self.get_collection(tenant_id, None)
                collections_to_search.append(("general", general_collection))
            except Exception as ve:
                error_msg = str(ve).lower()
                if not any(pattern in error_msg for pattern in INVALID_COLLECTION_NAME_PATTERNS):
                    logger.warning(f"Failed to get general collection: {str(ve)[:200]}")
            
            # Search each collection
            for collection_type, collection in collections_to_search:
                try:
                    # Build where clause - keep original where clause if provided
                    where_clause = (where or {}).copy()
                    
                    # Note: We don't filter by assistant_id in the where clause because:
                    # - Assistant collection already contains only that assistant's documents (or empty string)
                    # - General collection already contains only documents without assistant_id (empty string)
                    # The collection separation itself handles the filtering
                    
                    # Search
                    results = collection.query(
                        query_embeddings=[query_embedding],
                        n_results=limit,
                        where=where_clause if where_clause else None
                    )
                    
                    # Format results
                    if results['ids'] and len(results['ids'][0]) > 0:
                        for i, chunk_id in enumerate(results['ids'][0]):
                            # Get distance (ChromaDB returns distance, convert to similarity)
                            distance = results['distances'][0][i] if results.get('distances') else 0.0
                            # ChromaDB uses L2 distance, convert to similarity (1 / (1 + distance))
                            similarity = 1.0 / (1.0 + distance) if distance > 0 else 1.0
                            
                            # Filter by minimum similarity
                            if similarity >= min_similarity:
                                all_chunks.append({
                                    "id": chunk_id,
                                    "content": results['documents'][0][i],
                                    "metadata": results['metadatas'][0][i],
                                    "similarity": similarity,
                                    "distance": distance
                                })
                
                except Exception as query_error:
                    # Catch any collection-related errors during query
                    error_msg = str(query_error).lower()
                    if any(pattern in error_msg for pattern in INVALID_COLLECTION_NAME_PATTERNS):
                        logger.warning(f"ChromaDB collection name validation error during query (likely old collection), skipping: {str(query_error)[:200]}")
                    else:
                        logger.warning(f"Error querying {collection_type} collection: {str(query_error)[:200]}")
                    continue
            
            # Sort by similarity (descending) and limit results
            all_chunks.sort(key=lambda x: x['similarity'], reverse=True)
            final_chunks = all_chunks[:limit]
            
            logger.debug(f"Found {len(final_chunks)} chunks for tenant {tenant_id} (assistant_id={assistant_id}, min_similarity={min_similarity})")
            return final_chunks
            
        except Exception as e:
            logger.error(f"ChromaDB search failed: {str(e)}")
            return []
    
    def get_collection_stats(
        self,
        tenant_id: UUID,
        assistant_id: Optional[UUID] = None
    ) -> Dict:
        """
        Get statistics about a collection
        
        Args:
            tenant_id: Tenant UUID
            assistant_id: Optional assistant UUID
        
        Returns:
            Dictionary with collection statistics
        """
        try:
            collection = self.get_collection(tenant_id, assistant_id)
            count = collection.count()
            
            return {
                "tenant_id": str(tenant_id),
                "assistant_id": str(assistant_id) if assistant_id else None,
                "chunk_count": count
            }
        except Exception as e:
            logger.error(f"Failed to get collection stats: {str(e)}")
            return {"chunk_count": 0}


class PineconeVectorStoreService:
    """Service for managing vector embeddings in Pinecone"""
    
    def __init__(self):
        """Initialize Pinecone client"""
        from pinecone import Pinecone, ServerlessSpec
        
        api_key = settings.PINECONE_API_KEY
        if not api_key:
            raise ValueError("PINECONE_API_KEY is required when using Pinecone")
        
        self.pc = Pinecone(api_key=api_key)
        self.index_name = settings.PINECONE_INDEX_NAME
        self.dimension = 768  # gemini-embedding-001 dimension
        
        # Check if host is provided (recommended for production)
        if settings.PINECONE_HOST:
            # Connect directly using host URL
            logger.info(f"Connecting to Pinecone at {settings.PINECONE_HOST}")
            self.index = self.pc.Index(
                name=self.index_name,
                host=settings.PINECONE_HOST
            )
        else:
            # Auto-discover or create index
            existing_indexes = [idx.name for idx in self.pc.list_indexes()]
            if self.index_name not in existing_indexes:
                logger.info(f"Creating Pinecone index: {self.index_name}")
                self.pc.create_index(
                    name=self.index_name,
                    dimension=self.dimension,
                    metric="cosine",
                    spec=ServerlessSpec(
                        cloud="aws",
                        region="us-east-1"
                    )
                )
            self.index = self.pc.Index(self.index_name)
        
        logger.info(f"Connected to Pinecone index: {self.index_name}")
    
    def _get_namespace(self, tenant_id: UUID, assistant_id: Optional[UUID] = None) -> str:
        """Get namespace for tenant/assistant"""
        if assistant_id:
            return f"{tenant_id}_{assistant_id}"
        return str(tenant_id)
    
    def add_document_chunks(
        self,
        tenant_id: UUID,
        document_id: UUID,
        chunks: List[Dict[str, any]],
        assistant_id: Optional[UUID] = None
    ) -> bool:
        """Add document chunks with embeddings to Pinecone"""
        try:
            namespace = self._get_namespace(tenant_id, assistant_id)
            
            vectors = []
            for chunk in chunks:
                chunk_id = f"{document_id}_{chunk['chunk_index']}"
                vectors.append({
                    "id": chunk_id,
                    "values": chunk['embedding'],
                    "metadata": {
                        "document_id": str(document_id),
                        "chunk_index": int(chunk.get('chunk_index', 0)),
                        "tenant_id": str(tenant_id),
                        "assistant_id": str(assistant_id) if assistant_id else "",
                        "content": chunk['content'][:1000]  # Pinecone metadata limit
                    }
                })
            
            # Upsert in batches of 100
            batch_size = 100
            for i in range(0, len(vectors), batch_size):
                batch = vectors[i:i + batch_size]
                self.index.upsert(vectors=batch, namespace=namespace)
            
            logger.info(f"Added {len(vectors)} chunks to Pinecone namespace {namespace}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add chunks to Pinecone: {str(e)}")
            raise
    
    def delete_document_chunks(
        self,
        tenant_id: UUID,
        document_id: UUID,
        assistant_id: Optional[UUID] = None
    ) -> bool:
        """Delete all chunks for a document from Pinecone"""
        try:
            namespace = self._get_namespace(tenant_id, assistant_id)
            
            # Delete by metadata filter
            self.index.delete(
                filter={"document_id": str(document_id)},
                namespace=namespace
            )
            
            logger.info(f"Deleted chunks for document {document_id} from Pinecone")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete chunks from Pinecone: {str(e)}")
            raise
    
    def search(
        self,
        tenant_id: UUID,
        query_embedding: List[float],
        limit: int = 10,
        assistant_id: Optional[UUID] = None,
        min_similarity: float = 0.0,
        where: Optional[Dict] = None
    ) -> List[Dict]:
        """Search for similar chunks using query embedding"""
        all_chunks = []
        
        try:
            # Search assistant-specific namespace if provided
            namespaces_to_search = []
            if assistant_id:
                namespaces_to_search.append(self._get_namespace(tenant_id, assistant_id))
            # Also search general tenant namespace
            namespaces_to_search.append(self._get_namespace(tenant_id, None))
            
            for namespace in namespaces_to_search:
                try:
                    results = self.index.query(
                        vector=query_embedding,
                        top_k=limit,
                        include_metadata=True,
                        namespace=namespace,
                        filter=where
                    )
                    
                    for match in results.get('matches', []):
                        similarity = match.get('score', 0)
                        if similarity >= min_similarity:
                            metadata = match.get('metadata', {})
                            all_chunks.append({
                                "id": match['id'],
                                "content": metadata.get('content', ''),
                                "metadata": metadata,
                                "similarity": similarity,
                                "distance": 1 - similarity  # Convert similarity to distance
                            })
                except Exception as e:
                    logger.warning(f"Error searching namespace {namespace}: {str(e)}")
                    continue
            
            # Sort by similarity and limit
            all_chunks.sort(key=lambda x: x['similarity'], reverse=True)
            final_chunks = all_chunks[:limit]
            
            logger.debug(f"Found {len(final_chunks)} chunks from Pinecone")
            return final_chunks
            
        except Exception as e:
            logger.error(f"Pinecone search failed: {str(e)}")
            return []
    
    def get_collection_stats(
        self,
        tenant_id: UUID,
        assistant_id: Optional[UUID] = None
    ) -> Dict:
        """Get statistics about vectors in namespace"""
        try:
            namespace = self._get_namespace(tenant_id, assistant_id)
            stats = self.index.describe_index_stats()
            
            namespace_stats = stats.get('namespaces', {}).get(namespace, {})
            
            return {
                "tenant_id": str(tenant_id),
                "assistant_id": str(assistant_id) if assistant_id else None,
                "chunk_count": namespace_stats.get('vector_count', 0)
            }
        except Exception as e:
            logger.error(f"Failed to get Pinecone stats: {str(e)}")
            return {"chunk_count": 0}


# Type alias for vector store service
VectorStoreServiceType = VectorStoreService | PineconeVectorStoreService

# Singleton instance
_vector_store_service: Optional[VectorStoreServiceType] = None


def get_vector_store_service() -> VectorStoreServiceType:
    """Get singleton VectorStoreService instance based on config"""
    global _vector_store_service
    if _vector_store_service is None:
        provider = settings.VECTOR_DB_PROVIDER.lower()
        
        if provider == "pinecone":
            logger.info("Using Pinecone vector store")
            _vector_store_service = PineconeVectorStoreService()
        else:
            logger.info("Using ChromaDB vector store")
            _vector_store_service = VectorStoreService()
    
    return _vector_store_service
