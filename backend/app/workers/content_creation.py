"""
Content Creation Celery Tasks
"""
from app.workers import celery_app
from app.utils.logger import logger
from uuid import UUID
import asyncio
import random
from typing import Dict, Any, List, Optional


def _retrieve_rag_context_sync(
    tenant_id: str,
    assistant_id: str,
    query: str,
    limit: int = 5
) -> Dict[str, Any]:
    """
    Sync helper function to retrieve RAG context.
    Uses sync session for RAG operations.
    """
    from app.db.session import create_worker_session_factory
    from app.services.rag_service import RAGService
    
    # Create a sync session for RAG operations
    SessionFactory = create_worker_session_factory()
    db = SessionFactory()
    try:
        rag_service = RAGService(db, UUID(tenant_id))
        chunks = rag_service.retrieve_relevant_context(
            query=query,
            limit=limit,
            assistant_id=UUID(assistant_id) if assistant_id else None
        )
        return {
            "success": True,
            "chunks": chunks,
            "count": len(chunks)
        }
    except Exception as e:
        logger.error(f"RAG retrieval error in sync helper: {str(e)}", exc_info=True)
        return {
            "success": False,
            "chunks": [],
            "count": 0,
            "error": str(e)
        }
    finally:
        db.close()


@celery_app.task(name="rag.retrieve_context", bind=True, max_retries=3)
def retrieve_rag_context(
    self,
    tenant_id: str,
    assistant_id: str,
    query: str,
    limit: int = 5
) -> Dict[str, Any]:
    """
    Retrieve relevant context from documents using RAG
    
    Args:
        tenant_id: Tenant UUID string
        assistant_id: Assistant UUID string
        query: User query/question
        limit: Number of relevant chunks to retrieve
    
    Returns:
        Dictionary with context chunks
    """
    try:
        chunks_result = _retrieve_rag_context_sync(tenant_id, assistant_id, query, limit)
        return chunks_result
    
    except Exception as e:
        logger.error(f"RAG retrieval failed: {str(e)}")
        # Retry on failure
        raise self.retry(exc=e, countdown=60)


def _generate_image_prompt(
    platform: str,
    content: str
) -> str:
    """
    Generate image prompt in the format: 
    "Generate a suitable image to post along with below content in [platform] -- [content]"
    
    Args:
        platform: Social media platform name (e.g., "LinkedIn", "Twitter", "Facebook")
        content: The generated social media content
    
    Returns:
        Formatted image prompt string
    """
    # Format: "Generate a suitable image to post along with below content in [platform] -- [content]"
    image_prompt = f"Generate a suitable image to post along with below content in {platform} -- {content}. IMPORTANT: Ensure all text in the image is in English and free of spelling mistakes."
    return image_prompt


def _generate_video_prompt(
    platform: str,
    content: str
) -> str:
    """
    Generate a storytelling, film-like short ad prompt tied to the social content.
    Format:
    "Create a short, cinematic, story-driven ad for [platform], based on this post. 
    Make it intriguing with a hook and a cliffhanger so viewers want to know what happens next. 
    Keep it tightly aligned to the post content. -- [content]"
    
    Args:
        platform: Social media platform name (e.g., "LinkedIn", "Twitter", "Facebook")
        content: The generated social media content
    
    Returns:
        Formatted video prompt string
    """
    video_prompt = (
        "Create a short, cinematic, story-driven ad for "
        f"{platform}. Base it on this post so the visuals and narrative stay aligned. "
        "Open with a strong hook, build intrigue, and end on a cliffhanger that makes viewers want to know what happens next. "
        f"Here is the post to align with: {content}\n\n"
        "IMPORTANT: Ensure all text in the video is in English and free of spelling mistakes."
    )
    return video_prompt


def _fetch_brand_asset_bytes(tenant_id: str, limit: int = 5) -> List[bytes]:
    """
    Fetch brand asset image bytes for a tenant.
    Used to provide reference images for AI generation.
    
    Args:
        tenant_id: Tenant UUID string
        limit: Maximum number of assets to fetch (default 5)
    
    Returns:
        List of image bytes
    """
    from app.db.session import create_worker_session_factory
    from app.models.brand_asset import BrandAsset
    from app.services.storage import get_storage
    from sqlalchemy import select
    import httpx
    
    SessionFactory = create_worker_session_factory()
    db = SessionFactory()
    
    try:
        # Fetch image-type brand assets for this tenant
        result = db.execute(
            select(BrandAsset)
            .where(BrandAsset.tenant_id == UUID(tenant_id))
            .where(BrandAsset.asset_type == "image")
            .order_by(BrandAsset.usage_count.desc())  # Prioritize frequently used assets
            .limit(limit)
        )
        assets = result.scalars().all()
        
        if not assets:
            logger.info(f"No brand assets found for tenant {tenant_id}")
            return []
        
        logger.info(f"Found {len(assets)} brand assets for tenant {tenant_id}")
        
        # Download image bytes from storage
        asset_bytes = []
        for asset in assets:
            try:
                if asset.url:
                    # Download from URL using httpx (sync)
                    with httpx.Client(timeout=30.0) as client:
                        response = client.get(asset.url)
                        if response.status_code == 200:
                            asset_bytes.append(response.content)
                            logger.info(f"Fetched brand asset: {asset.name} ({len(response.content)} bytes)")
                            
                            # Update usage count
                            asset.usage_count = (asset.usage_count or 0) + 1
            except Exception as e:
                logger.warning(f"Failed to fetch brand asset {asset.id}: {e}")
                continue
        
        db.commit()
        return asset_bytes
        
    except Exception as e:
        logger.error(f"Error fetching brand assets: {e}")
        return []
    finally:
        db.close()


