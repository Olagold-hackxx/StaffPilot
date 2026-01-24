"""
LLM Service Factory - creates the appropriate LLM service based on provider
"""
from typing import Optional
from app.services.llm.base import BaseLLMService, LLMProvider
from app.services.llm.gemini import GeminiService
from app.services.llm.openai import OpenAIService
from app.services.llm.anthropic import AnthropicService
from app.config import settings
from app.utils.logger import logger


def create_llm_service(
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model_config: Optional[dict] = None
) -> BaseLLMService:
    """
    Factory function to create the appropriate LLM service
    
    Args:
        provider: Provider name (gemini, openai, anthropic). If None, uses default from config
        api_key: API key for the provider. If None, uses default from config
        model_config: Model configuration dict. If None, uses defaults
        
    Returns:
        BaseLLMService instance
        
    Example:
        # Use default provider from config
        llm = create_llm_service()
        
        # Use specific provider
        llm = create_llm_service(provider="openai", api_key="sk-...")
        
        # Custom model config
        llm = create_llm_service(
            provider="gemini",
            model_config={
                "content_model": "gemini-1.5-pro",
                "embedding_model": "text-embedding-004"
            }
        )
    """
    
    # Determine provider
    if not provider:
        # Get default from config or environment
        provider = getattr(settings, 'DEFAULT_LLM_PROVIDER', 'gemini').lower()
    
    provider_enum = LLMProvider(provider)
    
    # Get API key
    if not api_key:
        if provider_enum == LLMProvider.GEMINI:
            api_key = settings.GOOGLE_API_KEY
        elif provider_enum == LLMProvider.OPENAI:
            api_key = settings.OPENAI_API_KEY
        elif provider_enum == LLMProvider.ANTHROPIC:
            api_key = settings.ANTHROPIC_API_KEY
    
    if not api_key:
        raise ValueError(f"API key not provided for provider: {provider}")
    
    # Get model config
    if not model_config:
        if provider_enum == LLMProvider.GEMINI:
            model_config = {
                "content_model": getattr(settings, 'GOOGLE_MODEL_CONTENT', 'gemini-1.5-pro'),
                "image_model": getattr(settings, 'GOOGLE_MODEL_IMAGE', 'gemini-3-pro-image-preview'),
                "video_model": getattr(settings, 'GOOGLE_MODEL_VIDEO', 'veo-3.1-generate-preview'),
                "embedding_model": getattr(settings, 'GOOGLE_EMBEDDING_MODEL', 'text-embedding-004')
            }
        elif provider_enum == LLMProvider.OPENAI:
            model_config = {
                "content_model": getattr(settings, 'OPENAI_MODEL_CONTENT', 'gpt-4o'),
                "image_model": "dall-e-3",
                "embedding_model": getattr(settings, 'OPENAI_EMBEDDING_MODEL', 'text-embedding-3-small')
            }
        elif provider_enum == LLMProvider.ANTHROPIC:
            model_config = {
                "content_model": getattr(settings, 'ANTHROPIC_MODEL_CONTENT', 'claude-3-5-sonnet-20241022'),
                "embedding_model": None  # Not supported
            }
    
    # Create service instance
    try:
        if provider_enum == LLMProvider.GEMINI:
            return GeminiService(api_key, model_config)
        elif provider_enum == LLMProvider.OPENAI:
            return OpenAIService(api_key, model_config)
        elif provider_enum == LLMProvider.ANTHROPIC:
            return AnthropicService(api_key, model_config)
        else:
            raise ValueError(f"Unsupported provider: {provider}")
    except Exception as e:
        logger.error(f"Failed to create LLM service for provider {provider}: {str(e)}")
        raise


def get_llm_service_for_assistant(
    assistant_config: dict
) -> BaseLLMService:
    """
    Get LLM service based on assistant configuration
    
    Args:
        assistant_config: Assistant config dict with keys:
            - llm_provider: Provider name
            - llm_model: Model name
            - api_key: Optional API key override
            
    Returns:
        BaseLLMService instance
    """
    provider = assistant_config.get("llm_provider", "gemini")
    api_key = assistant_config.get("api_key")
    model_name = assistant_config.get("llm_model")
    
    model_config = {}
    if model_name:
        if provider == "gemini":
            model_config["content_model"] = model_name
        elif provider == "openai":
            model_config["content_model"] = model_name
        elif provider == "anthropic":
            model_config["content_model"] = model_name
    
    return create_llm_service(provider=provider, api_key=api_key, model_config=model_config)

