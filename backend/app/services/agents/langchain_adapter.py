"""
LangChain adapter - bridges our provider-agnostic LLM service with LangChain
"""
from typing import Optional, List, Dict, Any, AsyncGenerator
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.callbacks import CallbackManagerForLLMRun, AsyncCallbackManagerForLLMRun
from langchain_core.outputs import ChatGeneration, ChatResult, LLMResult
from app.services.llm import create_llm_service, BaseLLMService
from app.utils.logger import logger


class LangChainLLMAdapter(BaseChatModel):
    """
    Adapter that wraps our provider-agnostic LLM service to work with LangChain
    """
    
    def __init__(
        self,
        llm_service: Optional[BaseLLMService] = None,
        provider: Optional[str] = None,
        temperature: float = 0.7,
        **kwargs
    ):
        super().__init__(**kwargs)
        # Use object.__setattr__ to bypass Pydantic's field validation
        # BaseChatModel is a Pydantic model and doesn't allow arbitrary attributes
        if llm_service:
            object.__setattr__(self, 'llm_service', llm_service)
        else:
            object.__setattr__(self, 'llm_service', create_llm_service(provider=provider))
        object.__setattr__(self, 'temperature', temperature)
    
    @property
    def _llm_type(self) -> str:
        """Return type of LLM"""
        return "staffpilot_llm_adapter"
    
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Synchronous generation - not used in async context"""
        raise NotImplementedError("Use async generation instead")
    
    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Async generation using our LLM service"""
        # Convert LangChain messages to prompt
        system_instruction = None
        user_prompt = ""
        
        for message in messages:
            if isinstance(message, SystemMessage):
                system_instruction = message.content
            elif isinstance(message, HumanMessage):
                user_prompt += message.content + "\n"
            elif isinstance(message, AIMessage):
                # Include AI messages in context
                user_prompt += f"Assistant: {message.content}\n"
        
        # Generate content
        # Filter out unsupported parameters like automatic_function_calling
        filtered_kwargs = {k: v for k, v in kwargs.items() 
                          if k not in ['automatic_function_calling', 'functions', 'function_call']}
        
        try:
            content = await self.llm_service.generate_content(
                prompt=user_prompt.strip(),
                system_instruction=system_instruction,
                temperature=self.temperature,
                max_tokens=filtered_kwargs.get("max_tokens", 2048),
                **{k: v for k, v in filtered_kwargs.items() if k != "max_tokens"}
            )
            
            # Create LangChain response
            message = AIMessage(content=content)
            generation = ChatGeneration(message=message)
            
            return ChatResult(generations=[generation])
            
        except Exception as e:
            logger.error(f"LangChain adapter generation failed: {str(e)}")
            raise
    
    async def astream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[BaseMessage, None]:
        """Stream generation"""
        # Convert messages
        system_instruction = None
        user_prompt = ""
        
        for message in messages:
            if isinstance(message, SystemMessage):
                system_instruction = message.content
            elif isinstance(message, HumanMessage):
                user_prompt += message.content + "\n"
            elif isinstance(message, AIMessage):
                user_prompt += f"Assistant: {message.content}\n"
        
        # Stream content
        async for chunk in self.llm_service.stream_content(
            prompt=user_prompt.strip(),
            system_instruction=system_instruction,
            temperature=self.temperature
        ):
            yield AIMessage(content=chunk)

