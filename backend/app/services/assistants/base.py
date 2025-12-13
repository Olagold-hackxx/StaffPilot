"""
Base Assistant class - foundation for all StaffPilot assistants
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, AsyncGenerator, Optional
from enum import Enum


class AssistantType(str, Enum):
    """Assistant types"""
    DIGITAL_MARKETER = "digital_marketer"
    EXECUTIVE_ASSISTANT = "executive_assistant"
    CUSTOMER_SUPPORT = "customer_support"


class BaseAssistant(ABC):
    """
    Base class for all StaffPilot assistants.
    Each assistant implements specific capabilities while sharing
    common infrastructure (RAG, LLM providers, memory).
    """
    
    def __init__(
        self,
        tenant_id: str,
        llm_service=None,  # Placeholder for LLM service
        vector_service=None,  # Placeholder for vector service
        redis_client=None  # Placeholder for Redis client
    ):
        self.tenant_id = tenant_id
        self.llm_service = llm_service
        self.vector_service = vector_service
        self.redis_client = redis_client
        self.assistant_type = self.get_type()
    
    @abstractmethod
    def get_type(self) -> AssistantType:
        """Return the assistant type"""
        pass
    
    @abstractmethod
    def get_system_prompt(self, tenant_config: Dict) -> str:
        """Generate system prompt with tenant customizations"""
        pass
    
    @abstractmethod
    async def get_available_tools(self) -> List[Dict]:
        """Return list of tools this assistant can use"""
        pass
    
    async def retrieve_context(
        self, 
        query: str, 
        top_k: int = 5
    ) -> List[Dict]:
        """
        Retrieve relevant context from vector DB
        Placeholder - AI integration not implemented
        """
        # TODO: Implement RAG retrieval
        return []
    
    async def get_session_memory(
        self, 
        session_id: str
    ) -> List[Dict]:
        """
        Get recent conversation history from Redis
        Placeholder - Redis integration not implemented
        """
        # TODO: Implement Redis memory retrieval
        return []
    
    async def stream_response(
        self,
        messages: List[Dict],
        session_id: str,
        tenant_config: Optional[Dict] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """
        Main orchestration method:
        1. Retrieve context (RAG)
        2. Load session memory
        3. Build prompt
        4. Stream LLM response
        5. Execute tools if needed
        
        Placeholder - AI integration not implemented
        """
        # TODO: Implement full streaming response
        # For now, return a placeholder response
        yield "AI integration not yet implemented. This is a placeholder response."

