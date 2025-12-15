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
    number_of_images: int = 1
) -> List[bytes]:
        """
        Generate images using Imagen model via the new google.genai API.
        
        Args:
            prompt: Text prompt for image generation
            aspect_ratio: Image aspect ratio (e.g., "1:1", "16:9", "9:16")
            number_of_images: Number of images to generate
        
        Returns:
            List of image data as bytes (decoded, ready to use)
        """
        try:
            import base64
            
            model_name = self.image_model_name or "gemini-2.5-flash-image"
            logger.info(f"Generating {number_of_images} image(s) with {model_name}, prompt: {prompt[:100]}...")
            
            images = []
            
            for _ in range(number_of_images):
                def _generate():
                    response = self.genai_client.models.generate_content(
                        model=model_name,
                        contents=[prompt]
                    )
                    return response
                
                response = await asyncio.to_thread(_generate)
                
                # Process response parts
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
        number_of_images: int = 1
    ) -> List[bytes]:
        """
        Generate images synchronously - for Celery workers.
        
        Args:
            prompt: Text prompt for image generation
            aspect_ratio: Image aspect ratio (e.g., "1:1", "16:9", "9:16")
            number_of_images: Number of images to generate
        
        Returns:
            List of image data as bytes (decoded, ready to use)
        """
        try:
            import base64
            
            model_name = self.image_model_name or "gemini-2.5-flash-image"
            logger.info(f"[SYNC] Generating {number_of_images} image(s) with {model_name}")
            
            images = []
            
            for _ in range(number_of_images):
                # Call API directly (synchronous)
                response = self.genai_client.models.generate_content(
                    model=model_name,
                    contents=[prompt]
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
        Generate video using Veo 3.1 model via the new google.genai API.
        
        Args:
            prompt: Text prompt for video generation
            duration_seconds: Video duration in seconds
            aspect_ratio: Video aspect ratio (e.g., "16:9", "9:16", "1:1")
        
        Returns:
            Video data as bytes (MP4 format)
        """
        try:
            import time
            
            model_name = self.video_model_name or "veo-3.1-generate-preview"
            logger.info(f"Generating video with {model_name}, prompt: {prompt[:100]}..., duration: {duration_seconds}s")
            
            def _generate():
                # Start video generation - returns an operation
                
                # Configuration for the video (if supported)
                config = {'duration_seconds': float(duration_seconds), 'aspect_ratio': aspect_ratio}
                call_kwargs = {'model': model_name, 'prompt': prompt}
                
                # Try creating a config object if types is available
                if types and hasattr(types, 'GenerateVideosConfig'):
                    try:
                        cfg_obj = types.GenerateVideosConfig(
                            aspect_ratio=aspect_ratio,
                            duration_seconds=float(duration_seconds)
                        )
                        call_kwargs['config'] = cfg_obj
                    except Exception as e:
                        logger.warning(f"Failed to create GenerateVideosConfig: {e}")
                        call_kwargs['config'] = config
                else:
                    call_kwargs['config'] = config

                # 1. Try client.models.generate_videos (Standard)
                try:
                    if hasattr(self.genai_client.models, 'generate_videos'):
                        return self.genai_client.models.generate_videos(**call_kwargs)
                except Exception as e:
                    logger.warning(f"client.models.generate_videos failed: {e}")

                # 2. Try client.generate_videos (Alternative)
                try:
                    if hasattr(self.genai_client, 'generate_videos'):
                        return self.genai_client.generate_videos(**call_kwargs)
                except Exception as e:
                    logger.warning(f"client.generate_videos failed: {e}")

                # 3. Try singular naming: client.models.generate_video
                try:
                    if hasattr(self.genai_client.models, 'generate_video'):
                        return self.genai_client.models.generate_video(**call_kwargs)
                except Exception as e:
                    logger.warning(f"client.models.generate_video failed: {e}")

                # 4. Try singular naming: client.generate_video
                try:
                    if hasattr(self.genai_client, 'generate_video'):
                        return self.genai_client.generate_video(**call_kwargs)
                except Exception as e:
                    logger.warning(f"client.generate_video failed: {e}")

                # 5. Fallback: Try getting model instance (Wrapped to prevent crash)
                try:
                    logger.info("Attempting fallback to models.get() pattern...")
                    video_model = self.genai_client.models.get(model_name)
                    
                    if hasattr(video_model, 'generate_videos'):
                        return video_model.generate_videos(prompt=prompt, config=call_kwargs.get('config'))
                    elif hasattr(video_model, 'generate'):
                        return video_model.generate(prompt=prompt, config=call_kwargs.get('config'))
                    else:
                        raise AttributeError("Model instance found but has no generate methods")
                except TypeError as type_error:
                     # Specific catch for "Models.get() takes 1 positional argument" error
                     logger.warning(f"Fallback to models.get() failed with TypeError (known issue in some versions): {type_error}")
                except Exception as fallback_error:
                    logger.warning(f"Fallback to models.get() failed: {fallback_error}")
                
                 # 6. Fallback: Try with v1beta API version (often needed for Veo/experimental)
                try:
                    logger.info("Attempting fallback to v1beta API client...")
                    # Create a temporary client with v1beta
                    beta_client = genai.Client(api_key=self.api_key, http_options={'api_version': 'v1beta'})
                    
                    if hasattr(beta_client.models, 'generate_videos'):
                         logger.info("Found generate_videos on v1beta client!")
                         return beta_client.models.generate_videos(**call_kwargs)
                    elif hasattr(beta_client, 'generate_videos'):
                         return beta_client.generate_videos(**call_kwargs)
                except Exception as beta_error:
                    logger.warning(f"Fallback to v1beta client failed: {beta_error}")

                # If we get here, nothing worked
                # Log available methods for debugging
                available_models = dir(self.genai_client.models) if hasattr(self.genai_client, 'models') else []
                logger.error(f"Generate video failed. Available client.models methods: {available_models}")
                raise AttributeError("Video generation method not found on Google GenAI client (checked standard and v1beta)")
            
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
                    # Try operations.get() pattern
                    if hasattr(self.genai_client, 'operations') and hasattr(self.genai_client.operations, 'get'):
                         return self.genai_client.operations.get(op)
                    return op # If API doesn't support polling this way, rely on internal update
                
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
                # Try to get content attribute
                video_data = getattr(video_file, 'content', None)
                if not video_data:
                    raise Exception(f"Unable to extract video data from file object: {type(video_file)}")
            
            if not video_data:
                raise Exception("Downloaded video file is empty")
            
            logger.info(f"✓ Video generated successfully ({len(video_data)} bytes)")
            return video_data
            
        except Exception as e:
            logger.error(f"Gemini video generation failed: {str(e)}", exc_info=True)
            raise Exception(f"Gemini video generation failed: {str(e)}")
    
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
            
            model_name = self.video_model_name or "veo-3.1-generate-preview"
            logger.info(f"[SYNC] Generating video with {model_name}, duration: {duration_seconds}s")
            
            # Configure video generation
            config = None
            if types and hasattr(types, 'GenerateVideosConfig'):
                config = types.GenerateVideosConfig(
                    aspect_ratio=aspect_ratio,
                    duration_seconds=float(duration_seconds)
                )
            
            # Start video generation
            call_kwargs = {'model': model_name, 'prompt': prompt}
            if config:
                call_kwargs['config'] = config
            
            if hasattr(self.genai_client.models, 'generate_videos'):
                operation = self.genai_client.models.generate_videos(**call_kwargs)
            elif hasattr(self.genai_client, 'generate_videos'):
                operation = self.genai_client.generate_videos(**call_kwargs)
            else:
                raise Exception("Video generation method not found")
            
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
            logger.error(f"[SYNC] Video generation failed: {str(e)}")
            raise Exception(f"Video generation failed: {str(e)}")
    
    async def generate_embeddings(
        self,
        texts: List[str],
        task_type: str = "RETRIEVAL_DOCUMENT"
    ) -> List[List[float]]:
        """Generate embeddings using Google text-embedding-004"""
        
        try:
            model_name = self.embedding_model_name or "text-embedding-004"
            
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
