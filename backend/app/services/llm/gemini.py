"""
Google Gemini LLM implementation using the new google.genai API
"""
import asyncio
from typing import Dict, List, Optional, AsyncGenerator
import json
from io import BytesIO
from app.services.llm.base import BaseLLMService
from app.utils.logger import logger

try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    genai = None
    types = None
    logger.warning("google-genai not installed. Install with: pip install google-genai")

try:
    from PIL import Image
    Image_available = True
except ImportError:
    Image = None
    Image_available = False
    logger.warning("PIL/Pillow not installed. Install with: pip install Pillow")


class GeminiService(BaseLLMService):
    """
    Google Gemini implementation of BaseLLMService using the new google.genai API
    """
    
    def __init__(self, api_key: str, model_config: Dict):
        if not GENAI_AVAILABLE or genai is None:
            raise ImportError("google-genai library not installed. Install with: pip install google-genai")
        
        super().__init__(api_key, model_config)
        
        # Initialize the genai client
        self.genai_client = genai.Client(api_key=api_key)
    
    async def close(self):
        """Cleanup the genai client to prevent async resource warnings."""
        try:
            if hasattr(self.genai_client, '_api_client') and hasattr(self.genai_client._api_client, 'aclose'):
                await self.genai_client._api_client.aclose()
            elif hasattr(self.genai_client, 'aclose'):
                await self.genai_client.aclose()
        except Exception:
            pass  # Ignore cleanup errors
    
    def __del__(self):
        """Destructor - attempt sync cleanup if not done."""
        pass  # Don't do anything here to avoid async issues
    
    async def generate_content(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs
    ) -> str:
        """Generate text content using Gemini"""
        
        try:
            model_name = self.content_model_name or "gemini-2.5-flash"
            
            # Build contents - can be string directly (as per reference)
            if system_instruction:
                contents = f"{system_instruction}\n\n{prompt}"
            else:
                contents = prompt
            
            def _generate():
                # Simple API call as per reference: client.models.generate_content(model, contents)
                # The new API doesn't support max_output_tokens, temperature, etc. as direct kwargs
                # Filter out all unsupported kwargs
                unsupported_params = [
                    'automatic_function_calling', 'functions', 'function_call', 'tools',
                    'max_output_tokens', 'max_tokens', 'temperature'  # These are not supported in the simple API
                ]
                
                # Only pass through kwargs that might be supported (but likely none are)
                call_kwargs = {}
                for key, value in kwargs.items():
                    if key not in unsupported_params:
                        call_kwargs[key] = value
                
                # Call the API - simple approach as per reference (no config parameters)
                if call_kwargs:
                    response = self.genai_client.models.generate_content(
                        model=model_name,
                        contents=contents,
                        **call_kwargs
                    )
                else:
                    response = self.genai_client.models.generate_content(
                        model=model_name,
                        contents=contents
                    )
                return response
            
            response = await asyncio.to_thread(_generate)
            
            # Extract text from response - use response.text (the simple approach from reference)
            if hasattr(response, 'text') and response.text:
                return str(response.text).strip()
            
            # Fallback: check response.parts if .text doesn't exist
            if hasattr(response, 'parts') and response.parts:
                text_parts = []
                for part in response.parts:
                    if hasattr(part, 'text') and part.text is not None:
                        text_parts.append(str(part.text))
                if text_parts:
                    return ''.join(text_parts).strip()
            
            raise Exception("Failed to extract text from response: No text content found.")
            
        except Exception as e:
            logger.error(f"Gemini content generation failed: {str(e)}")
            raise Exception(f"Gemini content generation failed: {str(e)}")
    
    def generate_content_sync(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs
    ) -> str:
        """Generate text content using Gemini - synchronous version for Celery workers"""
        
        try:
            model_name = self.content_model_name or "gemini-2.5-flash"
            
            # Build contents
            if system_instruction:
                contents = f"{system_instruction}\n\n{prompt}"
            else:
                contents = prompt
            
            # Call the API directly (synchronous)
            response = self.genai_client.models.generate_content(
                model=model_name,
                contents=contents
            )
            
            # Extract text from response
            if hasattr(response, 'text') and response.text:
                return str(response.text).strip()
            
            # Fallback: check response.parts
            if hasattr(response, 'parts') and response.parts:
                text_parts = []
                for part in response.parts:
                    if hasattr(part, 'text') and part.text is not None:
                        text_parts.append(str(part.text))
                if text_parts:
                    return ''.join(text_parts).strip()
            
            raise Exception("Failed to extract text from response: No text content found.")
            
        except Exception as e:
            logger.error(f"Gemini content generation failed: {str(e)}")
            raise Exception(f"Gemini content generation failed: {str(e)}")
    
    async def generate_json(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.5
    ) -> Dict:
        """Generate structured JSON output"""
        
        json_prompt = f"""{prompt}

Return your response as valid JSON only. Do not include any markdown formatting or explanation."""
        
        response_text = await self.generate_content(
            prompt=json_prompt,
            system_instruction=system_instruction,
            temperature=temperature
        )
        
        # Clean response (remove markdown if present)
        response_text = response_text.strip()
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.startswith('```'):
            response_text = response_text[3:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        
        try:
            return json.loads(response_text.strip())
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            raise Exception(f"Failed to parse JSON response: {str(e)}")
    
    async def stream_content(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Stream content generation"""
        
        model_name = self.content_model_name or "gemini-2.5-flash"
        
        # Build contents
        if system_instruction:
            full_prompt = f"{system_instruction}\n\n{prompt}"
        else:
            full_prompt = prompt
        
        def _generate():
            # Filter out unsupported kwargs - the new API doesn't support temperature, max_output_tokens, etc.
            unsupported_params = [
                'automatic_function_calling', 'functions', 'function_call', 'tools',
                'max_output_tokens', 'max_tokens', 'temperature'  # These are not supported in the simple API
            ]
            call_kwargs = {}
            
            for key, value in kwargs.items():
                if key not in unsupported_params:
                    call_kwargs[key] = value
            
            # Call with stream=True - simple approach
            if call_kwargs:
                response = self.genai_client.models.generate_content(
                    model=model_name,
                    contents=full_prompt,
                    stream=True,
                    **call_kwargs
                )
            else:
                response = self.genai_client.models.generate_content(
                    model=model_name,
                    contents=full_prompt,
                    stream=True
                )
            return response
        
        response = await asyncio.to_thread(_generate)
        
        # Stream chunks - use response.text if available, otherwise check parts
        for chunk in response:
            if hasattr(chunk, 'text') and chunk.text:
                yield chunk.text
            elif hasattr(chunk, 'parts') and chunk.parts:
                for part in chunk.parts:
                    if hasattr(part, 'text') and part.text:
                        yield part.text
    
    async def generate_image(
    self,
    prompt: str,
    aspect_ratio: str = "1:1",
    number_of_images: int = 1,
    reference_images: Optional[List[bytes]] = None
) -> List[bytes]:
        """
        Generate images using Imagen model via the new google.genai API.
        
        Args:
            prompt: Text prompt for image generation
            aspect_ratio: Image aspect ratio (e.g., "1:1", "16:9", "9:16")
            number_of_images: Number of images to generate
            reference_images: Optional list of image bytes to use as references
        
        Returns:
            List of image data as bytes (decoded, ready to use)
        """
        try:
            import base64
            from google.genai import types
            
            model_name = self.image_model_name or "imagen-3.0-generate-002"
            logger.info(f"Generating {number_of_images} image(s) with {model_name}, prompt: {prompt[:100]}...")
            
            if reference_images:
                logger.info(f"Using {len(reference_images)} reference images for generation")
            
            images = []
            
            # Check if model is an Imagen model (uses generate_images API)
            is_imagen_model = "imagen" in model_name.lower()
            
            for i in range(number_of_images):
                def _generate():
                    if is_imagen_model:
                        # Use Imagen API (generate_images method)
                        try:
                            # Imagen 4 uses image_size instead of aspect_ratio
                            config = types.GenerateImagesConfig(
                                number_of_images=1,
                                image_size="1K",  # Optional: "2K" or "1K"
                            )
                            
                            response = self.genai_client.models.generate_images(
                                model=model_name,
                                prompt=prompt,
                                config=config
                            )
                            return response
                        except AttributeError:
                            # Fallback to generate_content if generate_images not available
                            logger.warning("generate_images not available, falling back to generate_content")
                            return self.genai_client.models.generate_content(
                                model=model_name,
                                contents=[prompt]
                            )
                    else:
                        # Use Gemini multimodal API (generate_content)
                        contents = []
                        
                        # Add reference images first
                        if reference_images:
                            for idx, img_bytes in enumerate(reference_images[:3]):  # Max 3 references
                                # Detect mime type
                                mime_type = "image/jpeg"
                                if img_bytes[:8] == b'\x89PNG\r\n\x1a\n':
                                    mime_type = "image/png"
                                elif img_bytes[:2] == b'\xff\xd8':
                                    mime_type = "image/jpeg"
                                
                                contents.append(types.Part.from_bytes(
                                    data=img_bytes,
                                    mime_type=mime_type
                                ))
                                logger.info(f"Added reference image {idx+1} ({mime_type}, {len(img_bytes)} bytes)")
                        
                        # Add text prompt
                        if reference_images:
                            contents.append(f"Using the reference images above as style inspiration, generate: {prompt}")
                        else:
                            contents.append(prompt)
                        
                        response = self.genai_client.models.generate_content(
                            model=model_name,
                            contents=contents
                        )
                        return response
                
                response = await asyncio.to_thread(_generate)
                
                # Handle Imagen API response (generated_images list)
                if is_imagen_model and hasattr(response, 'generated_images') and response.generated_images:
                    for gen_image in response.generated_images:
                        try:
                            if hasattr(gen_image, 'image') and hasattr(gen_image.image, 'image_bytes'):
                                image_data = gen_image.image.image_bytes
                                if image_data:
                                    logger.info(f"✓ Got Imagen image ({len(image_data)} bytes)")
                                    images.append(image_data)
                        except Exception as e:
                            logger.error(f"Failed to extract Imagen image: {str(e)}")
                    continue  # Skip the generate_content response handling below
                
                # Process response parts (for generate_content responses)
                if hasattr(response, 'parts') and response.parts:
                    for part in response.parts:
                        if hasattr(part, 'inline_data') and part.inline_data is not None:
                            try:
                                inline_data = part.inline_data
                                image_data = None
                                
                                # Extract raw data
                                if hasattr(inline_data, 'data'):
                                    data = inline_data.data
                                    
                                    # ===== FIX: Handle base64-encoded data =====
                                    if isinstance(data, str):
                                        # Data is base64-encoded string - decode it
                                        try:
                                            image_data = base64.b64decode(data)
                                            logger.info(f"✓ Decoded base64 image data ({len(image_data)} bytes)")
                                        except Exception as e:
                                            logger.error(f"Failed to decode base64: {str(e)}")
                                            continue
                                            
                                    elif isinstance(data, bytes):
                                        # Check if it's actually base64-encoded bytes
                                        # PNG signature in base64 starts with: iVBORw0K
                                        if data.startswith(b'iVBORw0K') or data.startswith(b'/9j/'):
                                            # It's base64-encoded bytes, decode it
                                            try:
                                                image_data = base64.b64decode(data)
                                                logger.info(f"✓ Decoded base64 bytes to image ({len(image_data)} bytes)")
                                            except Exception as e:
                                                logger.error(f"Failed to decode base64 bytes: {str(e)}")
                                                continue
                                        else:
                                            # It's already raw binary image data
                                            image_data = data
                                            logger.info(f"✓ Using raw binary image data ({len(image_data)} bytes)")
                                    else:
                                        logger.warning(f"Unexpected data type: {type(data)}")
                                        continue
                                
                                # Validate the decoded image
                                if image_data:
                                    # Verify it's a valid image by checking magic bytes
                                    if image_data.startswith(b'\x89PNG'):
                                        logger.info("✓ Valid PNG image")
                                    elif image_data.startswith(b'\xff\xd8\xff'):
                                        logger.info("✓ Valid JPEG image")
                                    elif image_data.startswith(b'GIF8'):
                                        logger.info("✓ Valid GIF image")
                                    else:
                                        logger.warning(f"Unknown image format. First 10 bytes: {image_data[:10].hex()}")
                                    
                                    # Optionally validate with PIL
                                    if Image_available and Image:
                                        try:
                                            img_buffer = BytesIO(image_data)
                                            pil_image = Image.open(img_buffer)
                                            pil_image.verify()
                                            logger.info(f"✓ PIL validation passed: {pil_image.format} {pil_image.size}")
                                            
                                            # Re-open and ensure it's PNG
                                            img_buffer = BytesIO(image_data)
                                            pil_image = Image.open(img_buffer)
                                            
                                            if pil_image.format != 'PNG':
                                                logger.info(f"Converting {pil_image.format} to PNG")
                                                img_bytes = BytesIO()
                                                pil_image.save(img_bytes, format='PNG')
                                                image_data = img_bytes.getvalue()
                                        
                                        except Exception as e:
                                            logger.warning(f"PIL validation failed: {str(e)}")
                                            # Continue anyway - the binary data might still be valid
                                    
                                    images.append(image_data)
                                    logger.info(f"✓ Added image {len(images)} ({len(image_data)} bytes)")
                            
                            except Exception as e:
                                logger.error(f"Failed to process image: {str(e)}", exc_info=True)
                                continue
                
                # Also check candidates structure
                if not images and hasattr(response, 'candidates') and response.candidates:
                    for candidate in response.candidates:
                        if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                            for part in candidate.content.parts:
                                if hasattr(part, 'inline_data') and part.inline_data is not None:
                                    try:
                                        inline_data = part.inline_data
                                        image_data = None
                                        
                                        if hasattr(inline_data, 'data'):
                                            data = inline_data.data
                                            
                                            # ===== FIX: Same decoding logic =====
                                            if isinstance(data, str):
                                                try:
                                                    image_data = base64.b64decode(data)
                                                    logger.info(f"✓ Decoded base64 from candidate ({len(image_data)} bytes)")
                                                except Exception as e:
                                                    logger.error(f"Failed to decode: {str(e)}")
                                                    continue
                                            
                                            elif isinstance(data, bytes):
                                                if data.startswith(b'iVBORw0K') or data.startswith(b'/9j/'):
                                                    try:
                                                        image_data = base64.b64decode(data)
                                                        logger.info(f"✓ Decoded base64 bytes from candidate ({len(image_data)} bytes)")
                                                    except Exception as e:
                                                        logger.error(f"Failed to decode: {str(e)}")
                                                        continue
                                                else:
                                                    image_data = data
                                                    logger.info(f"✓ Using raw binary from candidate ({len(image_data)} bytes)")
                                        
                                        if image_data:
                                            # Validate
                                            if image_data.startswith(b'\x89PNG') or image_data.startswith(b'\xff\xd8\xff'):
                                                images.append(image_data)
                                                logger.info(f"✓ Added candidate image {len(images)}")
                                            else:
                                                logger.warning(f"Invalid image format from candidate")
                                    
                                    except Exception as e:
                                        logger.error(f"Failed to process candidate image: {str(e)}", exc_info=True)
                                        continue
                
                if images and number_of_images == 1:
                    break
            
            if not images:
                # DEBUG: Check if there's text content explaining why
                if hasattr(response, 'text') and response.text:
                    logger.warning(f"Image generation returned text instead of image: {response.text}")
                elif hasattr(response, 'parts'):
                    for part in response.parts:
                        if hasattr(part, 'text') and part.text:
                            logger.warning(f"Image generation returned text part: {part.text}")

                # DEBUG: Deep inspection
                logger.warning(f"FULL RESPONSE DUMP: {response}")
                if hasattr(response, 'prompt_feedback'):
                   logger.warning(f"Prompt Feedback: {response.prompt_feedback}")
                if hasattr(response, 'candidates'):
                   logger.warning(f"Candidates: {response.candidates}")
                            
                raise Exception("No valid images generated")
            
            logger.info(f"✓ Successfully generated {len(images)} image(s)")
            return images
            
        except Exception as e:
            logger.error(f"Image generation failed: {str(e)}", exc_info=True)
            raise Exception(f"Image generation failed: {str(e)}")
    
    def generate_image_sync(
        self,
        prompt: str,
        aspect_ratio: str = "1:1",
        number_of_images: int = 1,
        reference_images: Optional[List[bytes]] = None
    ) -> List[bytes]:
        """
        Generate images synchronously - for Celery workers.
        
        Args:
            prompt: Text prompt for image generation
            aspect_ratio: Image aspect ratio (e.g., "1:1", "16:9", "9:16")
            number_of_images: Number of images to generate
            reference_images: Optional list of image bytes to use as references
        
        Returns:
            List of image data as bytes (decoded, ready to use)
        """
        try:
            import base64
            from google.genai import types
            
            model_name = self.image_model_name or "imagen-3.0-generate-002"
            logger.info(f"[SYNC] Generating {number_of_images} image(s) with {model_name}")
            
            images = []
            is_imagen_model = "imagen" in model_name.lower()
            
            for _ in range(number_of_images):
                if is_imagen_model:
                    # Use Imagen API (generate_images method)
                    try:
                        # Imagen 4 uses image_size instead of aspect_ratio
                        config = types.GenerateImagesConfig(
                            number_of_images=1,
                            image_size="1K",  # Optional: "2K" or "1K"
                        )
                        
                        response = self.genai_client.models.generate_images(
                            model=model_name,
                            prompt=prompt,
                            config=config
                        )
                        
                        # Handle Imagen API response
                        if hasattr(response, 'generated_images') and response.generated_images:
                            for gen_image in response.generated_images:
                                if hasattr(gen_image, 'image') and hasattr(gen_image.image, 'image_bytes'):
                                    image_data = gen_image.image.image_bytes
                                    if image_data:
                                        images.append(image_data)
                                        logger.info(f"[SYNC] Added Imagen image ({len(image_data)} bytes)")
                        continue
                    except AttributeError as e:
                        logger.warning(f"generate_images not available, falling back: {e}")
                        # Fall through to generate_content below
                
                # Use Gemini multimodal API (generate_content)
                contents = []
                
                # Add reference images first
                if reference_images:
                    for i, img_bytes in enumerate(reference_images[:3]):  # Max 3 references
                        # Detect mime type
                        mime_type = "image/jpeg"
                        if img_bytes[:8] == b'\x89PNG\r\n\x1a\n':
                            mime_type = "image/png"
                        elif img_bytes[:2] == b'\xff\xd8':
                            mime_type = "image/jpeg"
                        
                        contents.append(types.Part.from_bytes(
                            data=img_bytes,
                            mime_type=mime_type
                        ))
                
                # Add text prompt
                if reference_images:
                    contents.append(f"Using the reference images above as style inspiration, generate: {prompt}")
                else:
                    contents.append(prompt)

                # Call API directly (synchronous)
                response = self.genai_client.models.generate_content(
                    model=model_name,
                    contents=contents
                )
                
                # Process response parts
                if hasattr(response, 'parts') and response.parts:
                    for part in response.parts:
                        if hasattr(part, 'inline_data') and part.inline_data is not None:
                            try:
                                inline_data = part.inline_data
                                image_data = None
                                
                                if hasattr(inline_data, 'data'):
                                    data = inline_data.data
                                    
                                    if isinstance(data, str):
                                        try:
                                            image_data = base64.b64decode(data)
                                        except Exception:
                                            continue
                                    elif isinstance(data, bytes):
                                        if data.startswith(b'iVBORw0K') or data.startswith(b'/9j/'):
                                            try:
                                                image_data = base64.b64decode(data)
                                            except Exception:
                                                continue
                                        else:
                                            image_data = data
                                
                                if image_data:
                                    images.append(image_data)
                                    logger.info(f"[SYNC] Added image {len(images)} ({len(image_data)} bytes)")
                            except Exception:
                                continue
                
                if images and number_of_images == 1:
                    break
            
            if not images:
                raise Exception("No valid images generated")
            
            logger.info(f"[SYNC] Successfully generated {len(images)} image(s)")
            return images
            
        except Exception as e:
            logger.error(f"[SYNC] Image generation failed: {str(e)}")
            raise Exception(f"Image generation failed: {str(e)}")
        
    async def generate_video(
        self,
        prompt: str,
        duration_seconds: int = 5,
        aspect_ratio: str = "16:9"
    ) -> bytes:
        """
        Generate video using Veo model via the google.genai API.
        
        Args:
            prompt: Text prompt for video generation
            duration_seconds: Video duration in seconds
            aspect_ratio: Video aspect ratio (e.g., "16:9", "9:16", "1:1")
        
        Returns:
            Video data as bytes (MP4 format)
        """
        try:
            model_name = self.video_model_name or "veo-3.1-generate-preview"
            logger.info(f"Generating video with {model_name}, prompt: {prompt[:100]}..., duration: {duration_seconds}s")
            
            # Check if video generation is available
            if not hasattr(self.genai_client.models, 'generate_videos'):
                available = [m for m in dir(self.genai_client.models) if not m.startswith('_')]
                raise Exception(
                    f"Video generation (generate_videos) not available in your google-genai library. "
                    f"Available methods: {available}. "
                    f"Please upgrade: pip install --upgrade google-genai"
                )
            
            def _generate():
                # Start video generation - returns an operation
                # Append negative constraint for text/subtitles
                full_prompt = f"{prompt} Do not include any text, subtitles on screen, or captions in the video."
                
                operation = self.genai_client.models.generate_videos(
                    model=model_name,
                    prompt=full_prompt
                )
                return operation
            
            # Start the operation
            operation = await asyncio.to_thread(_generate)
            operation_name = operation.name if hasattr(operation, 'name') else str(operation)
            logger.info(f"Video generation operation started: {operation_name}")
            
            # Poll the operation status until the video is ready
            max_wait_time = 600  # 10 minutes max
            wait_interval = 10  # Check every 10 seconds
            elapsed_time = 0
            
            while not operation.done:
                if elapsed_time >= max_wait_time:
                    raise Exception(f"Video generation timed out after {max_wait_time} seconds")
                
                logger.info(f"Waiting for video generation to complete... (elapsed: {elapsed_time}s)")
                await asyncio.sleep(wait_interval)
                elapsed_time += wait_interval
                
                # Get updated operation status
                def _get_operation(op):
                    if hasattr(self.genai_client, 'operations') and hasattr(self.genai_client.operations, 'get'):
                        return self.genai_client.operations.get(op)
                    return op
                
                operation = await asyncio.to_thread(_get_operation, operation)
            
            logger.info("Video generation completed!")
            
            # Check if operation was successful
            if hasattr(operation, 'error') and operation.error:
                error_msg = str(operation.error)
                logger.error(f"Video generation operation failed: {error_msg}")
                raise Exception(f"Video generation failed: {error_msg}")
            
            # Download the generated video
            if not hasattr(operation, 'response') or not operation.response:
                raise Exception("Video generation operation completed but no response found")
            
            if not hasattr(operation.response, 'generated_videos') or not operation.response.generated_videos:
                raise Exception("Video generation operation completed but no videos found in response")
            
            generated_video = operation.response.generated_videos[0]
            
            if not hasattr(generated_video, 'video') or not generated_video.video:
                raise Exception("Generated video object found but no video file available")
            
            # Download the video file
            def _download():
                return self.genai_client.files.download(file=generated_video.video)
            
            video_file = await asyncio.to_thread(_download)
            
            # Read video data
            if hasattr(video_file, 'read'):
                video_data = video_file.read()
            elif hasattr(video_file, 'getvalue'):
                video_data = video_file.getvalue()
            elif isinstance(video_file, bytes):
                video_data = video_file
            else:
                video_data = getattr(video_file, 'content', None)
                if not video_data:
                    raise Exception(f"Unable to extract video data from file object: {type(video_file)}")
            
            if not video_data:
                raise Exception("Downloaded video file is empty")
            
            logger.info(f"✓ Video generated successfully ({len(video_data)} bytes)")
            return video_data
            
        except Exception as e:
            logger.error(f"Video generation failed: {str(e)}", exc_info=True)
            raise Exception(f"Video generation failed: {str(e)}")
    
    def generate_video_sync(
        self,
        prompt: str,
        duration_seconds: int = 5,
        aspect_ratio: str = "16:9"
    ) -> bytes:
        """
        Generate video synchronously - for Celery workers.
        Uses time.sleep instead of asyncio.sleep.
        
        Args:
            prompt: Text prompt for video generation
            duration_seconds: Video duration in seconds
            aspect_ratio: Video aspect ratio (e.g., "16:9", "9:16", "1:1")
        
        Returns:
            Video data as bytes (MP4 format)
        """
        try:
            import time
            
            model_name = self.video_model_name or "veo3.1"
            logger.info(f"[SYNC] Generating video with {model_name}, duration: {duration_seconds}s")
            
            # Check if video generation is available
            if not hasattr(self.genai_client.models, 'generate_videos'):
                available = [m for m in dir(self.genai_client.models) if not m.startswith('_')]
                raise Exception(
                    f"Video generation (generate_videos) not available. "
                    f"Available methods: {available}. "
                    f"Please upgrade: pip install --upgrade google-genai"
                )
            
            # Start video generation
            # Append negative constraint for text/subtitles
            full_prompt = f"{prompt} Do not include any text, subtitles on screen, or captions in the video."
            
            operation = self.genai_client.models.generate_videos(
                model=model_name,
                prompt=full_prompt
            )
            
            operation_name = operation.name if hasattr(operation, 'name') else str(operation)
            logger.info(f"[SYNC] Video generation operation started: {operation_name}")
            
            # Poll the operation status (using time.sleep, not asyncio)
            max_wait_time = 600  # 10 minutes max
            wait_interval = 10  # Check every 10 seconds
            elapsed_time = 0
            
            while not operation.done:
                if elapsed_time >= max_wait_time:
                    raise Exception(f"Video generation timed out after {max_wait_time} seconds")
                
                logger.info(f"[SYNC] Waiting for video... (elapsed: {elapsed_time}s)")
                time.sleep(wait_interval)  # Sync sleep
                elapsed_time += wait_interval
                
                # Get updated operation status
                if hasattr(self.genai_client, 'operations') and hasattr(self.genai_client.operations, 'get'):
                    operation = self.genai_client.operations.get(operation)
            
            logger.info("[SYNC] Video generation completed!")
            
            # Check for errors
            if hasattr(operation, 'error') and operation.error:
                raise Exception(f"Video generation failed: {operation.error}")
            
            # Get video data
            if not hasattr(operation, 'response') or not operation.response:
                raise Exception("No response found after completion")
            
            if not hasattr(operation.response, 'generated_videos') or not operation.response.generated_videos:
                raise Exception("No videos found in response")
            
            generated_video = operation.response.generated_videos[0]
            
            if not hasattr(generated_video, 'video') or not generated_video.video:
                raise Exception("No video file available")
            
            # Download the video file
            video_file = self.genai_client.files.download(file=generated_video.video)
            
            # Read video data
            if hasattr(video_file, 'read'):
                video_data = video_file.read()
            elif hasattr(video_file, 'getvalue'):
                video_data = video_file.getvalue()
            elif isinstance(video_file, bytes):
                video_data = video_file
            else:
                video_data = getattr(video_file, 'content', None)
                if not video_data:
                    raise Exception(f"Unable to extract video data from: {type(video_file)}")
            
            if not video_data:
                raise Exception("Downloaded video file is empty")
            
            logger.info(f"[SYNC] Video generated successfully ({len(video_data)} bytes)")
            return video_data
            
        except Exception as e:
            logger.error(f"[SYNC] Video generation failed: {str(e)}", exc_info=True)
            raise Exception(f"Video generation failed: {str(e)}")
    
    def generate_video_with_references_sync(
        self,
        prompt: str,
        reference_images: List[bytes],
        aspect_ratio: str = "16:9"
    ) -> bytes:
        """
        Generate video with reference images synchronously - for Celery workers.
        Uses Veo's reference image feature to incorporate brand assets.
        
        Args:
            prompt: Text prompt for video generation
            reference_images: List of image data as bytes to use as references
            aspect_ratio: Video aspect ratio
        
        Returns:
            Video data as bytes (MP4 format)
        """
        try:
            import time
            
            model_name = self.video_model_name or "veo3.1"
            logger.info(f"[SYNC] Generating video with {len(reference_images)} reference images")
            
            # Check if video generation is available
            if not hasattr(self.genai_client.models, 'generate_videos'):
                raise Exception("Video generation (generate_videos) not available")
            
            # Build reference image objects using VideoGenerationReferenceImage
            reference_image_objects = []
            for i, img_bytes in enumerate(reference_images[:3]):  # Max 3 reference images for Veo 3.1
                try:
                    # Check if types module is available
                    if types is None:
                        logger.warning("google.genai.types not available for reference images")
                        break
                    
                    # Detect mime type
                    mime_type = "image/jpeg"
                    if img_bytes[:4] == b'\x89PNG':
                        mime_type = "image/png"
                    elif img_bytes[:4] == b'GIF8':
                        mime_type = "image/gif"
                    elif img_bytes[:4] == b'RIFF':
                        mime_type = "image/webp"
                    
                    # Create types.Image with image_bytes and mime_type
                    image_obj = types.Image(
                        image_bytes=img_bytes,
                        mime_type=mime_type
                    )
                    
                    # Create VideoGenerationReferenceImage with types.Image
                    ref_image = types.VideoGenerationReferenceImage(
                        image=image_obj,
                        reference_type="asset"
                    )
                    reference_image_objects.append(ref_image)
                    logger.info(f"[SYNC] Added reference image {i+1} ({len(img_bytes)} bytes, {mime_type})")
                except Exception as e:
                    logger.warning(f"[SYNC] Failed to create reference image {i+1}: {e}")
            
            # Build config with reference images
            config = None
            if reference_image_objects and types is not None:
                config = types.GenerateVideosConfig(
                    reference_images=reference_image_objects,
                    aspect_ratio=aspect_ratio
                )
            
            # Start video generation
            # Append negative constraint for text/subtitles
            full_prompt = f"{prompt} Do not include any text, subtitles on screen, or captions in the video."
            
            if config:
                operation = self.genai_client.models.generate_videos(
                    model=model_name,
                    prompt=full_prompt,
                    config=config
                )
            else:
                operation = self.genai_client.models.generate_videos(
                    model=model_name,
                    prompt=full_prompt,
                    config=types.GenerateVideosConfig(aspect_ratio=aspect_ratio) if types else None
                )
            
            operation_name = operation.name if hasattr(operation, 'name') else str(operation)
            logger.info(f"[SYNC] Video generation with references started: {operation_name}")
            
            # Poll the operation status
            max_wait_time = 600
            wait_interval = 10
            elapsed_time = 0
            
            while not operation.done:
                if elapsed_time >= max_wait_time:
                    raise Exception(f"Video generation timed out after {max_wait_time} seconds")
                
                logger.info(f"[SYNC] Waiting for video... (elapsed: {elapsed_time}s)")
                time.sleep(wait_interval)
                elapsed_time += wait_interval
                
                if hasattr(self.genai_client, 'operations') and hasattr(self.genai_client.operations, 'get'):
                    operation = self.genai_client.operations.get(operation)
            
            logger.info("[SYNC] Video generation with references completed!")
            
            # Check for errors
            if hasattr(operation, 'error') and operation.error:
                raise Exception(f"Video generation failed: {operation.error}")
            
            # Get video data
            if not hasattr(operation, 'response') or not operation.response:
                raise Exception("No response found after completion")
            
            if not hasattr(operation.response, 'generated_videos') or not operation.response.generated_videos:
                logger.error(f"[SYNC] No videos found in response.")
                try:
                    # Log everything we can about the operation
                    logger.error(f"Operation dict: {operation.__dict__}")
                    if hasattr(operation, 'result'):
                        logger.error(f"Operation result: {operation.result}")
                except Exception as log_err:
                    logger.error(f"Failed to log operation details: {log_err}")
                
                raise Exception("No videos found in response")
            
            generated_video = operation.response.generated_videos[0]
            
            if not hasattr(generated_video, 'video') or not generated_video.video:
                raise Exception("No video file available")
            
            # Download the video file
            video_file = self.genai_client.files.download(file=generated_video.video)
            
            # Read video data
            if hasattr(video_file, 'read'):
                video_data = video_file.read()
            elif hasattr(video_file, 'getvalue'):
                video_data = video_file.getvalue()
            elif isinstance(video_file, bytes):
                video_data = video_file
            else:
                video_data = getattr(video_file, 'content', None)
                if not video_data:
                    raise Exception(f"Unable to extract video data from: {type(video_file)}")
            
            if not video_data:
                raise Exception("Downloaded video file is empty")
            
            logger.info(f"[SYNC] Video with references generated successfully ({len(video_data)} bytes)")
            return video_data
            
        except Exception as e:
            logger.error(f"[SYNC] Video generation with references failed: {str(e)}", exc_info=True)
            raise Exception(f"Video generation with references failed: {str(e)}")
    
    def extend_video_sync(
        self,
        video_object,  # This should be the video object from a previous generation
        prompt: str
    ) -> tuple:
        """
        Extend an existing video by approximately 8 seconds synchronously.
        Uses Veo's video extension feature.
        
        Args:
            video_object: The video object from a previous generation (operation.response.generated_videos[0].video)
            prompt: Text prompt describing what should happen in the extension
        
        Returns:
            Tuple of (extended video data as bytes, video object for further extension)
        """
        try:
            import time
            from google.genai import types
            
            model_name = self.video_model_name or "veo3.1"
            logger.info(f"[SYNC] Extending video with prompt: {prompt[:100]}...")
            
            # Start video extension using the video parameter
            # According to the API, we pass the video object from previous generation
            # Append negative constraint for text/subtitles
            full_prompt = f"{prompt} Do not include any text, subtitles on screen, or captions in the video."
            
            operation = self.genai_client.models.generate_videos(
                model=model_name,
                video=video_object,  # Pass the video object from previous generation
                prompt=full_prompt,
                config=types.GenerateVideosConfig(
                    number_of_videos=1,
                    resolution="720p"
                )
            )
            
            operation_name = operation.name if hasattr(operation, 'name') else str(operation)
            logger.info(f"[SYNC] Video extension operation started: {operation_name}")
            
            # Poll the operation status
            max_wait_time = 600
            wait_interval = 10
            elapsed_time = 0
            
            while not operation.done:
                if elapsed_time >= max_wait_time:
                    raise Exception(f"Video extension timed out after {max_wait_time} seconds")
                
                logger.info(f"[SYNC] Waiting for extended video... (elapsed: {elapsed_time}s)")
                time.sleep(wait_interval)
                elapsed_time += wait_interval
                
                if hasattr(self.genai_client, 'operations') and hasattr(self.genai_client.operations, 'get'):
                    operation = self.genai_client.operations.get(operation)
            
            logger.info("[SYNC] Video extension completed!")
            
            # Check for errors
            if hasattr(operation, 'error') and operation.error:
                raise Exception(f"Video extension failed: {operation.error}")
            
            # Get extended video data
            if not hasattr(operation, 'response') or not operation.response:
                raise Exception("No response found after completion")
            
            if not hasattr(operation.response, 'generated_videos') or not operation.response.generated_videos:
                raise Exception("No videos found in response")
            
            extended_video = operation.response.generated_videos[0]
            
            if not hasattr(extended_video, 'video') or not extended_video.video:
                raise Exception("No video file available")
            
            # Download the extended video
            video_file = self.genai_client.files.download(file=extended_video.video)
            
            # Read video data
            if hasattr(video_file, 'read'):
                extended_data = video_file.read()
            elif hasattr(video_file, 'getvalue'):
                extended_data = video_file.getvalue()
            elif isinstance(video_file, bytes):
                extended_data = video_file
            else:
                extended_data = getattr(video_file, 'content', None)
                if not extended_data:
                    raise Exception(f"Unable to extract extended video data from: {type(video_file)}")
            
            if not extended_data:
                raise Exception("Downloaded extended video file is empty")
            
            logger.info(f"[SYNC] Video extended successfully ({len(extended_data)} bytes)")
            # Return both bytes and video object for further extension
            return extended_data, extended_video.video
            
        except Exception as e:
            logger.error(f"[SYNC] Video extension failed: {str(e)}", exc_info=True)
            raise Exception(f"Video extension failed: {str(e)}")
    
    def generate_extended_video_sync(
        self,
        prompt: str,
        target_duration_seconds: int,
        reference_images: Optional[List[bytes]] = None,
        aspect_ratio: str = "16:9"
    ) -> bytes:
        """
        Generate a video and extend it to reach the target duration.
        Each extension adds approximately 8 seconds.
        
        Args:
            prompt: Text prompt for video generation
            target_duration_seconds: Target video duration (8-60 seconds)
            reference_images: Optional list of image bytes to use as references
            aspect_ratio: Video aspect ratio
        
        Returns:
            Final extended video data as bytes (MP4 format)
        """
        try:
            import time
            from google.genai import types
            
            # Clamp duration to valid range
            target_duration_seconds = max(8, min(60, target_duration_seconds))
            
            model_name = self.video_model_name or "veo3.1"
            logger.info(f"[SYNC] Generating extended video: target={target_duration_seconds}s, refs={len(reference_images or [])}")
            
            # Step 1: Generate initial video and get the video object for chaining
            # Build reference image objects if provided
            reference_image_objects = []
            if reference_images:
                for i, img_bytes in enumerate(reference_images[:3]):
                    try:
                        if types is not None:
                            mime_type = "image/jpeg"
                            if img_bytes[:4] == b'\x89PNG':
                                mime_type = "image/png"
                            image_obj = types.Image(
                                image_bytes=img_bytes,
                                mime_type=mime_type
                            )
                            ref_image = types.VideoGenerationReferenceImage(
                                image=image_obj,
                                reference_type="asset"
                            )
                            reference_image_objects.append(ref_image)
                            logger.info(f"[SYNC] Added reference image {i+1} ({len(img_bytes)} bytes)")
                    except Exception as e:
                        logger.warning(f"[SYNC] Failed to create reference image: {e}")
            
            # Build config
            config = types.GenerateVideosConfig(
                number_of_videos=1,
                resolution="720p"
            )
            if reference_image_objects:
                config = types.GenerateVideosConfig(
                    number_of_videos=1,
                    resolution="720p",
                    reference_images=reference_image_objects,
                    aspect_ratio=aspect_ratio
                )
            
            # Generate initial video
            # Append negative constraint for text/subtitles
            full_prompt = f"{prompt} Do not include any text, subtitles on screen, or captions in the video."
            
            operation = self.genai_client.models.generate_videos(
                model=model_name,
                prompt=full_prompt,
                config=config
            )
            
            # Poll until complete
            max_wait_time = 600
            wait_interval = 10
            elapsed_time = 0
            
            while not operation.done:
                if elapsed_time >= max_wait_time:
                    raise Exception(f"Video generation timed out after {max_wait_time} seconds")
                logger.info(f"[SYNC] Waiting for initial video... (elapsed: {elapsed_time}s)")
                time.sleep(wait_interval)
                elapsed_time += wait_interval
                if hasattr(self.genai_client, 'operations') and hasattr(self.genai_client.operations, 'get'):
                    operation = self.genai_client.operations.get(operation)
            
            if hasattr(operation, 'error') and operation.error:
                raise Exception(f"Video generation failed: {operation.error}")
            
            if not hasattr(operation, 'response') or not operation.response:
                raise Exception("No response found after completion")
            if not hasattr(operation.response, 'generated_videos') or not operation.response.generated_videos:
                raise Exception("No videos found in response")
            
            generated_video = operation.response.generated_videos[0]
            if not hasattr(generated_video, 'video') or not generated_video.video:
                raise Exception("No video file available")
            
            # Store the video object for chaining extensions
            current_video_object = generated_video.video
            
            logger.info("[SYNC] Initial video generated successfully")
            
            current_duration = 8
            extension_count = 0
            
            # Step 2: Extend until we reach target duration
            while current_duration < target_duration_seconds:
                extension_count += 1
                logger.info(f"[SYNC] Extension {extension_count}: current={current_duration}s, target={target_duration_seconds}s")
                
                try:
                    # Extend video using the video object from previous generation
                    operation = self.genai_client.models.generate_videos(
                        model=model_name,
                        video=current_video_object,  # Pass the video object from previous generation
                        prompt=full_prompt,
                        config=types.GenerateVideosConfig(
                            number_of_videos=1,
                            resolution="720p"
                        )
                    )
                    
                    # Poll until complete
                    elapsed_time = 0
                    while not operation.done:
                        if elapsed_time >= max_wait_time:
                            raise Exception(f"Video extension timed out")
                        logger.info(f"[SYNC] Waiting for extension... (elapsed: {elapsed_time}s)")
                        time.sleep(wait_interval)
                        elapsed_time += wait_interval
                        if hasattr(self.genai_client, 'operations') and hasattr(self.genai_client.operations, 'get'):
                            operation = self.genai_client.operations.get(operation)
                    
                    if hasattr(operation, 'error') and operation.error:
                        raise Exception(f"Extension failed: {operation.error}")
                    
                    if not hasattr(operation.response, 'generated_videos') or not operation.response.generated_videos:
                        raise Exception("No videos in extension response")
                    
                    extended_video = operation.response.generated_videos[0]
                    if not hasattr(extended_video, 'video') or not extended_video.video:
                        raise Exception("No video file in extension")
                    
                    # Update video object for next extension
                    current_video_object = extended_video.video
                    current_duration += 8
                    logger.info(f"[SYNC] Extension {extension_count} completed")
                    
                except Exception as ext_error:
                    logger.warning(f"[SYNC] Extension {extension_count} failed: {ext_error}")
                    break
            
            # Step 3: Download the final video
            video_file = self.genai_client.files.download(file=current_video_object)
            
            # Read video data
            if hasattr(video_file, 'read'):
                video_data = video_file.read()
            elif hasattr(video_file, 'getvalue'):
                video_data = video_file.getvalue()
            elif isinstance(video_file, bytes):
                video_data = video_file
            else:
                video_data = getattr(video_file, 'content', None)
                if not video_data:
                    raise Exception(f"Unable to extract video data from: {type(video_file)}")
            

            if not video_data:
                raise Exception("Downloaded video file is empty")
            
            logger.info(f"[SYNC] Extended video complete: {extension_count} extensions, ~{current_duration}s, {len(video_data)} bytes")
            return video_data
            
        except Exception as e:
            logger.error(f"[SYNC] Extended video generation failed: {str(e)}", exc_info=True)
            raise Exception(f"Extended video generation failed: {str(e)}")
    
    async def generate_embeddings(
        self,
        texts: List[str],
        task_type: str = "RETRIEVAL_DOCUMENT"
    ) -> List[List[float]]:
        """Generate embeddings using Google gemini-embedding-001"""
        
        try:
            model_name = self.embedding_model_name or "gemini-embedding-001"
            
            # Use the new API for embeddings
            # The new API doesn't support task_type parameter
            def _embed():
                result = self.genai_client.models.embed_content(
                    model=model_name,
                    contents=texts
                )
                return result
            
            result = await asyncio.to_thread(_embed)
            
            # Extract embeddings from result
            # The new API returns ContentEmbedding objects with a 'values' attribute
            embeddings_list = []
            
            # Handle different response structures
            if hasattr(result, 'embeddings'):
                embeddings = result.embeddings
            elif isinstance(result, dict) and 'embeddings' in result:
                embeddings = result['embeddings']
            elif isinstance(result, dict) and 'embedding' in result:
                embeddings = result['embedding']
            elif isinstance(result, list):
                embeddings = result
            else:
                embeddings = []
            
            if not embeddings:
                logger.warning("No embeddings returned from Google API")
                return []
            
            # Extract values from ContentEmbedding objects or use directly if already lists
            for embedding in embeddings:
                if hasattr(embedding, 'values'):
                    # ContentEmbedding object - extract values
                    embeddings_list.append(list(embedding.values))
                elif isinstance(embedding, list):
                    # Already a list of floats
                    embeddings_list.append(embedding)
                elif isinstance(embedding, (int, float)):
                    # Single value (shouldn't happen, but handle it)
                    logger.warning("Unexpected single value in embeddings")
                    continue
                else:
                    logger.warning(f"Unexpected embedding type: {type(embedding)}")
                    continue
            
            if not embeddings_list:
                logger.warning("No valid embeddings extracted from result")
                return []
            
            return embeddings_list
            
        except Exception as e:
            logger.error(f"Embedding generation failed: {str(e)}")
            raise Exception(f"Embedding generation failed: {str(e)}")