async def _generate_image_async(
    prompt: str,
    aspect_ratio: str = "1:1",
    number_of_images: int = 1,
    tenant_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Async helper function to generate images using AI.
    Automatically uses brand assets as reference images if tenant_id is provided.
    
    Args:
        prompt: Text prompt for image generation
        aspect_ratio: Image aspect ratio
        number_of_images: Number of images to generate
        tenant_id: Optional tenant ID to fetch brand assets for references
    
    Returns:
        Dict with success, images, and count
    """
    from app.services.llm.factory import create_llm_service
    
    llm_service = create_llm_service()
    
    # Fetch brand assets for reference images if tenant_id provided
    reference_images = []
    if tenant_id:
        reference_images = _fetch_brand_asset_bytes(tenant_id, limit=5)
        if reference_images:
            logger.info(f"Using {len(reference_images)} brand assets as reference images for generation")
    
    # Generate images with references if available
    # The updated GeminiService.generate_image supports reference_images
    images = await llm_service.generate_image(
        prompt=prompt,
        aspect_ratio=aspect_ratio,
        number_of_images=number_of_images,
        reference_images=reference_images if reference_images else None
    )
    
    return {
        "success": True,
        "images": images if isinstance(images, list) else [images] if images else [],
        "count": len(images) if isinstance(images, list) else (1 if images else 0),
        "used_references": len(reference_images)
    }



async def _upload_media_async(
    tenant_id: str,
    execution_id: str,
    media_type: str,  # "image" or "video"
    media_data: Any,  # bytes, PIL Image, or file-like object
    filename: str
) -> Dict[str, Any]:
    """
    Async helper function to upload generated media to storage.
    Can be called directly from async contexts.
    
    Args:
        tenant_id: Tenant UUID string
        execution_id: Execution UUID string
        media_type: "image" or "video"
        media_data: Media data (bytes from Gemini, PIL Image, etc.)
        filename: Filename for storage
    
    Returns:
        Dictionary with storage URL
    """
    try:
        from app.services.storage import get_storage
        from io import BytesIO
        import uuid as uuid_lib
        
        storage = get_storage()
        
        if media_type == "image":
            # Handle image data - can be bytes, PIL Image, or file-like object
            img_bytes = BytesIO()
            
            if isinstance(media_data, bytes):
                # Already bytes (from Gemini image generation)
                img_bytes.write(media_data)
            elif hasattr(media_data, 'save'):
                # PIL Image object
                media_data.save(img_bytes, format="PNG")
            elif hasattr(media_data, 'read'):
                # File-like object
                img_bytes.write(media_data.read())
            else:
                # Try to convert to bytes
                img_bytes.write(bytes(media_data))
            
            img_bytes.seek(0)
            
            storage_key = f"tenants/{tenant_id}/content/{execution_id}/images/{uuid_lib.uuid4()}.png"
            url = await storage.upload(
                key=storage_key,
                file=img_bytes,
                content_type="image/png"
            )
            logger.info(f"Uploaded image to storage: {storage_key}, URL: {url}")
            return {
                "success": True,
                "url": url,
                "media_type": media_type
            }
        
        elif media_type == "video":
            # Handle video bytes
            video_bytes = BytesIO()
            
            if isinstance(media_data, bytes):
                video_bytes.write(media_data)
            elif hasattr(media_data, 'read'):
                video_bytes.write(media_data.read())
            else:
                video_bytes.write(bytes(media_data))
            
            video_bytes.seek(0)
            
            storage_key = f"tenants/{tenant_id}/content/{execution_id}/videos/{uuid_lib.uuid4()}.mp4"
            url = await storage.upload(
                key=storage_key,
                file=video_bytes,
                content_type="video/mp4"
            )
            logger.info(f"Uploaded video to storage: {storage_key}, URL: {url}")
            return {
                "success": True,
                "url": url,
                "media_type": media_type
            }
        
        else:
            raise ValueError(f"Unsupported media_type: {media_type}")
            
    except Exception as e:
        logger.error(f"Media upload failed: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


async def _generate_video_async(
    prompt: str,
    duration_seconds: Optional[int] = None,
    tenant_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Async helper function to generate video using AI.
    Automatically uses brand assets as reference images if tenant_id is provided.
    Note: Uses sync method internally for better Celery compatibility.
    """
    try:
        from app.services.llm.factory import create_llm_service
        
        llm_service = create_llm_service()
        
        if duration_seconds is None:
            duration_seconds = random.randint(24, 60)

        # Fetch brand assets for reference images if tenant_id provided
        reference_images = []
        if tenant_id:
            reference_images = _fetch_brand_asset_bytes(tenant_id, limit=3)
            if reference_images:
                logger.info(f"Using {len(reference_images)} brand assets as reference images for video generation")
        
        # Use extended video generation with references if available
        if hasattr(llm_service, 'generate_extended_video_sync'):
            video = llm_service.generate_extended_video_sync(
                prompt=prompt,
                target_duration_seconds=duration_seconds,
                reference_images=reference_images if reference_images else None,
                aspect_ratio="16:9"
            )
        # Use sync method with references for better Celery compatibility
        elif reference_images and hasattr(llm_service, 'generate_video_with_references_sync'):
            video = llm_service.generate_video_with_references_sync(
                prompt=prompt,
                reference_images=reference_images,
                aspect_ratio="16:9"
            )
        elif hasattr(llm_service, 'generate_video_sync'):
            video = llm_service.generate_video_sync(
                prompt=prompt,
                duration_seconds=duration_seconds
            )
        else:
            # Fallback to async if sync not available
            video = await llm_service.generate_video(
                prompt=prompt,
                duration_seconds=duration_seconds
            )
        
        return {
            "success": True,
            "video": video,
            "used_references": len(reference_images)
        }
    except Exception as e:
        logger.error(f"Video generation failed: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


def _generate_content_direct(
    tenant_id: str,
    assistant_id: str,
    request: str,
    context: str = "",
    keyword_results: Optional[Dict[str, Any]] = None,
    platform: Optional[str] = None
) -> str:
    """
    Generate content directly using LLM (not through agent).
    Keyword research is done separately and results are appended to the prompt.
    
    Args:
        tenant_id: Tenant UUID string
        assistant_id: Assistant UUID string
        request: User request from frontend
        context: RAG context from documents
        keyword_results: Results from keyword research tool
        platform: Platform name for platform-specific content
    
    Returns:
        Generated content string
    """
    from app.db.session import create_worker_session_factory
    from sqlalchemy import select
    from app.models.tenant import Tenant
    from app.services.llm.factory import create_llm_service
    
    # Create a new session factory for this worker task (sync)
    SessionFactory = create_worker_session_factory()
    db = SessionFactory()
    try:
        # Get tenant config (sync)
        tenant_result = db.execute(
            select(Tenant).where(Tenant.id == UUID(tenant_id))
        )
        tenant = tenant_result.scalar_one_or_none()
        
        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")
        
        # Build system prompt
        brand_voice = tenant.brand_voice or "professional"
        target_audience = tenant.target_audience or ""
        offerings = tenant.offerings or ""
        
        system_prompt = f"""You are a Digital Marketing Assistant. Your job is to create engaging, platform-appropriate social media content.

Brand Guidelines:
- Voice & Tone: {brand_voice}
- Target Audience: {target_audience}
- Products/Services: {offerings}

IMPORTANT: Generate ONE single, final post that is ready to publish immediately. Do NOT provide multiple options, variations, or alternatives. Do NOT include labels like "Option 1", "Option 2", "Headline:", "Body:", "Call to Action:" - just write the complete post content as it should appear when published. Do not explain your process or steps - just return the final, ready-to-post content."""
        
        # Build platform-specific instructions
        platform_instruction = ""
        if platform:
            platform_guidelines = {
                "linkedin": "LinkedIn: Professional tone, 150-300 words, focus on business value, use industry insights, include a call-to-action. Avoid emojis except sparingly.",
                "twitter": "Twitter/X: Concise and engaging, 1-2 sentences or 280 characters max, use relevant hashtags (2-3), conversational tone, can include emojis.",
                "facebook": "Facebook: Conversational and friendly, 100-250 words, encourage engagement with questions, can use emojis, include a clear call-to-action.",
                "instagram": "Instagram: Visual-first thinking, 125-220 words, use emojis, include 5-10 relevant hashtags, focus on storytelling and visual appeal.",
                "tiktok": "TikTok: Short, punchy, and entertaining, 50-150 words, use trending language, include hooks, focus on quick value or entertainment."
            }
            if platform.lower() in platform_guidelines:
                platform_instruction = f"\n\nPlatform Requirements: {platform_guidelines[platform.lower()]}"
        
        # Get website URL from tenant
        website_url = tenant.website_url or ""
        
        # Build user prompt
        user_prompt = request
        
        # Add context if available
        if context:
            user_prompt += f"\n\nRelevant Context:\n{context}"
        
        # Add keyword results if available
        if keyword_results and keyword_results.get("keywords"):
            keywords = keyword_results.get("keywords", [])
            keyword_list = ", ".join([k.get("keyword", "") for k in keywords[:10]])
            user_prompt += f"\n\nRelevant Keywords: {keyword_list}"
            if keyword_results.get("seed_keyword"):
                user_prompt += f"\nPrimary Topic: {keyword_results.get('seed_keyword')}"
        
        # Add website URL instruction
        if website_url:
            user_prompt += f"\n\nIMPORTANT: Include the website URL ({website_url}) in the content where appropriate (e.g., in call-to-action, links, etc.)."
        
        # Add platform instruction
        if platform_instruction:
            user_prompt += platform_instruction
        
        # Get LLM service and generate content (async, handle event loop properly)
        async def _generate():
            llm_service = create_llm_service()
            # Increase max_tokens for LinkedIn (longer posts) and other platforms
            # LinkedIn posts can be 150-300 words, so we need more tokens
            max_tokens = 2000 if platform == "linkedin" else 1500
            result = await llm_service.generate_content(
                prompt=user_prompt,
                system_instruction=system_prompt,
                temperature=0.7,
                max_tokens=max_tokens
            )
            # Ensure we return a string, not a coroutine
            if isinstance(result, str):
                return result
            return str(result) if result else ""
        
        # Handle event loop properly for Celery workers
        try:
            # Try to get existing loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Loop is running - this shouldn't happen in sync context
                # Fall back to creating a new loop in a thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, _generate())
                    content = future.result()
            else:
                content = loop.run_until_complete(_generate())
        except RuntimeError:
            # No event loop exists, create a new one
            content = asyncio.run(_generate())
        
        return content.strip() if content else ""
    finally:
        db.close()  # Sync close


@celery_app.task(name="content.generate", bind=True, max_retries=2)
def generate_content(
    self,
    tenant_id: str,
    assistant_id: str,
    request: str,
    context: str = ""
) -> Dict[str, Any]:
    """
    Generate content using AI agent
    
    Args:
        tenant_id: Tenant UUID string
        assistant_id: Assistant UUID string
        request: User request
        context: RAG context from documents
    
    Returns:
        Dictionary with generated content and metadata
    """
    try:
        # Use asyncio.run() which properly manages the event loop lifecycle
        result = asyncio.run(
            _generate_content_async(tenant_id, assistant_id, request, context)
        )
        return result
    
    except Exception as e:
        logger.error(f"Content generation failed: {str(e)}")
        raise self.retry(exc=e, countdown=120)


@celery_app.task(name="content.generate_image", bind=True, max_retries=2)
def generate_image_task(
    self,
    prompt: str,
    aspect_ratio: str = "1:1",
    number_of_images: int = 1
) -> Dict[str, Any]:
    """
    Generate images using AI
    
    Args:
        prompt: Image generation prompt
        aspect_ratio: Image aspect ratio
        number_of_images: Number of images to generate
    
    Returns:
        Dictionary with image data or URLs
    """
    try:
        async def _generate():
            from app.services.llm.factory import create_llm_service
            
            llm_service = create_llm_service()
            images = await llm_service.generate_image(
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                number_of_images=number_of_images
            )
            return images
        
        # Use asyncio.run() which properly manages the event loop lifecycle
        images = asyncio.run(_generate())
        
        return {
            "success": True,
            "images": images if isinstance(images, list) else [images] if images else [],
            "count": len(images) if isinstance(images, list) else (1 if images else 0)
        }
    
    except Exception as e:
        logger.error(f"Image generation failed: {str(e)}")
        raise self.retry(exc=e, countdown=60)


@celery_app.task(name="content.generate_video", bind=True, max_retries=2)
def generate_video_task(
    self,
    prompt: str,
    duration_seconds: Optional[int] = None
) -> Dict[str, Any]:
    """
    Generate video using AI
    
    Args:
        prompt: Video generation prompt
        duration_seconds: Video duration
    
    Returns:
        Dictionary with video data or URL
    """
    try:
        llm_service = create_llm_service()
        
        if duration_seconds is None:
            duration_seconds = random.randint(24, 60)
        
        # Use sync method for Celery worker compatibility
        if hasattr(llm_service, 'generate_video_sync'):
            video = llm_service.generate_video_sync(
                prompt=prompt,
                duration_seconds=duration_seconds
            )
        else:
            # Fallback to async if sync not available
            async def _generate():
                return await llm_service.generate_video(
                    prompt=prompt,
                    duration_seconds=duration_seconds
                )
            video = asyncio.run(_generate())
        
        return {
            "success": True,
            "video": video
        }
    
    except Exception as e:
        logger.error(f"Video generation failed: {str(e)}")
        raise self.retry(exc=e, countdown=120)


@celery_app.task(name="content.generate_video_with_assets", bind=True, max_retries=1, time_limit=1800)
def generate_video_with_assets_task(
    self,
    tenant_id: str,
    prompt: str,
    target_duration: Optional[int] = None,
    brand_asset_ids: list = None,
    user_id: str = None
) -> Dict[str, Any]:
    """
    Generate video for content using brand assets as reference images.
    Supports video extension to reach target duration (up to 60 seconds).
    
    Args:
        tenant_id: Tenant UUID string
        prompt: Video generation prompt
        target_duration: Target video duration in seconds (8-60)
        brand_asset_ids: Optional list of brand asset UUIDs to use as references
    
    Returns:
        Dict with video URL and generation details
    """
    try:
        if target_duration is None:
            target_duration = random.randint(24, 60)
            
        logger.info(f"=== CONTENT VIDEO GENERATION WITH ASSETS STARTED ===")
        logger.info(f"Tenant: {tenant_id}, Duration: {target_duration}s, Assets: {len(brand_asset_ids or [])}")
        
        from app.db.session import create_worker_session_factory
        from app.models.brand_asset import BrandAsset
        from app.services.llm.factory import create_llm_service
        from app.services.storage import get_storage
        from sqlalchemy import select
        from io import BytesIO
        import uuid as uuid_lib
        import requests
        
        SessionFactory = create_worker_session_factory()
        db = SessionFactory()
        
        try:
            # Fetch brand assets if provided
            reference_images = []
            if brand_asset_ids:
                for asset_id in brand_asset_ids:
                    try:
                        asset_result = db.execute(
                            select(BrandAsset).where(
                                BrandAsset.id == UUID(asset_id),
                                BrandAsset.tenant_id == UUID(tenant_id),
                                BrandAsset.is_active == True,
                                BrandAsset.asset_type == "image"
                            )
                        )
                        asset = asset_result.scalar_one_or_none()
                        
                        if asset and asset.url:
                            logger.info(f"Fetching brand asset {asset_id}: {asset.name}")
                            try:
                                response = requests.get(asset.url, timeout=30)
                                if response.status_code == 200:
                                    reference_images.append(response.content)
                                    logger.info(f"Loaded brand asset: {asset.name} ({len(response.content)} bytes)")
                                    
                                    # Update usage count
                                    asset.usage_count = (asset.usage_count or 0) + 1
                                    from datetime import datetime, timezone
                                    asset.last_used_at = datetime.now(timezone.utc)
                                else:
                                    logger.warning(f"Failed to fetch asset {asset_id}: HTTP {response.status_code}")
                            except Exception as fetch_err:
                                logger.warning(f"Failed to fetch asset {asset_id}: {fetch_err}")
                    except Exception as asset_err:
                        logger.warning(f"Failed to load brand asset {asset_id}: {asset_err}")
            
            logger.info(f"Loaded {len(reference_images)} reference images")
            
            # Generate video
            llm_service = create_llm_service()
            video_url = None
            
            try:
                # Add strict English instruction to prompt
                prompt += ". IMPORTANT: Ensure all text in the video is in English and free of spelling errors."
                
                logger.info(f"Generating {target_duration}s video with {len(reference_images)} references...")
                
                # Use extended video generation with references
                if hasattr(llm_service, 'generate_extended_video_sync'):
                    video_data = llm_service.generate_extended_video_sync(
                        prompt=prompt,
                        target_duration_seconds=target_duration,
                        reference_images=reference_images if reference_images else None,
                        aspect_ratio="16:9"
                    )
                elif reference_images and hasattr(llm_service, 'generate_video_with_references_sync'):
                    video_data = llm_service.generate_video_with_references_sync(
                        prompt=prompt,
                        reference_images=reference_images,
                        aspect_ratio="16:9"
                    )
                else:
                    video_data = llm_service.generate_video_sync(
                        prompt=prompt,
                        duration_seconds=target_duration,
                        aspect_ratio="16:9"
                    )
                
                if video_data:
                    storage = get_storage()
                    video_bytes = BytesIO()
                    if isinstance(video_data, bytes):
                        video_bytes.write(video_data)
                    else:
                        video_bytes.write(bytes(video_data))
                    
                    video_bytes.seek(0)
                    storage_key = f"tenants/{tenant_id}/content/videos/{uuid_lib.uuid4()}.mp4"
                    
                    url = storage.upload_sync(
                        key=storage_key,
                        file=video_bytes,
                        content_type="video/mp4"
                    )
                    video_url = url
                    logger.info(f"Uploaded video to: {url}")
                    
                    # Create BrandAsset record for the generated video
                    from datetime import datetime
                    
                    video_name = f"Generated Video {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                    new_asset = BrandAsset(
                        tenant_id=UUID(tenant_id),
                        name=video_name,
                        description=f"AI Generated video from prompt: {prompt[:50]}...",
                        asset_type="video",
                        source="generated",
                        url=video_url,
                        duration=target_duration,
                        created_by=UUID(user_id) if user_id else None,
                        is_active=True
                    )
                    db.add(new_asset)
                    logger.info(f"Created BrandAsset for generated video: {video_name}")
                    
            except Exception as e:
                logger.error(f"Video generation with assets failed: {e}")
                raise
            
            db.commit()
            
            logger.info(f"=== CONTENT VIDEO GENERATION COMPLETED ===")
            
            return {
                "success": True,
                "video_url": video_url,
                "target_duration": target_duration,
                "reference_count": len(reference_images)
            }
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Content video generation with assets failed: {str(e)}", exc_info=True)
        raise self.retry(exc=e, countdown=120)


@celery_app.task(name="content.upload_media", bind=True, max_retries=3)
def upload_media_to_storage(
    self,
    tenant_id: str,
    execution_id: str,
    media_type: str,  # "image" or "video"
    media_data: Any,  # PIL Image, bytes, or file object
    filename: str
) -> Dict[str, Any]:
    """
    Upload generated media to storage
    
    Args:
        tenant_id: Tenant UUID string
        execution_id: Execution UUID string
        media_type: "image" or "video"
        media_data: Media data (PIL Image, bytes, etc.)
        filename: Filename for storage
    
    Returns:
        Dictionary with storage URL
    """
    try:
        async def _upload():
            from app.services.storage import get_storage
            from io import BytesIO
            import uuid as uuid_lib
            
            storage = get_storage()
            
            if media_type == "image":
                # Handle image data - can be bytes, PIL Image, or file-like object
                img_bytes = BytesIO()
                
                if isinstance(media_data, bytes):
                    # Already bytes (from Gemini image generation)
                    img_bytes.write(media_data)
                elif hasattr(media_data, 'save'):
                    # PIL Image object
                    media_data.save(img_bytes, format="PNG")
                elif hasattr(media_data, 'read'):
                    # File-like object
                    img_bytes.write(media_data.read())
                else:
                    # Try to convert to bytes
                    img_bytes.write(bytes(media_data))
                
                img_bytes.seek(0)
                
                storage_key = f"tenants/{tenant_id}/content/{execution_id}/images/{uuid_lib.uuid4()}.png"
                url = await storage.upload(
                    key=storage_key,
                    file=img_bytes,
                    content_type="image/png"
                )
                logger.info(f"Uploaded image to storage: {storage_key}, URL: {url}")
                return url
            
            elif media_type == "video":
                # Handle video bytes
                if isinstance(media_data, bytes):
                    video_bytes = BytesIO(media_data)
                else:
                    video_bytes = media_data
                
                storage_key = f"tenants/{tenant_id}/content/{execution_id}/videos/{uuid_lib.uuid4()}.mp4"
                url = await storage.upload(
                    key=storage_key,
                    file=video_bytes,
                    content_type="video/mp4"
                )
                return url
        
        # Use asyncio.run() which properly manages the event loop lifecycle
        url = asyncio.run(_upload())
        
        return {
            "success": True,
            "url": url,
            "media_type": media_type
        }
    
    except Exception as e:
        logger.error(f"Media upload failed: {str(e)}")
        raise self.retry(exc=e, countdown=30)


async def _post_to_social_platform_async(
    platform: str,
    content: str,
    access_token: str,
    integration_data: Dict[str, Any],
    media_urls: Optional[List[str]] = None,
    integration=None,
    db_session=None
) -> Dict[str, Any]:
    """
    Async helper function to post content to social platforms.
    Can be called directly from async contexts.
    """
    from app.services.integrations.social import ( 
        FacebookPostingService, InstagramPostingService, 
        LinkedInPostingService, TwitterPostingService, TikTokPostingService 
    )
    import asyncio
    
    logger.info(f"[{platform}] Starting post to {platform}...")
    logger.debug(f"[{platform}] Content length: {len(content)}, Has media: {bool(media_urls)}, Integration data keys: {list(integration_data.keys())}")
    
    # Clean markdown formatting from content before posting
    from app.utils.content_formatter import clean_markdown_for_social
    cleaned_content = clean_markdown_for_social(content, platform=platform)
    logger.debug(f"[{platform}] Cleaned content (removed markdown): {cleaned_content[:200]}...")
    
    try:
        # Posting services are synchronous, so run them in a thread
        if platform == "facebook":
            page_id = integration_data.get("page_id")
            logger.info(f"[{platform}] Required params - page_id: {page_id}, access_token: {'present' if access_token else 'missing'}")
            if not page_id:
                logger.error(f"[{platform}] Missing required parameter: page_id")
                return {"success": False, "error": "Facebook page_id not found"}
            if not access_token:
                logger.error(f"[{platform}] Missing required parameter: access_token")
                return {"success": False, "error": "Facebook access_token not found"}
            
            logger.info(f"[{platform}] Calling FacebookPostingService.post with page_id={page_id}")
            post_result = await asyncio.to_thread(
                FacebookPostingService.post,
                content=cleaned_content,
                access_token=access_token,
                page_id=page_id,
                media_urls=media_urls
            )
            logger.info(f"[{platform}] Facebook post completed: success={post_result.get('success')}")
            return post_result
        
        elif platform == "instagram":
            ig_user_id = integration_data.get("ig_user_id") or integration_data.get("instagram_user_id")
            logger.info(f"[{platform}] Required params - ig_user_id: {ig_user_id}, access_token: {'present' if access_token else 'missing'}")
            if not ig_user_id:
                logger.error(f"[{platform}] Missing required parameter: ig_user_id")
                return {"success": False, "error": "Instagram user_id not found"}
            if not access_token:
                logger.error(f"[{platform}] Missing required parameter: access_token")
                return {"success": False, "error": "Instagram access_token not found"}
            
            logger.info(f"[{platform}] Calling InstagramPostingService.post with ig_user_id={ig_user_id}")
            post_result = await asyncio.to_thread(
                InstagramPostingService.post,
                content=cleaned_content,
                access_token=access_token,
                ig_user_id=ig_user_id,
                media_urls=media_urls
            )
            logger.info(f"[{platform}] Instagram post completed: success={post_result.get('success')}")
            return post_result
        
        elif platform == "linkedin":
            entity_id = integration_data.get("entity_id") or integration_data.get("organization_id")
            is_organization = integration_data.get("is_organization", False)
            logger.info(f"[{platform}] Required params - entity_id: {entity_id}, is_organization: {is_organization}, access_token: {'present' if access_token else 'missing'}")
            if not entity_id:
                logger.error(f"[{platform}] Missing required parameter: entity_id")
                return {"success": False, "error": "LinkedIn entity_id not found"}
            if not access_token:
                logger.error(f"[{platform}] Missing required parameter: access_token")
                return {"success": False, "error": "LinkedIn access_token not found"}
            
            # Clean markdown formatting from content before posting
            from app.utils.content_formatter import clean_markdown_for_social
            cleaned_content = clean_markdown_for_social(content, platform="linkedin")
            logger.info(f"[{platform}] Calling LinkedInPostingService.post with entity_id={entity_id}, is_organization={is_organization}")
            logger.debug(f"[{platform}] Original content length: {len(content)}, Cleaned content length: {len(cleaned_content)}")
            logger.debug(f"[{platform}] Cleaned content preview: {cleaned_content[:100]}..., Media URLs count: {len(media_urls) if media_urls else 0}")
            try:
                post_result = await asyncio.to_thread(
                    LinkedInPostingService.post,
                    content=cleaned_content,
                    access_token=access_token,
                    entity_id=entity_id,
                    is_organization=is_organization,
                    media_urls=media_urls
                )
                logger.info(f"[{platform}] LinkedIn post completed: success={post_result.get('success')}")
                if not post_result.get("success"):
                    error_msg = post_result.get('error', 'Unknown error')
                    logger.error(f"[{platform}] LinkedIn post error: {error_msg}")
                    logger.debug(f"[{platform}] Full error response: {error_msg}")
                return post_result
            except Exception as e:
                logger.error(f"[{platform}] Exception in LinkedInPostingService.post: {str(e)}", exc_info=True)
                return {"success": False, "error": f"LinkedIn posting exception: {str(e)}"}
        
        elif platform == "twitter":
            logger.info(f"[{platform}] Required params - access_token: {'present' if access_token else 'missing'}")
            if not access_token:
                logger.error(f"[{platform}] Missing required parameter: access_token")
                return {"success": False, "error": "Twitter access_token not found"}
            
            # Get Twitter OAuth config for token refresh
            refresh_token = None
            client_id = None
            client_secret = None
            token_expires_at = None
            integration_id = None
            
            if integration:
                refresh_token = integration.refresh_token
                token_expires_at = integration.token_expires_at
                refresh_token_expires_at = integration.refresh_token_expires_at
                integration_id = str(integration.id)
                
                # Log refresh token info for debugging
                if refresh_token:
                    logger.debug(f"[{platform}] Refresh token present (length: {len(refresh_token)}, first 20 chars: {refresh_token[:20]}...)")
                else:
                    logger.warning(f"[{platform}] Refresh token is None or empty in integration {integration_id}")
                
                # Get OAuth config
                try:
                    from app.services.integration_service import IntegrationService
                    integration_service = IntegrationService(db_session) if db_session else None
                    if integration_service:
                        config = await integration_service.get_integration_config("twitter")
                        if config:
                            client_id = config.client_id
                            client_secret = config.client_secret
                except Exception as config_error:
                    logger.warning(f"[{platform}] Failed to get Twitter OAuth config: {str(config_error)}")
            
            logger.info(f"[{platform}] Calling TwitterPostingService.post (with token refresh if needed)")
            # TwitterPostingService.post is now async, so call it directly
            post_result = await TwitterPostingService.post(
                text=cleaned_content,
                access_token=access_token,
                image_urls=media_urls,
                refresh_token=refresh_token,
                client_id=client_id,
                client_secret=client_secret,
                token_expires_at=token_expires_at,
                refresh_token_expires_at=refresh_token_expires_at,
                integration_id=integration_id,
                db_session=db_session
            )
            logger.info(f"[{platform}] Twitter post completed: success={post_result.get('success')}")
            if not post_result.get("success"):
                logger.error(f"[{platform}] Twitter post error: {post_result.get('error')}")
            return post_result
        
        elif platform == "tiktok":
            logger.info(f"[{platform}] Required params - access_token: {'present' if access_token else 'missing'}, has_video: {bool(media_urls and any(url.endswith(('.mp4', '.mov', '.avi')) for url in media_urls))}")
            if not access_token:
                logger.error(f"[{platform}] Missing required parameter: access_token")
                return {"success": False, "error": "TikTok access_token not found"}
            if not media_urls or not any(url.endswith(('.mp4', '.mov', '.avi')) for url in (media_urls or [])):
                logger.error(f"[{platform}] Missing required parameter: video URL")
                return {"success": False, "error": "TikTok requires a video"}
            
            logger.info(f"[{platform}] Calling TikTokPostingService.post")
            post_result = await asyncio.to_thread(
                TikTokPostingService.post,
                content=cleaned_content,
                access_token=access_token,
                media_urls=media_urls or []
            )
            logger.info(f"[{platform}] TikTok post completed: success={post_result.get('success')}")
            return post_result
        
        else:
            logger.error(f"[{platform}] Unsupported platform: {platform}")
            return {"success": False, "error": f"Unsupported platform for posting: {platform}"}
    
    except Exception as e:
        logger.error(f"[{platform}] Exception during posting: {str(e)}", exc_info=True)
        return {"success": False, "error": f"Posting failed: {str(e)}"}


@celery_app.task(name="content.post_to_platform", bind=True, max_retries=3)
def post_to_social_platform(
    self,
    platform: str,
    content: str,
    access_token: str,
    integration_data: Dict[str, Any],
    media_urls: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Post content to a social media platform
    
    Args:
        platform: Platform name (facebook, instagram, etc.)
        content: Post content
        access_token: Platform access token
        integration_data: Platform-specific integration data
        media_urls: Optional media URLs
    
    Returns:
        Dictionary with post result
    """
    try:
        from app.services.integrations.social import (
            FacebookPostingService,
            InstagramPostingService,
            LinkedInPostingService,
            TwitterPostingService,
            TikTokPostingService
        )
        
        if platform == "facebook":
            page_id = integration_data.get("page_id")
            if not page_id:
                return {"success": False, "error": "Facebook page_id not found"}
            return FacebookPostingService.post(
                content=content,
                access_token=access_token,
                page_id=page_id,
                media_urls=media_urls
            )
        
        elif platform == "instagram":
            ig_user_id = integration_data.get("ig_user_id") or integration_data.get("instagram_user_id")
            if not ig_user_id:
                return {"success": False, "error": "Instagram user_id not found"}
            return InstagramPostingService.post(
                content=content,
                access_token=access_token,
                ig_user_id=ig_user_id,
                media_urls=media_urls
            )
        
        elif platform == "linkedin":
            entity_id = integration_data.get("entity_id") or integration_data.get("organization_id")
            is_organization = integration_data.get("is_organization", False)
            if not entity_id:
                return {"success": False, "error": "LinkedIn entity_id not found"}
            return LinkedInPostingService.post(
                content=content,
                access_token=access_token,
                entity_id=entity_id,
                is_organization=is_organization,
                media_urls=media_urls
            )
        
        elif platform == "twitter":
            # TwitterPostingService.post is async, so use asyncio.run()
            # Pass refresh token parameters from integration_data for token refresh on 403
            import asyncio
            return asyncio.run(TwitterPostingService.post(
                text=content,
                access_token=access_token,
                image_urls=media_urls,
                refresh_token=integration_data.get("refresh_token"),
                client_id=integration_data.get("client_id"),
                client_secret=integration_data.get("client_secret"),
                integration_id=integration_data.get("integration_id")
            ))
        
        elif platform == "tiktok":
            if not media_urls or not any(url.endswith(('.mp4', '.mov', '.avi')) for url in (media_urls or [])):
                return {"success": False, "error": "TikTok requires a video"}
            return TikTokPostingService.post(
                content=content,
                access_token=access_token,
                media_urls=media_urls or []
            )
        
        else:
            return {"success": False, "error": f"Unsupported platform: {platform}"}
    
    except Exception as e:
        logger.error(f"Posting to {platform} failed: {str(e)}")
        raise self.retry(exc=e, countdown=60)


@celery_app.task(name="content.create_execution", bind=True, max_retries=1)
def execute_content_creation(
    self,
    execution_id: str,
    tenant_id: str,
    assistant_id: str,
    request_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Main Celery task for content creation execution
    
    This orchestrates the entire workflow:
    1. RAG retrieval
    2. Content generation
    3. Image/video generation (if requested)
    4. Media upload
    5. Social media posting
    6. Database updates
    
    Args:
        execution_id: Execution UUID string
        tenant_id: Tenant UUID string
        assistant_id: Assistant UUID string
        request_data: Request data with user request, platforms, etc.
    
    Returns:
        Execution result
    """
    try:
        # Use sync database operations - no asyncio.run() needed for DB
        from app.db.session import create_worker_session_factory
        from app.models.content import ContentItem
        from app.models.integration import SocialIntegration
        from app.models.agent_execution import AgentExecution
        from sqlalchemy import select
        from datetime import datetime, timezone
        
        # Create a new session factory for this worker task (sync)
        SessionFactory = create_worker_session_factory()
        db = SessionFactory()
        try:
            # Update status to running (sync)
            result = db.execute(
                select(AgentExecution).where(AgentExecution.id == UUID(execution_id))
            )
            execution = result.scalar_one_or_none()
            if execution:
                execution.status = "running"
                if not execution.started_at:
                    execution.started_at = datetime.now(timezone.utc)
                db.commit()
                db.refresh(execution)
                
                user_request = request_data.get("request", "")
                platforms = request_data.get("platforms", [])
                include_images = request_data.get("include_images", False)
                include_video = request_data.get("include_video", False)
                
                # Task tracking for logging
                tasks = []
                
                # Step 1: RAG retrieval (call async helper directly)
                logger.info("=" * 80)
                logger.info("CONTENT CREATION EXECUTION STARTED")
                logger.info(f"Execution ID: {execution_id}")
                logger.info(f"Tenant ID: {tenant_id}")
                logger.info(f"Assistant ID: {assistant_id}")
                logger.info(f"Platforms: {platforms}")
                logger.info(f"Include Images: {include_images}, Include Video: {include_video}")
                logger.info("=" * 80)
                
                logger.info("[TASK 1/6] Starting RAG retrieval...")
                # RAG retrieval uses sync sessions
                rag_result = _retrieve_rag_context_sync(
                    tenant_id=tenant_id,
                    assistant_id=assistant_id,
                    query=user_request,
                    limit=10  # Increased from 5 to 10 for better retrieval
                )
                
                context = ""
                context_text_for_keywords = ""  # Raw text from chunks for keyword extraction
                if rag_result.get("success") and rag_result.get("chunks"):
                    chunks = rag_result.get("chunks", [])
                    chunks_count = len(chunks)
                    context_parts = ["RELEVANT CONTEXT FROM KNOWLEDGE BASE:"]
                    # Extract raw text from chunks for keyword research
                    chunk_texts = []
                    for i, chunk in enumerate(chunks, 1):
                        chunk_content = chunk.get('content', '')
                        chunk_texts.append(chunk_content)
                        context_parts.append(
                            f"\n[{i}] Source: {chunk.get('source', 'Unknown')}\n"
                            f"Content: {chunk_content[:500]}..."
                        )
                    context = "\n".join(context_parts)
                    # Combine chunk texts for keyword extraction (use first 500 chars from each chunk)
                    context_text_for_keywords = " ".join([text[:500] for text in chunk_texts])
                    tasks.append({"task": "RAG Retrieval", "status": "PASSED", "details": f"Retrieved {chunks_count} relevant chunks"})
                    logger.info(f"[TASK 1/6] ✓ PASSED - Retrieved {chunks_count} relevant chunks from knowledge base")
                else:
                    chunks_count = rag_result.get("count", 0)
                    if chunks_count > 0:
                        tasks.append({"task": "RAG Retrieval", "status": "PASSED", "details": f"Retrieved {chunks_count} relevant chunks"})
                        logger.info(f"[TASK 1/6] ✓ PASSED - Retrieved {chunks_count} relevant chunks from knowledge base")
                    else:
                        tasks.append({"task": "RAG Retrieval", "status": "FAILED", "details": "No chunks retrieved"})
                        logger.warning("[TASK 1/6] ✗ FAILED - No chunks retrieved from knowledge base")
                
                # Step 2: Keyword Research
                logger.info("[TASK 2/6] Starting keyword research...")
                keyword_results = None
                try:
                    from app.services.integrations.seo import SerpAPIService
                    serp_service = SerpAPIService()
                    # Use context from RAG retrieval for keyword research instead of user prompt
                    # This ensures keywords are relevant to the actual content context
                    if context_text_for_keywords:
                        # Extract key terms from context text (first 200 chars to get main topics)
                        # Remove common words and extract meaningful phrases
                        keyword_query = context_text_for_keywords[:200].strip()
                        # Clean up - remove extra whitespace and newlines
                        keyword_query = " ".join(keyword_query.split())
                        keyword_query = keyword_query[:100]  # Limit to 100 chars
                    else:
                        # Fallback to user request if no context available
                        keyword_query = user_request[:100]
                    
                    # Keyword research is async, so use asyncio.run()
                    keyword_results = asyncio.run(
                        serp_service.keyword_research(
                            query=keyword_query,
                            location="United States",
                            limit=10
                        )
                    )
                    keywords = keyword_results.get('keywords', [])
                    keywords_count = len(keywords)
                    if keywords:
                        # Log all generated keywords
                        keyword_list = []
                        for k in keywords:
                            if isinstance(k, dict):
                                keyword_str = k.get('keyword', str(k))
                                if 'search_volume' in k:
                                    keyword_str += f" (vol: {k.get('search_volume', 'N/A')})"
                                keyword_list.append(keyword_str)
                            else:
                                keyword_list.append(str(k))
                        logger.info(f"[TASK 2/6] Generated keywords ({keywords_count}): {', '.join(keyword_list)}")
                    tasks.append({"task": "Keyword Research", "status": "PASSED", "details": f"Found {keywords_count} keywords"})
                    logger.info(f"[TASK 2/6] ✓ PASSED - Found {keywords_count} keywords")
                except Exception as e:
                    tasks.append({"task": "Keyword Research", "status": "FAILED", "details": str(e)})
                    logger.warning(f"[TASK 2/6] ✗ FAILED - Keyword research failed: {str(e)}, continuing without keywords")
                
                # Step 3: Generate content using LLM (with keywords appended)
                logger.info("[TASK 3/6] Starting content generation...")
                platform_contents = {}
                content_generation_passed = 0
                content_generation_failed = 0
                
                if platforms:
                    # Generate platform-specific content for each platform
                    for platform in platforms:
                        logger.info(f"[TASK 3/6] Generating content for {platform}...")
                        try:
                            # Content generation (sync function that handles async LLM internally)
                            content_result = _generate_content_direct(
                                tenant_id=tenant_id,
                                assistant_id=assistant_id,
                                request=user_request,
                                context=context,
                                keyword_results=keyword_results,
                                platform=platform
                            )
                            if content_result and content_result.strip():
                                platform_contents[platform] = content_result
                                content_generation_passed += 1
                                logger.info(f"[TASK 3/6] ✓ PASSED - Content generated for {platform} ({len(content_result)} chars)")
                            else:
                                content_generation_failed += 1
                                logger.warning(f"[TASK 3/6] ✗ FAILED - Empty content for {platform}")
                        except Exception as e:
                            content_generation_failed += 1
                            logger.error(f"[TASK 3/6] ✗ FAILED - Content generation error for {platform}: {str(e)}")
                else:
                    # No platforms specified, generate generic content
                    try:
                        # Content generation (sync function that handles async LLM internally)
                        content_result = _generate_content_direct(
                            tenant_id=tenant_id,
                            assistant_id=assistant_id,
                            request=user_request,
                            context=context,
                            keyword_results=keyword_results,
                            platform=None
                        )
                        if content_result and content_result.strip():
                            # Use same content for all platforms if not specified
                            for platform in platforms:
                                platform_contents[platform] = content_result
                            content_generation_passed = len(platforms) if platforms else 1
                            logger.info(f"[TASK 3/6] ✓ PASSED - Generic content generated ({len(content_result)} chars)")
                        else:
                            content_generation_failed = 1
                            logger.warning("[TASK 3/6] ✗ FAILED - Empty generic content")
                    except Exception as e:
                        content_generation_failed = 1
                        logger.error(f"[TASK 3/6] ✗ FAILED - Generic content generation error: {str(e)}")
                
                # Log content generation summary
                if content_generation_passed > 0:
                    tasks.append({"task": "Content Generation", "status": "PASSED", "details": f"{content_generation_passed} platform(s) succeeded"})
                if content_generation_failed > 0:
                    tasks.append({"task": "Content Generation", "status": "PARTIAL", "details": f"{content_generation_failed} platform(s) failed"})
                
                # Check if we have content for at least one platform
                if not platform_contents or not any(platform_contents.values()):
                    tasks.append({"task": "Content Generation", "status": "FAILED", "details": "No content generated for any platform"})
                    # Update execution status (sync)
                    result = db.execute(
                        select(AgentExecution).where(AgentExecution.id == UUID(execution_id))
                    )
                    execution = result.scalar_one_or_none()
                    if execution:
                        execution.status = "failed"
                        execution.error_message = "Content generation returned empty result for all platforms"
                        execution.completed_at = datetime.now(timezone.utc)
                        if execution.started_at:
                            delta = execution.completed_at - execution.started_at
                            execution.execution_time_ms = int(delta.total_seconds() * 1000)
                        db.commit()
                    logger.error("=" * 80)
                    logger.error("CONTENT CREATION EXECUTION FAILED")
                    logger.error("=" * 80)
                    return {
                        "success": False,
                        "error": "Content generation returned empty result for all platforms"
                    }
                
                # Step 4: Generate images/videos if requested (using generated content)
                logger.info("[TASK 4/6] Starting media generation...")
                image_urls = []
                video_urls = []
                
                if include_images:
                    logger.info("[TASK 4/6] Generating images...")
                    try:
                        # Get the first platform and its content for image generation
                        first_platform = platforms[0] if platforms else "social media"
                        first_platform_content = None
                        if platform_contents:
                            # Get content for the first platform
                            first_platform_content = platform_contents.get(first_platform, "")
                            if not first_platform_content:
                                # Fallback to first available content
                                first_platform_content = next(iter(platform_contents.values()), "")
                        
                        # Format platform name nicely (capitalize first letter)
                        platform_name = first_platform.capitalize() if first_platform else "Social media"
                        
                        # Generate image prompt in the format: 
                        # "Generate a suitable image to post along with below content in [platform] -- [content]"
                        if first_platform_content:
                            image_prompt = _generate_image_prompt(
                                platform=platform_name,
                                content=first_platform_content
                            )
                        else:
                            # Fallback if no content generated yet
                            image_prompt = f"Generate a suitable image to post along with below content in {platform_name} -- {user_request}"
                        
                        logger.info(f"[TASK 4/6] Generated image prompt: {image_prompt[:200]}...")
                        
                        # Image generation is async (uses LLM), so use asyncio.run()
                        # Pass tenant_id to auto-use brand assets as reference images
                        image_result = asyncio.run(
                            _generate_image_async(
                                prompt=image_prompt,
                                aspect_ratio="1:1",
                                number_of_images=1,
                                tenant_id=tenant_id  # Auto-fetch and use brand assets
                            )
                        )
                        
                        if image_result.get("success"):
                            images = image_result.get("images", [])
                            uploaded_count = 0
                            # Upload each image
                            for img in images:
                                # Media upload is async, so use asyncio.run()
                                upload_result = asyncio.run(
                                    _upload_media_async(
                                        tenant_id=tenant_id,
                                        execution_id=execution_id,
                                        media_type="image",
                                        media_data=img,
                                        filename="generated_image.png"
                                    )
                                )
                                
                                if upload_result.get("success"):
                                    image_urls.append(upload_result["url"])
                                    uploaded_count += 1
                            
                            if uploaded_count > 0:
                                tasks.append({"task": "Image Generation", "status": "PASSED", "details": f"{uploaded_count} image(s) generated and uploaded"})
                                logger.info(f"[TASK 4/6] ✓ PASSED - {uploaded_count} image(s) generated and uploaded")
                            else:
                                tasks.append({"task": "Image Generation", "status": "FAILED", "details": "Images generated but upload failed"})
                                logger.warning("[TASK 4/6] ✗ FAILED - Images generated but upload failed")
                        else:
                            tasks.append({"task": "Image Generation", "status": "FAILED", "details": image_result.get("error", "Unknown error")})
                            logger.warning(f"[TASK 4/6] ✗ FAILED - Image generation failed: {image_result.get('error', 'Unknown error')}")
                    except NotImplementedError as e:
                        # Image generation not available (e.g., Gemini doesn't support it)
                        tasks.append({"task": "Image Generation", "status": "SKIPPED", "details": "Not available for current LLM provider"})
                        logger.warning(f"[TASK 4/6] ⊘ SKIPPED - Image generation not available: {str(e)}")
                    except Exception as e:
                        tasks.append({"task": "Image Generation", "status": "FAILED", "details": str(e)})
                        logger.error(f"[TASK 4/6] ✗ FAILED - Image generation/upload error: {str(e)}")
                else:
                    tasks.append({"task": "Image Generation", "status": "SKIPPED", "details": "Not requested"})
                    logger.info("[TASK 4/6] ⊘ SKIPPED - Image generation not requested")
                
                if include_video:
                    logger.info("[TASK 4/6] Generating video...")
                    try:
                        # Generate video prompt in the format: 
                        # "Generate a suitable video to post along with below content in [platform] -- [content]"
                        first_platform = platforms[0] if platforms else "social media"
                        first_platform_content = None
                        if platform_contents:
                            first_platform_content = next(iter(platform_contents.values()), "")
                        
                        if first_platform_content:
                            video_prompt = _generate_video_prompt(
                                platform=first_platform,
                                content=first_platform_content
                            )
                        else:
                            # Fallback if no content generated yet
                            video_prompt = f"Generate a suitable video to post along with below content in {first_platform} -- {user_request}"
                        
                        logger.info(f"[TASK 4/6] Generated video prompt: {video_prompt[:200]}...")
                        
                        # Video generation with auto brand asset references
                        video_result = asyncio.run(
                            _generate_video_async(
                                prompt=video_prompt,
                                duration_seconds=random.randint(24, 60),
                                tenant_id=tenant_id  # Auto-fetch and use brand assets
                            )
                        )
                        
                        if video_result.get("success"):
                            video = video_result.get("video")
                            # Upload video
                            # Media upload is async, so use asyncio.run()
                            upload_result = asyncio.run(
                                _upload_media_async(
                                    tenant_id=tenant_id,
                                    execution_id=execution_id,
                                    media_type="video",
                                    media_data=video,
                                    filename="generated_video.mp4"
                                )
                            )
                            
                            if upload_result.get("success"):
                                video_urls.append(upload_result["url"])
                                tasks.append({"task": "Video Generation", "status": "PASSED", "details": "Video generated and uploaded"})
                                logger.info("[TASK 4/6] ✓ PASSED - Video generated and uploaded")
                            else:
                                tasks.append({"task": "Video Generation", "status": "FAILED", "details": "Video generated but upload failed"})
                                logger.warning("[TASK 4/6] ✗ FAILED - Video generated but upload failed")
                        else:
                            tasks.append({"task": "Video Generation", "status": "FAILED", "details": video_result.get("error", "Unknown error")})
                            logger.warning(f"[TASK 4/6] ✗ FAILED - Video generation failed: {video_result.get('error', 'Unknown error')}")
                    except Exception as e:
                        tasks.append({"task": "Video Generation", "status": "FAILED", "details": str(e)})
                        logger.error(f"[TASK 4/6] ✗ FAILED - Video generation/upload error: {str(e)}")
                else:
                    tasks.append({"task": "Video Generation", "status": "SKIPPED", "details": "Not requested"})
                    logger.info("[TASK 4/6] ⊘ SKIPPED - Video generation not requested")
                
                # Step 5: Post to platforms
                logger.info("[TASK 5/6] Starting platform posting...")
                created_content_items = []
                all_media_urls = image_urls + video_urls
                posting_passed = 0
                posting_failed = 0
                posting_skipped = 0
                
                for platform in platforms:
                    try:
                        # Get platform-specific content
                        generated_content = platform_contents.get(platform, "")
                        if not generated_content:
                            posting_skipped += 1
                            logger.warning(f"[TASK 5/6] [{platform}] ⊘ SKIPPED - No content generated for {platform}")
                            created_content_items.append({
                                "platform": platform,
                                "status": "skipped",
                                "error": "No content generated for this platform"
                            })
                            continue
                        
                        # Get integration - allow integrations without assistant_id or matching assistant_id (sync)
                        integration_result = db.execute(
                            select(SocialIntegration).where(
                                SocialIntegration.tenant_id == UUID(tenant_id),
                                (SocialIntegration.assistant_id == UUID(assistant_id)) | (SocialIntegration.assistant_id.is_(None)),
                                SocialIntegration.platform == platform,
                                SocialIntegration.is_active == True
                            )
                        )
                        integration = integration_result.scalar_one_or_none()
                        
                        if not integration:
                            posting_skipped += 1
                            logger.warning(f"[TASK 5/6] [{platform}] ⊘ SKIPPED - No active integration found for {platform}")
                            created_content_items.append({
                                "platform": platform,
                                "status": "skipped",
                                "error": "No active integration found"
                            })
                            continue
                        
                        # Build integration data from model fields with comprehensive logging
                        logger.info(f"[{platform}] Building integration data for posting...")
                        integration_data = {}
                        
                        # Start with meta_data if available
                        if integration.meta_data:
                            integration_data.update(integration.meta_data)
                            logger.debug(f"[{platform}] Loaded meta_data: {list(integration_data.keys())}")
                        
                        # Platform-specific parameter extraction
                        if platform == "facebook":
                            logger.info(f"[{platform}] Extracting Facebook parameters...")
                            if not integration.pages:
                                logger.error(f"[{platform}] Missing pages data in integration")
                                created_content_items.append({
                                    "platform": platform,
                                    "status": "failed",
                                    "error": "Facebook pages not found in integration"
                                })
                                continue
                            
                            # Get default page or fall back to first page (sync)
                            selected_page = None
                            if integration.pages:
                                # Find default page (one with is_default=True)
                                if isinstance(integration.pages, list):
                                    for page in integration.pages:
                                        if isinstance(page, dict) and page.get("is_default"):
                                            selected_page = page
                                            break
                                    # If no default, use first page
                                    if not selected_page and integration.pages:
                                        selected_page = integration.pages[0]
                                elif isinstance(integration.pages, dict):
                                    # Single page
                                    selected_page = integration.pages
                            if not selected_page:
                                # Fall back to first page if no default is set
                                selected_page = integration.pages[0] if isinstance(integration.pages, list) and integration.pages else None
                                logger.info(f"[{platform}] No default page set, using first page")
                            else:
                                logger.info(f"[{platform}] Using default page: {selected_page.get('name', 'Unknown')}")
                            
                            if selected_page:
                                integration_data["page_id"] = selected_page.get("id") or selected_page.get("page_id")
                                integration_data["page_name"] = selected_page.get("name")
                                # CRITICAL: Use page access token, not user access token
                                page_access_token = selected_page.get("access_token")
                                if page_access_token:
                                    # Override the user access token with page access token
                                    logger.info(f"[{platform}] Using page access token for posting")
                                    integration_data["page_access_token"] = page_access_token
                                else:
                                    logger.warning(f"[{platform}] Page access token not found, using user token (may fail)")
                                logger.info(f"[{platform}] Found page_id: {integration_data.get('page_id')}, page_name: {integration_data.get('page_name')}")
                            else:
                                logger.error(f"[{platform}] No page data found in pages array")
                                created_content_items.append({
                                    "platform": platform,
                                    "status": "failed",
                                    "error": "No page data found in integration"
                                })
                                continue
                            
                            if not integration_data.get("page_id"):
                                logger.error(f"[{platform}] page_id is missing after extraction")
                                created_content_items.append({
                                    "platform": platform,
                                    "status": "failed",
                                    "error": "Facebook page_id not found"
                                })
                                continue
                        
                        elif platform == "instagram":
                            logger.info(f"[{platform}] Extracting Instagram parameters...")
                            # Instagram needs ig_user_id from profile_data or meta_data
                            ig_user_id = None
                            
                            # Try from profile_data (stored during OAuth)
                            if integration.profile_data:
                                ig_user_id = integration.profile_data.get("id")
                                logger.debug(f"[{platform}] Found id in profile_data: {ig_user_id}")
                            
                            # Try from pages (Instagram Business Account linked to Facebook Page)
                            if not ig_user_id and integration.pages:
                                for page in integration.pages if isinstance(integration.pages, list) else []:
                                    if page.get("instagram_business_account"):
                                        ig_user_id = page.get("instagram_business_account", {}).get("id")
                                        logger.debug(f"[{platform}] Found ig_user_id from pages: {ig_user_id}")
                                        break
                            
                            # Try from meta_data
                            if not ig_user_id:
                                ig_user_id = integration_data.get("ig_user_id") or integration_data.get("instagram_user_id") or integration_data.get("instagram_business_account_id")
                                logger.debug(f"[{platform}] Found ig_user_id from meta_data: {ig_user_id}")
                            
                            # Try from platform_user_id as last resort
                            if not ig_user_id and integration.platform_user_id:
                                ig_user_id = str(integration.platform_user_id)
                                logger.debug(f"[{platform}] Using platform_user_id as ig_user_id: {ig_user_id}")
                            
                            if not ig_user_id:
                                logger.error(f"[{platform}] ig_user_id not found. profile_data: {integration.profile_data}, pages: {integration.pages}, meta_data keys: {list(integration_data.keys())}, platform_user_id: {integration.platform_user_id}")
                                created_content_items.append({
                                    "platform": platform,
                                    "status": "failed",
                                    "error": "Instagram user_id not found"
                                })
                                continue
                            
                            integration_data["ig_user_id"] = str(ig_user_id)
                            logger.info(f"[{platform}] Found ig_user_id: {ig_user_id}")
                        
                        elif platform == "linkedin":
                            logger.info(f"[{platform}] Extracting LinkedIn parameters...")
                            entity_id = None
                            is_organization = False
                            
                            # Get default organization from meta_data first (set by user in integrations page)
                            # Then fall back to organizations array
                            selected_org = None
                            default_page_id = integration_data.get("default_page_id") or (integration.meta_data or {}).get("default_page_id")
                            
                            if integration.organizations:
                                if isinstance(integration.organizations, list):
                                    # First try to find the user-selected default
                                    if default_page_id:
                                        logger.info(f"[{platform}] Looking for default_page_id: {default_page_id}")
                                        for org in integration.organizations:
                                            if isinstance(org, dict):
                                                org_id = str(org.get("id") or org.get("entity_id") or org.get("organization_id") or "")
                                                if org_id == str(default_page_id):
                                                    selected_org = org
                                                    logger.info(f"[{platform}] Found matching organization for default_page_id: {org.get('name', 'Unknown')}")
                                                    break
                                    
                                    # If no default found by ID, check for is_default flag (legacy)
                                    if not selected_org:
                                        for org in integration.organizations:
                                            if isinstance(org, dict) and org.get("is_default"):
                                                selected_org = org
                                                logger.info(f"[{platform}] Found organization with is_default flag: {org.get('name', 'Unknown')}")
                                                break
                                    
                                    # If still no default, use first organization
                                    if not selected_org and integration.organizations:
                                        selected_org = integration.organizations[0]
                                        logger.info(f"[{platform}] No default set, using first organization: {selected_org.get('name', 'Unknown')}")
                                elif isinstance(integration.organizations, dict):
                                    # Single organization
                                    selected_org = integration.organizations
                            
                            if not selected_org:
                                # Fall back to first organization if no default is set
                                selected_org = integration.organizations[0] if isinstance(integration.organizations, list) and integration.organizations else None
                                if selected_org:
                                    logger.info(f"[{platform}] Fallback to first organization: {selected_org.get('name', 'Unknown')}")
                            
                            if selected_org:
                                entity_id = selected_org.get("id") or selected_org.get("entity_id") or selected_org.get("organization_id")
                                is_organization = selected_org.get("is_organization", False)
                                logger.info(f"[{platform}] Selected organization: name={selected_org.get('name', 'Unknown')}, entity_id={entity_id}, is_organization={is_organization}")
                            
                            # Try from meta_data if still not found
                            if not entity_id:
                                entity_id = integration_data.get("entity_id") or integration_data.get("organization_id") or integration_data.get("person_id")
                                is_organization = integration_data.get("is_organization", False)
                                logger.info(f"[{platform}] Found entity_id from meta_data: {entity_id}, is_organization: {is_organization}")
                            
                            # Try from platform_user_id or platform_name if still not found
                            if not entity_id:
                                # LinkedIn entity_id might be stored in platform_user_id
                                if integration.platform_user_id:
                                    entity_id = str(integration.platform_user_id)
                                    logger.info(f"[{platform}] Using platform_user_id as entity_id: {entity_id}")
                            
                            if not entity_id:
                                logger.error(f"[{platform}] entity_id not found. organizations: {integration.organizations}, meta_data keys: {list(integration_data.keys())}, platform_user_id: {integration.platform_user_id}")
                                created_content_items.append({
                                    "platform": platform,
                                    "status": "failed",
                                    "error": "LinkedIn entity_id not found"
                                })
                                continue
                            
                            # Clean entity_id - remove URN prefix if present
                            if isinstance(entity_id, str) and "urn:li:" in entity_id.lower():
                                # Extract numeric ID from URN like "urn:li:organization:123456" or "urn:li:person:123456"
                                # Handle nested URNs like "urn:li:person:urn:li:organization:123456"
                                if "urn:li:organization:" in entity_id.lower():
                                    # Extract organization ID
                                    org_part = entity_id.split("urn:li:organization:")[-1]
                                    entity_id = org_part.split(":")[0] if ":" in org_part else org_part
                                    is_organization = True
                                    logger.info(f"[{platform}] Extracted organization entity_id from nested URN: {entity_id}")
                                elif "urn:li:person:" in entity_id.lower():
                                    # Extract person ID
                                    person_part = entity_id.split("urn:li:person:")[-1]
                                    entity_id = person_part.split(":")[0] if ":" in person_part else person_part
                                    is_organization = False
                                    logger.info(f"[{platform}] Extracted person entity_id from nested URN: {entity_id}")
                                else:
                                    # Simple URN format
                                    parts = entity_id.split(":")
                                    if len(parts) >= 4:
                                        entity_id = parts[-1]
                                        is_organization = "organization" in entity_id.lower() or "organization" in str(integration.organizations).lower()
                                        logger.info(f"[{platform}] Extracted entity_id from URN: {entity_id}, is_organization: {is_organization}")
                            
                            integration_data["entity_id"] = str(entity_id)
                            integration_data["is_organization"] = is_organization
                            logger.info(f"[{platform}] Final entity_id: {integration_data.get('entity_id')}, is_organization: {integration_data.get('is_organization')}")
                        
                        elif platform == "twitter":
                            logger.info(f"[{platform}] Extracting Twitter parameters...")
                            # Twitter only needs access_token (bearer token)
                            if not integration.access_token:
                                logger.error(f"[{platform}] access_token is missing")
                                created_content_items.append({
                                    "platform": platform,
                                    "status": "failed",
                                    "error": "Twitter access_token not found"
                                })
                                continue
                            logger.info(f"[{platform}] Access token present: {integration.access_token[:20]}...")
                        
                        elif platform == "tiktok":
                            logger.info(f"[{platform}] Extracting TikTok parameters...")
                            # TikTok needs access_token and video URL
                            if not integration.access_token:
                                logger.error(f"[{platform}] access_token is missing")
                                created_content_items.append({
                                    "platform": platform,
                                    "status": "failed",
                                    "error": "TikTok access_token not found"
                                })
                                continue
                            
                            if not all_media_urls or not any(url.endswith(('.mp4', '.mov', '.avi')) for url in all_media_urls):
                                logger.error(f"[{platform}] No video URL found in media_urls")
                                created_content_items.append({
                                    "platform": platform,
                                    "status": "failed",
                                    "error": "TikTok requires a video URL"
                                })
                                continue
                            logger.info(f"[{platform}] Access token and video URL present")
                        
                        # Validate access token
                        if not integration.access_token:
                            logger.error(f"[{platform}] access_token is missing for all platforms")
                            created_content_items.append({
                                "platform": platform,
                                "status": "failed",
                                "error": "Access token not found"
                            })
                            continue
                        
                        logger.info(f"[{platform}] All required parameters extracted. Starting post...")
                        logger.debug(f"[{platform}] Integration data keys: {list(integration_data.keys())}")
                        
                        # Post to platform (call async helper directly)
                        # Use page access token for Facebook if available, otherwise use user token
                        access_token_to_use = integration.access_token
                        if platform == "facebook" and integration_data.get("page_access_token"):
                            access_token_to_use = integration_data["page_access_token"]
                            logger.info(f"[{platform}] Using page access token for posting")
                        
                        # Posting is async (uses HTTP requests), so use asyncio.run()
                        post_result = asyncio.run(
                            _post_to_social_platform_async(
                                platform=platform,
                                content=generated_content,
                                access_token=access_token_to_use,
                                integration_data=integration_data,
                                media_urls=all_media_urls if all_media_urls else None,
                                integration=integration,
                                db_session=db
                            )
                        )
                        
                        logger.info(f"[TASK 5/6] [{platform}] Post result: success={post_result.get('success')}, error={post_result.get('error', 'None')}")
                        
                        if post_result.get("success"):
                            # Create content item
                            content_item = ContentItem(
                                tenant_id=UUID(tenant_id),
                                execution_id=UUID(execution_id),
                                content_type="social_post",
                                platform=platform,
                                title=f"Post for {platform}",
                                content=generated_content,
                                publish_status="published",
                                published_at=datetime.now(timezone.utc),
                                platform_post_id=post_result.get("post_id"),
                                images=image_urls if image_urls else [],
                                videos=video_urls if video_urls else [],
                                meta_data={
                                    "post_type": post_result.get("post_type", "text"),
                                    "post_result": post_result
                                }
                            )
                            
                            db.add(content_item)
                            posting_passed += 1
                            logger.info(f"[TASK 5/6] [{platform}] ✓ PASSED - Post published successfully (ID: {post_result.get('post_id', 'N/A')})")
                            db.commit()  # Sync commit
                            db.refresh(content_item)  # Sync refresh
                            
                            created_content_items.append({
                                "id": str(content_item.id),
                                "platform": platform,
                                "post_id": post_result.get("post_id"),
                                "status": "published"
                            })
                        else:
                            posting_failed += 1
                            error_msg = post_result.get('error', 'Unknown error')
                            logger.error(f"[TASK 5/6] [{platform}] ✗ FAILED - Post failed: {error_msg}")
                            created_content_items.append({
                                "platform": platform,
                                "status": "failed",
                                "error": error_msg
                            })
                    
                    except Exception as e:
                        posting_failed += 1
                        logger.error(f"[TASK 5/6] [{platform}] ✗ FAILED - Exception during posting: {str(e)}", exc_info=True)
                        created_content_items.append({
                            "platform": platform,
                            "status": "failed",
                            "error": str(e)
                        })
                
                # Step 6: Update execution status and log summary
                logger.info("[TASK 6/6] Finalizing execution...")
                
                # Log posting summary
                if posting_passed > 0 or posting_failed > 0 or posting_skipped > 0:
                    tasks.append({
                        "task": "Platform Posting",
                        "status": "PARTIAL" if (posting_failed > 0 or posting_skipped > 0) else "PASSED",
                        "details": f"{posting_passed} passed, {posting_failed} failed, {posting_skipped} skipped"
                    })
                    logger.info(f"[TASK 5/6] Platform posting summary: {posting_passed} passed, {posting_failed} failed, {posting_skipped} skipped")
                
                # Calculate task summary
                passed_count = sum(1 for t in tasks if t["status"] == "PASSED")
                failed_count = sum(1 for t in tasks if t["status"] == "FAILED")
                skipped_count = sum(1 for t in tasks if t["status"] == "SKIPPED")
                partial_count = sum(1 for t in tasks if t["status"] == "PARTIAL")
                total_tasks = len(tasks)
                
                # Log final summary
                logger.info("=" * 80)
                logger.info("CONTENT CREATION EXECUTION SUMMARY")
                logger.info("=" * 80)
                logger.info(f"Total Tasks: {total_tasks}")
                logger.info(f"✓ Passed: {passed_count}")
                logger.info(f"✗ Failed: {failed_count}")
                logger.info(f"⊘ Skipped: {skipped_count}")
                logger.info(f"⚠ Partial: {partial_count}")
                logger.info("")
                logger.info("Task Details:")
                for i, task in enumerate(tasks, 1):
                    status_symbol = "✓" if task["status"] == "PASSED" else "✗" if task["status"] == "FAILED" else "⊘" if task["status"] == "SKIPPED" else "⚠"
                    logger.info(f"  {i}. {status_symbol} {task['task']}: {task['status']} - {task['details']}")
                logger.info("=" * 80)
                
                # Get the first successful content or first platform content for summary
                summary_content = ""
                for platform in platforms:
                    if platform in platform_contents and platform_contents[platform]:
                        summary_content = platform_contents[platform]
                        break
                
                # Update execution status (sync)
                result = db.execute(
                    select(AgentExecution).where(AgentExecution.id == UUID(execution_id))
                )
                execution = result.scalar_one_or_none()
                if execution:
                    execution.status = "completed"
                    execution.completed_at = datetime.now(timezone.utc)
                    if execution.started_at:
                        delta = execution.completed_at - execution.started_at
                        execution.execution_time_ms = int(delta.total_seconds() * 1000)
                    execution.result = {
                        "content": summary_content,
                        "platform_contents": platform_contents,
                        "content_items": created_content_items,
                        "images_generated": len(image_urls),
                        "videos_generated": len(video_urls),
                        "platforms_posted": [item["platform"] for item in created_content_items if item.get("status") == "published"],
                        "task_summary": {
                            "total_tasks": total_tasks,
                            "passed": passed_count,
                            "failed": failed_count,
                            "skipped": skipped_count,
                            "partial": partial_count,
                            "tasks": tasks
                        }
                    }
                    execution.steps_executed = []
                    execution.tools_used = []
                    db.commit()
                    db.refresh(execution)
                
                logger.info("[TASK 6/6] ✓ PASSED - Execution completed and status updated")
                
                return {
                    "success": True,
                    "execution_id": execution_id,
                    "content_items": created_content_items,
                    "platform_contents": platform_contents,
                    "content": summary_content
                }
        finally:
            db.close()  # Sync close
    
    except Exception as e:
    
        logger.error(f"Content creation execution failed: {str(e)}")
        
        # Update execution status (sync)
        try:
            from app.db.session import create_worker_session_factory
            from app.models.agent_execution import AgentExecution
            from sqlalchemy import select
            
            SessionFactory = create_worker_session_factory()
            db = SessionFactory()
            try:
                result = db.execute(
                    select(AgentExecution).where(AgentExecution.id == UUID(execution_id))
                )
                execution = result.scalar_one_or_none()
                if execution:
                    execution.status = "failed"
                    execution.error_message = str(e)
                    execution.completed_at = datetime.now(timezone.utc)
                    if execution.started_at:
                        delta = execution.completed_at - execution.started_at
                        execution.execution_time_ms = int(delta.total_seconds() * 1000)
                    db.commit()
            finally:
                db.close()  # Sync close
        except Exception as update_error:
            logger.error(f"Failed to update execution status: {str(update_error)}")
        
        raise self.retry(exc=e, countdown=120)