# LLM Service - Provider-Agnostic Architecture

This module provides a provider-agnostic interface for LLM services, allowing you to easily switch between Gemini, OpenAI, and Anthropic.

## Quick Start

### Using the Default Provider (from config)

```python
from app.services.llm import create_llm_service

# Uses DEFAULT_LLM_PROVIDER from config (default: "gemini")
llm = create_llm_service()

# Generate content
content = await llm.generate_content(
    prompt="Write a blog post about AI",
    system_instruction="You are a professional content writer",
    temperature=0.7
)
```

### Using a Specific Provider

```python
from app.services.llm import create_llm_service

# Use OpenAI
llm = create_llm_service(provider="openai")

# Use Anthropic
llm = create_llm_service(provider="anthropic")

# Use Gemini with custom API key
llm = create_llm_service(
    provider="gemini",
    api_key="your-api-key-here"
)
```

### Custom Model Configuration

```python
from app.services.llm import create_llm_service

# Custom Gemini config
llm = create_llm_service(
    provider="gemini",
    model_config={
        "content_model": "gemini-1.5-pro",
        "image_model": "imagen-3",
        "embedding_model": "gemini-embedding-001"
    }
)

# Custom OpenAI config
llm = create_llm_service(
    provider="openai",
    model_config={
        "content_model": "gpt-4-turbo",
        "embedding_model": "text-embedding-3-large"
    }
)
```

### For Assistant Configuration

```python
from app.services.llm import get_llm_service_for_assistant

# Get LLM service based on assistant config
assistant_config = {
    "llm_provider": "openai",
    "llm_model": "gpt-4o",
    "api_key": "sk-..."  # Optional override
}

llm = get_llm_service_for_assistant(assistant_config)
```

## Available Methods

All providers implement the same interface:

### Content Generation

```python
# Generate text
content = await llm.generate_content(
    prompt="Your prompt here",
    system_instruction="System context",
    temperature=0.7,
    max_tokens=2048
)

# Generate JSON
data = await llm.generate_json(
    prompt="Return user data as JSON",
    system_instruction="Format: {name, email, age}",
    temperature=0.5
)

# Stream content
async for chunk in llm.stream_content(
    prompt="Write a long story",
    temperature=0.8
):
    print(chunk, end="", flush=True)
```

### Image Generation

```python
# Generate images (Gemini & OpenAI support this)
images = await llm.generate_image(
    prompt="A futuristic cityscape",
    aspect_ratio="16:9",
    number_of_images=2
)
```

### Embeddings

```python
# Generate embeddings (Gemini & OpenAI support this)
embeddings = await llm.generate_embeddings(
    texts=["Text 1", "Text 2", "Text 3"],
    task_type="RETRIEVAL_DOCUMENT"
)
```

## Switching Providers

### Method 1: Environment Variable

```bash
# In .env file
DEFAULT_LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

### Method 2: Code-Level

```python
# Change default in config.py
DEFAULT_LLM_PROVIDER: str = "openai"  # or "anthropic"
```

### Method 3: Per-Assistant

```python
# Each assistant can have its own provider
assistant_config = {
    "llm_provider": "anthropic",
    "llm_model": "claude-3-5-sonnet-20241022"
}
```

## Provider-Specific Features

### Gemini

- ✅ Content generation
- ✅ Image generation (Imagen 3)
- ✅ Video generation (experimental)
- ✅ Embeddings (gemini-embedding-001)

### OpenAI

- ✅ Content generation
- ✅ Image generation (DALL-E 3)
- ✅ Embeddings (text-embedding-3)
- ❌ Video generation

### Anthropic

- ✅ Content generation
- ❌ Image generation
- ❌ Video generation
- ❌ Embeddings (not supported)

## Error Handling

```python
from app.services.llm import create_llm_service, LLMProvider

try:
    llm = create_llm_service(provider="openai")
    content = await llm.generate_content("Hello")
except ValueError as e:
    # Provider not found or API key missing
    print(f"Configuration error: {e}")
except Exception as e:
    # Generation failed
    print(f"Generation error: {e}")
```

## Adding a New Provider

1. Create a new file: `app/services/llm/your_provider.py`
2. Inherit from `BaseLLMService`
3. Implement required methods
4. Add to `LLMProvider` enum in `base.py`
5. Add to factory in `factory.py`

Example:

```python
from app.services.llm.base import BaseLLMService

class YourProviderService(BaseLLMService):
    def __init__(self, api_key: str, model_config: Dict):
        super().__init__(api_key, model_config)
        # Initialize your provider client

    async def generate_content(self, prompt: str, ...):
        # Implement content generation
        pass

    # ... implement other required methods
```
