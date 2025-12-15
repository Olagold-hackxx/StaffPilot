"""
Twitter/X posting service
"""
import requests
import httpx
import base64
from typing import Dict, List, Optional
from datetime import datetime, timezone, timedelta
from app.utils.logger import logger


class TwitterPostingService:
    """Service for posting to Twitter/X"""
    
    @staticmethod
    async def refresh_access_token(
        refresh_token: str,
        client_id: str,
        client_secret: str,
        scope: Optional[str] = None
    ) -> Dict:
        """
        Refresh Twitter access token using refresh token
        
        Args:
            refresh_token: Twitter refresh token
            client_id: Twitter OAuth2 client ID
            client_secret: Twitter OAuth2 client secret
            scope: Optional space-separated scopes to request (prevents losing permissions)
        
        Returns:
            Dictionary with new access_token, refresh_token, and expires_in
        """
        try:
            # Validate inputs
            if not refresh_token or not refresh_token.strip():
                error_msg = "Refresh token is empty or None"
                logger.error(f"[Twitter] {error_msg}")
                return {"success": False, "error": error_msg}
            
            if not client_id or not client_id.strip():
                error_msg = "Client ID is empty or None"
                logger.error(f"[Twitter] {error_msg}")
                return {"success": False, "error": error_msg}
            
            if not client_secret or not client_secret.strip():
                error_msg = "Client secret is empty or None"
                logger.error(f"[Twitter] {error_msg}")
                return {"success": False, "error": error_msg}
            
            # Log token info for debugging (first/last few chars only)
            logger.debug(f"[Twitter] Refresh token length: {len(refresh_token)}, starts with: {refresh_token[:10]}..., ends with: ...{refresh_token[-10:]}")
            
            credentials = f"{client_id}:{client_secret}"
            b64_credentials = base64.b64encode(credentials.encode()).decode()
            
            # Prepare request data
            request_data = {
                "refresh_token": refresh_token.strip(),  # Ensure no whitespace
                "grant_type": "refresh_token"
            }
            
            # Explicitly request scopes if provided to ensure permissions are retained
            if scope:
                request_data["scope"] = scope
            
            logger.debug(f"[Twitter] Making refresh token request to Twitter API...")
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.twitter.com/2/oauth2/token",
                    data=request_data,
                    headers={
                        "Authorization": f"Basic {b64_credentials}",
                        "Content-Type": "application/x-www-form-urlencoded"
                    }
                )
                
                if response.status_code != 200:
                    error_data = response.json() if response.content else {}
                    error_msg = error_data.get("error_description", f"Token refresh failed with status {response.status_code}")
                    logger.error(f"[Twitter] Token refresh failed: {error_msg}")
                    return {"success": False, "error": error_msg}
                
                token_data = response.json()
                
                # Log granted scopes to verify permissions
                granted_scopes = token_data.get("scope", "unknown")
                logger.info(f"[Twitter] Refresh successful. Granted scopes: {granted_scopes}")
                
                if "tweet.write" not in granted_scopes:
                    logger.error(f"[Twitter] CRITICAL: Refreshed token MISSING 'tweet.write' scope! Posting will fail.")
                
                return {
                    "success": True,
                    "access_token": token_data.get("access_token"),
                    "refresh_token": token_data.get("refresh_token"),  # Twitter may return a new refresh token
                    "expires_in": token_data.get("expires_in", 7200),  # Default 2 hours
                    "scope": granted_scopes
                }
        
        except Exception as e:
            logger.error(f"[Twitter] Token refresh error: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def upload_media_v2(
        media_url: str, 
        bearer_token: str,
        oauth1_token: Optional[str] = None,
        oauth1_token_secret: Optional[str] = None,
        consumer_key: Optional[str] = None,
        consumer_secret: Optional[str] = None
    ):
        """
        Upload media to Twitter using OAuth 1.0a authentication.
        
        Note: Twitter's media upload endpoints require OAuth 1.0a, not OAuth 2.0.
        OAuth 2.0 tokens cannot be used for media uploads, even if they have 'tweet.write' scope.
        
        Args:
            media_url: URL to media file (image or video) - can be Cloudinary URL
            bearer_token: Twitter OAuth2 bearer token (not used for upload, but kept for compatibility)
            oauth1_token: OAuth 1.0a access token (required for media upload)
            oauth1_token_secret: OAuth 1.0a access token secret (required for media upload)
            consumer_key: Twitter API consumer key (required for OAuth 1.0a)
            consumer_secret: Twitter API consumer secret (required for OAuth 1.0a)
        
        Returns:
            Tuple of (media_id_string, error) or (None, error_message)
        """
        import tempfile
        import os
        from urllib.parse import urlparse
        
        upload_url = "https://upload.twitter.com/1.1/media/upload.json"
        
        # Download media from URL (Cloudinary or other)
        logger.info(f"[Twitter] Fetching image from: {media_url[:100]}...")
        media_response = requests.get(media_url, timeout=30)
        media_response.raise_for_status()
        
        if not media_response.content:
            error_msg = f"Downloaded media from {media_url} is empty"
            logger.error(f"[Twitter] {error_msg}")
            return None, error_msg
        
        # Check content type from response headers first
        content_type = media_response.headers.get('Content-Type', '')
        
        # Clean content type - remove codecs and other parameters (Twitter doesn't accept them)
        if ';' in content_type:
            base_content_type = content_type.split(';')[0].strip()
            logger.debug(f"[Twitter] Cleaning content type: {content_type} -> {base_content_type}")
            content_type = base_content_type
        
        # Detect if this is a video based on URL or content-type
        url_lower = media_url.lower()
        is_video = False
        
        # Check for video indicators
        if 'video/' in content_type.lower():
            is_video = True
        elif '/video/' in url_lower or url_lower.endswith(('.mp4', '.mov', '.avi', '.webm', '.mkv')):
            is_video = True
        elif 'cloudinary' in url_lower and '/video/upload/' in url_lower:
            is_video = True
        
        # If no content type in headers or not yet determined, try to determine from URL or response content
        if not content_type or (not is_video and 'image' not in content_type.lower()):
            # Check URL extension
            if url_lower.endswith('.png'):
                content_type = 'image/png'
            elif url_lower.endswith(('.jpg', '.jpeg')):
                content_type = 'image/jpeg'
            elif url_lower.endswith('.gif'):
                content_type = 'image/gif'
            elif url_lower.endswith('.webp'):
                content_type = 'image/webp'
            elif url_lower.endswith('.mp4'):
                content_type = 'video/mp4'
                is_video = True
            elif url_lower.endswith('.mov'):
                content_type = 'video/quicktime'
                is_video = True
            # Check for Cloudinary URLs (they often don't have extensions)
            elif 'cloudinary' in url_lower or 'res.cloudinary.com' in url_lower:
                # Cloudinary URLs indicate type in the URL path
                if '/video/upload/' in url_lower:
                    content_type = 'video/mp4'  # Default for Cloudinary videos
                    is_video = True
                elif '/image/' in url_lower or '/images/' in url_lower:
                    # Try to detect from URL parameters or default to jpeg
                    if 'png' in url_lower or 'f_png' in url_lower:
                        content_type = 'image/png'
                    elif 'gif' in url_lower or 'f_gif' in url_lower:
                        content_type = 'image/gif'
                    elif 'webp' in url_lower or 'f_webp' in url_lower:
                        content_type = 'image/webp'
                    else:
                        content_type = 'image/jpeg'  # Default for Cloudinary images
                else:
                    content_type = 'image/jpeg'  # Default
            else:
                # Try to detect from actual content (magic bytes)
                content_bytes = media_response.content[:12]
                if content_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
                    content_type = 'image/png'
                elif content_bytes.startswith(b'\xff\xd8\xff'):
                    content_type = 'image/jpeg'
                elif content_bytes.startswith(b'GIF89a') or content_bytes.startswith(b'GIF87a'):
                    content_type = 'image/gif'
                elif content_bytes.startswith(b'RIFF') and b'WEBP' in content_bytes:
                    content_type = 'image/webp'
                # Check for video formats
                elif len(content_bytes) >= 12 and content_bytes[4:8] == b'ftyp':  # MP4/MOV
                    content_type = 'video/mp4'
                    is_video = True
                elif content_bytes.startswith(b'\x1a\x45\xdf\xa3'):  # WebM
                    content_type = 'video/webm'
                    is_video = True
                else:
                    content_type = 'image/jpeg'  # Default fallback
        
        # Check file size (Twitter limits: 5MB for images, 512MB for videos)
        file_size = len(media_response.content)
        if is_video:
            if file_size > 512 * 1024 * 1024:  # 512MB
                logger.error(f"[Twitter] Video too large: {file_size} bytes (max 512MB)")
                return None, f"Video file too large: {file_size} bytes. Twitter limit is 512MB."
            logger.info(f"[Twitter] Video content type: {content_type}, size: {file_size} bytes")
        else:
            if file_size > 5 * 1024 * 1024:  # 5MB
                logger.error(f"[Twitter] Image too large: {file_size} bytes (max 5MB)")
                return None, f"Image file too large: {file_size} bytes. Twitter limit is 5MB."
            logger.info(f"[Twitter] Image content type: {content_type}, size: {file_size} bytes")
        
        # Twitter's media upload endpoints require OAuth 1.0a, not OAuth 2.0
        # Check if we have OAuth 1.0a tokens available
        if not (oauth1_token and oauth1_token_secret and consumer_key and consumer_secret):
            logger.error("[Twitter] OAuth 1.0a tokens not found")
            logger.error("[Twitter] Twitter's media upload endpoints require OAuth 1.0a authentication")
            return None, "OAuth 1.0a tokens required for media uploads"
        
        # Use OAuth 1.0a authentication
        try:
            from requests_oauthlib import OAuth1
            logger.info(f"[Twitter] Using OAuth 1.0a authentication for {'video' if is_video else 'image'} upload")
            auth = OAuth1(
                consumer_key,      # Consumer Key
                consumer_secret,   # Consumer Secret
                oauth1_token,      # Access Token
                oauth1_token_secret  # Access Token Secret
            )
            
            # Videos ALWAYS require chunked upload (INIT, APPEND, FINALIZE)
            # Twitter's simple upload endpoint does not support videos
            if is_video:
                # All videos must use chunked upload with media_category
                return TwitterPostingService._upload_video_chunked(
                    media_response.content,
                    content_type,
                    auth,
                    file_size
                )
            else:
                # Image upload (simple upload)
                files = {
                    "media": (
                        "image.jpg",
                        media_response.content,
                        content_type
                    )
                }
                response = requests.post(upload_url, auth=auth, files=files, timeout=60)
            
            # If we returned from chunked upload, skip the rest
            if is_video:
                # Already handled by chunked upload
                return None, None  # This shouldn't happen, chunked upload returns directly
            
            # Log response for debugging
            logger.info(f"[Twitter] Response status: {response.status_code}")
            if response.status_code != 200:
                logger.error(f"[Twitter] Error response: {response.text}")
            
            if response.status_code == 200 or response.status_code == 201:
                result = response.json()
                media_id = result.get("media_id_string") or result.get("media_id")
                if media_id:
                    # Convert to string if it's a number
                    media_id = str(media_id)
                    logger.info(f"[Twitter] Media uploaded successfully, media_id: {media_id}")
                    return media_id, None
                else:
                    logger.error(f"[Twitter] Response missing media_id: {result}")
                    return None, f"Response missing media_id: {result}"
            elif response.status_code == 403:
                # 403 Forbidden - Token may be missing 'media.write' scope or OAuth 1.0a required
                error_text = response.text
                try:
                    error_json = response.json()
                    error_msg = error_json.get("errors", [{}])[0].get("message", error_text) if isinstance(error_json.get("errors"), list) else error_text
                except:
                    error_msg = error_text
                
                logger.error(f"[Twitter] 403 Forbidden: {error_msg}")
                if "not permitted to use OAuth2" in error_msg or "OAuth2" in error_msg or not (oauth1_token and oauth1_token_secret):
                    logger.error("[Twitter] Root cause: Twitter's media upload endpoints require OAuth 1.0a authentication, not OAuth 2.0")
                    logger.error("[Twitter] OAuth 2.0 tokens cannot be used for media uploads, even with 'tweet.write' scope")
                    return None, "Media upload failed: Twitter's media upload endpoints require OAuth 1.0a authentication. OAuth 2.0 tokens cannot be used for media uploads. Please configure OAuth 1.0a tokens in the integration settings."
                else:
                    logger.error("[Twitter] The OAuth 1.0a token may be invalid or missing required permissions")
                    return None, f"Media upload failed: {error_msg}"
            else:
                error_text = response.text
                try:
                    error_json = response.json()
                    error_msg = error_json.get("errors", [{}])[0].get("message", error_text) if isinstance(error_json.get("errors"), list) else error_text
                except:
                    error_msg = error_text
                logger.error(f"[Twitter] Failed with status {response.status_code}: {error_msg}")
                return None, error_msg
        except ImportError:
            logger.error("[Twitter] requests_oauthlib not installed. Install with: pip install requests-oauthlib")
            return None, "OAuth 1.0a library not installed. Install requests-oauthlib to enable media uploads."
        except Exception as oauth_error:
            logger.error(f"[Twitter] Error setting up OAuth 1.0a: {str(oauth_error)}")
            return None, f"OAuth 1.0a setup failed: {str(oauth_error)}"
    
    @staticmethod
    def _upload_video_chunked(
        video_data: bytes,
        content_type: str,
        auth,
        file_size: int
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Upload large video files using Twitter's chunked upload API.
        Twitter requires chunked upload for videos > 5MB.
        
        Process:
        1. INIT - Initialize upload, get media_id
        2. APPEND - Upload chunks (max 5MB per chunk)
        3. FINALIZE - Finalize upload
        
        Args:
            video_data: Video file bytes
            content_type: Video content type (e.g., 'video/mp4')
            auth: OAuth1 authentication object
            file_size: Size of video file in bytes
        
        Returns:
            Tuple of (media_id_string, error) or (None, error_message)
        """
        try:
            chunk_size = 5 * 1024 * 1024  # 5MB chunks
            upload_url = "https://upload.twitter.com/1.1/media/upload.json"
            
            # Step 1: INIT - Initialize chunked upload
            # IMPORTANT: media_category is REQUIRED for videos
            init_data = {
                "command": "INIT",
                "media_type": content_type,
                "total_bytes": file_size,
                "media_category": "tweet_video"  # Required for videos: tweet_video, amplify_video, or dm_video
            }
            
            logger.info(f"[Twitter] Initializing chunked video upload ({file_size} bytes)...")
            init_response = requests.post(upload_url, auth=auth, data=init_data, timeout=60)
            
            # Parse response - INIT returns media_id on success
            # Note: INIT can return 200 or 201, and the response contains media_id
            init_result = init_response.json()
            
            # Check if response contains media_id (indicates success)
            media_id = init_result.get("media_id_string") or init_result.get("media_id")
            
            if not media_id:
                # No media_id means INIT failed
                error_msg = init_response.text
                logger.error(f"[Twitter] INIT failed - no media_id in response. Status: {init_response.status_code}, Response: {error_msg}")
                return None, f"Video upload INIT failed: {error_msg}"
            
            # Convert to string if it's a number
            media_id = str(media_id)
            
            # Log success
            logger.info(f"[Twitter] ✓ INIT successful. Media ID: {media_id}, Status: {init_response.status_code}")
            
            logger.info(f"[Twitter] Video upload initialized, media_id: {media_id}")
            
            # Step 2: APPEND - Upload chunks
            # Clean content type - remove codecs parameter if present (Twitter doesn't accept it)
            clean_content_type = content_type.split(';')[0].strip() if ';' in content_type else content_type
            logger.debug(f"[Twitter] Using content type: {clean_content_type} (original: {content_type})")
            
            segment_index = 0
            total_chunks = (file_size + chunk_size - 1) // chunk_size
            
            for offset in range(0, file_size, chunk_size):
                chunk = video_data[offset:offset + chunk_size]
                segment_index += 1
                
                append_data = {
                    "command": "APPEND",
                    "media_id": media_id,
                    "segment_index": segment_index - 1  # 0-indexed
                }
                
                files = {
                    "media": ("video.mp4", chunk, clean_content_type)
                }
                
                logger.info(f"[Twitter] Uploading chunk {segment_index}/{total_chunks} ({len(chunk)} bytes)...")
                append_response = requests.post(upload_url, auth=auth, data=append_data, files=files, timeout=120)
                
                logger.debug(f"[Twitter] APPEND response status: {append_response.status_code}")
                logger.debug(f"[Twitter] APPEND response headers: {dict(append_response.headers)}")
                
                if append_response.status_code not in [200, 204]:
                    error_msg = append_response.text or f"HTTP {append_response.status_code}"
                    logger.error(f"[Twitter] APPEND failed for chunk {segment_index}: Status {append_response.status_code}, Response: {error_msg}")
                    logger.error(f"[Twitter] APPEND request data: command={append_data.get('command')}, media_id={append_data.get('media_id')}, segment_index={append_data.get('segment_index')}")
                    return None, f"Video upload APPEND failed: {error_msg}"
                
                # 204 No Content is also a valid success response for APPEND
                if append_response.status_code == 204:
                    logger.debug(f"[Twitter] ✓ Chunk {segment_index}/{total_chunks} uploaded (204 No Content)")
                else:
                    logger.debug(f"[Twitter] ✓ Chunk {segment_index}/{total_chunks} uploaded (200 OK)")
            
            logger.info(f"[Twitter] All chunks uploaded successfully")
            
            # Step 3: FINALIZE - Finalize upload
            finalize_data = {
                "command": "FINALIZE",
                "media_id": media_id
            }
            
            logger.info(f"[Twitter] Finalizing video upload...")
            finalize_response = requests.post(upload_url, auth=auth, data=finalize_data, timeout=60)
            
            if finalize_response.status_code != 200:
                error_msg = finalize_response.text
                logger.error(f"[Twitter] FINALIZE failed: {error_msg}")
                return None, f"Video upload FINALIZE failed: {error_msg}"
            
            result = finalize_response.json()
            media_id_string = result.get("media_id_string") or media_id
            
            # Check processing status if available
            # Twitter processes videos asynchronously - we may need to wait
            processing_info = result.get("processing_info")
            if processing_info:
                state = processing_info.get("state", "unknown")
                logger.info(f"[Twitter] Video processing state: {state}")
                
                # If processing is needed, check status
                if state in ["pending", "in_progress"]:
                    check_after_secs = processing_info.get("check_after_secs", 5)
                    logger.info(f"[Twitter] Video is processing. Will check status in {check_after_secs}s...")
                    
                    # Poll for processing status (with timeout)
                    max_wait = 300  # 5 minutes max
                    elapsed = 0
                    import time
                    
                    while elapsed < max_wait:
                        time.sleep(check_after_secs)
                        elapsed += check_after_secs
                        
                        # Check status
                        status_data = {
                            "command": "STATUS",
                            "media_id": media_id_string
                        }
                        
                        status_response = requests.get(upload_url, auth=auth, params=status_data, timeout=60)
                        
                        if status_response.status_code == 200:
                            status_result = status_response.json()
                            processing_info = status_result.get("processing_info", {})
                            state = processing_info.get("state", "unknown")
                            
                            logger.info(f"[Twitter] Processing status: {state}")
                            
                            if state == "succeeded":
                                logger.info("[Twitter] ✓ Video processing succeeded")
                                break
                            elif state == "failed":
                                error = processing_info.get("error", {}).get("message", "Unknown error")
                                logger.error(f"[Twitter] Video processing failed: {error}")
                                return None, f"Video processing failed: {error}"
                            
                            check_after_secs = processing_info.get("check_after_secs", 5)
                        else:
                            logger.warning(f"[Twitter] Status check failed: {status_response.status_code}")
                            # Continue anyway - media_id is still valid
                            break
                    
                    if elapsed >= max_wait:
                        logger.warning("[Twitter] Video processing check timed out, but media_id is valid")
                elif state == "succeeded":
                    logger.info("[Twitter] ✓ Video processing already succeeded")
                elif state == "failed":
                    error = processing_info.get("error", {}).get("message", "Unknown error")
                    logger.error(f"[Twitter] Video processing failed: {error}")
                    return None, f"Video processing failed: {error}"
            else:
                logger.info("[Twitter] No processing info - video may be ready immediately")
            
            logger.info(f"[Twitter] Video uploaded successfully, media_id: {media_id_string}")
            return str(media_id_string), None
            
        except Exception as e:
            logger.error(f"[Twitter] Chunked video upload failed: {str(e)}", exc_info=True)
            return None, f"Video upload failed: {str(e)}"
    
    @staticmethod
    async def post(
        text: str,
        access_token: str,
        image_urls: Optional[List[str]] = None,
        refresh_token: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        token_expires_at: Optional[datetime] = None,
        refresh_token_expires_at: Optional[datetime] = None,
        integration_id: Optional[str] = None,
        db_session = None
    ) -> Dict:
        """
        Post to Twitter/X using OAuth2 Bearer token
        Automatically refreshes token if expired or about to expire
        
        Args:
            text: Tweet text content
            access_token: Twitter OAuth2 bearer token
            image_urls: Optional list of image URLs
            refresh_token: Optional refresh token for refreshing access token
            client_id: Optional Twitter OAuth2 client ID
            client_secret: Optional Twitter OAuth2 client secret
            token_expires_at: Optional datetime when token expires
            integration_id: Optional integration ID for updating token in DB
            db_session: Optional database session for updating token
        """
        try:
            bearer_token = access_token
            
            # FORCE REFRESH: Always refresh before posting if credentials are available
            # This ensures we always use a fresh token with correct scopes and prevents 403 errors
            # caused by token invalidation or scope loss after previous use.
            needs_refresh = False
            if refresh_token and client_id and client_secret:
                needs_refresh = True
                logger.info("[Twitter] Forcing token refresh before posting to ensure validity...")
            
            # Refresh token if needed
            if needs_refresh:
                logger.info("[Twitter] Refreshing access token...")
                # Log refresh token info for debugging (don't log full token for security)
                if refresh_token:
                    logger.debug(f"[Twitter] Using refresh token (first 20 chars): {refresh_token[:20]}... (length: {len(refresh_token)})")
                else:
                    logger.error("[Twitter] Refresh token is None or empty!")
                if client_id:
                    logger.debug(f"[Twitter] Client ID (first 10 chars): {client_id[:10]}...")
                else:
                    logger.error("[Twitter] Client ID is None or empty!")
                
                # Define scopes required for posting to ensure we maintain write access
                required_scopes = "tweet.read tweet.write users.read offline.access"
                
                refresh_result = await TwitterPostingService.refresh_access_token(
                    refresh_token=refresh_token,
                    client_id=client_id,
                    client_secret=client_secret,
                    scope=required_scopes
                )
                
                if refresh_result.get("success"):
                    # Validate scopes before proceeding
                    granted_scopes = refresh_result.get("scope", "")
                    if "tweet.write" not in granted_scopes:
                         logger.error(f"[Twitter] Refreshed token missing required 'tweet.write' scope. Cannot post.")
                         raise Exception(f"Refreshed token missing 'tweet.write' scope. Granted: {granted_scopes}")

                    bearer_token = refresh_result["access_token"]
                    new_refresh_token = refresh_result.get("refresh_token", refresh_token)
                    expires_in = refresh_result.get("expires_in", 7200)
                    new_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                    
                    logger.info("[Twitter] Token refreshed successfully")
                    
                    # Update token in database if integration_id and db_session provided
                    if integration_id and db_session:
                        try:
                            from app.models.integration import SocialIntegration
                            from sqlalchemy import select
                            from uuid import UUID
                            import inspect
                            
                            # Check if session is async by checking if execute is a coroutine function
                            is_async = inspect.iscoroutinefunction(getattr(db_session, 'execute', None))
                            
                            # Build update values dict - only update token-related fields to avoid JSON serialization issues
                            # Note: We don't update refresh_token_expires_at here - it's only set during initial token exchange
                            from sqlalchemy import update
                            update_values = {
                                'access_token': bearer_token,
                                'token_expires_at': new_expires_at
                            }
                            if new_refresh_token:
                                update_values['refresh_token'] = new_refresh_token
                            
                            if is_async:
                                # Async session - use update statement to only update token fields
                                update_stmt = (
                                    update(SocialIntegration)
                                    .where(SocialIntegration.id == UUID(integration_id) if isinstance(integration_id, str) else integration_id)
                                    .values(**update_values)
                                )
                                await db_session.execute(update_stmt)
                                await db_session.commit()
                                logger.info(f"[Twitter] Updated token in database for integration {integration_id}")
                            else:
                                # Sync session - use update statement to only update token fields
                                update_stmt = (
                                    update(SocialIntegration)
                                    .where(SocialIntegration.id == UUID(integration_id) if isinstance(integration_id, str) else integration_id)
                                    .values(**update_values)
                                )
                                db_session.execute(update_stmt)
                                db_session.commit()
                                logger.info(f"[Twitter] Updated token in database for integration {integration_id}")
                        except Exception as db_error:
                            logger.warning(f"[Twitter] Failed to update token in database: {str(db_error)}", exc_info=True)
                            # Continue with posting even if DB update fails - we have valid token in memory
                else:
                    error_msg = refresh_result.get('error', 'Unknown error')
                    logger.error(f"[Twitter] Token refresh failed: {error_msg}")
                    
                    # Check if refresh token is actually expired
                    # Twitter refresh tokens last 6 months
                    # Twitter returns "Value passed for the token was invalid" when refresh token is expired/invalid
                    refresh_token_expired = False
                    
                    # Check if refresh_token_expires_at is set and in the past
                    if refresh_token_expires_at:
                        if refresh_token_expires_at < datetime.now(timezone.utc):
                            refresh_token_expired = True
                            logger.info(f"[Twitter] Refresh token expired at {refresh_token_expires_at}")
                    
                    # Check for specific error message indicating invalid refresh token
                    # This is the most reliable indicator from Twitter API
                    is_invalid_token_error = "Value passed for the token was invalid" in error_msg
                    
                    # Only deactivate if:
                    # 1. We have explicit confirmation the refresh token is expired (refresh_token_expires_at in past)
                    # 2. OR Twitter explicitly says the token is invalid (most reliable indicator)
                    should_deactivate = refresh_token_expired or is_invalid_token_error
                    
                    # Deactivate integration if refresh token is confirmed expired/invalid
                    if should_deactivate and integration_id and db_session:
                        try:
                            from app.models.integration import SocialIntegration
                            from sqlalchemy import select
                            from uuid import UUID
                            import inspect
                            
                            if refresh_token_expired:
                                logger.warning(f"[Twitter] Refresh token expired (6 months). Deactivating integration {integration_id}")
                            elif is_invalid_token_error:
                                logger.warning(f"[Twitter] Twitter API confirmed refresh token is invalid. Deactivating integration {integration_id}")
                            
                            # Check if session is async
                            is_async = inspect.iscoroutinefunction(getattr(db_session, 'execute', None))
                            
                            if is_async:
                                # Async session
                                result = await db_session.execute(
                                    select(SocialIntegration).where(SocialIntegration.id == UUID(integration_id) if isinstance(integration_id, str) else integration_id)
                                )
                                integration = result.scalar_one_or_none()
                                
                                if integration:
                                    integration.is_active = False
                                    integration.refresh_token = None  # Clear invalid refresh token
                                    await db_session.commit()
                                    logger.info(f"[Twitter] Deactivated integration {integration_id} due to expired refresh token")
                            else:
                                # Sync session
                                result = db_session.execute(
                                    select(SocialIntegration).where(SocialIntegration.id == UUID(integration_id) if isinstance(integration_id, str) else integration_id)
                                )
                                integration = result.scalar_one_or_none()
                                
                                if integration:
                                    integration.is_active = False
                                    integration.refresh_token = None  # Clear invalid refresh token
                                    db_session.commit()
                                    logger.info(f"[Twitter] Deactivated integration {integration_id} due to expired refresh token")
                        except Exception as deactivate_error:
                            logger.error(f"[Twitter] Failed to deactivate integration: {str(deactivate_error)}")
                            # Continue to return error even if deactivation fails
                    
                    return {
                        "success": False,
                        "error": f"Token refresh failed: {error_msg}. Please reconnect your Twitter account."
                    }
            
            # Validate token format (should not be empty)
            if not bearer_token or not bearer_token.strip():
                logger.error("[Twitter] Bearer token is empty or invalid")
                return {"success": False, "error": "Bearer token is empty or invalid"}
            
            logger.info(f"[Twitter] Using bearer token (first 20 chars): {bearer_token[:20]}...")
            
            # Extract OAuth 1.0a tokens from integration meta_data if available
            # OAuth 1.0a tokens are REQUIRED for media uploads
            oauth1_token = None
            oauth1_token_secret = None
            consumer_key = None
            consumer_secret = None
            
            # Always try to fetch OAuth 1.0a tokens if we have integration_id and db_session
            if integration_id and db_session:
                try:
                    from app.models.integration import SocialIntegration, IntegrationConfig
                    from sqlalchemy import select
                    from uuid import UUID
                    import inspect
                    
                    # Check if session is async
                    is_async = inspect.iscoroutinefunction(getattr(db_session, 'execute', None))
                    
                    if is_async:
                        # Get integration to access meta_data
                        result = await db_session.execute(
                            select(SocialIntegration).where(
                                SocialIntegration.id == UUID(integration_id) if isinstance(integration_id, str) else integration_id
                            )
                        )
                        integration = result.scalar_one_or_none()
                        
                        # Get integration config for consumer key/secret
                        config_result = await db_session.execute(
                            select(IntegrationConfig).where(IntegrationConfig.platform == "twitter")
                        )
                        config = config_result.scalar_one_or_none()
                    else:
                        # Sync session
                        result = db_session.execute(
                            select(SocialIntegration).where(
                                SocialIntegration.id == UUID(integration_id) if isinstance(integration_id, str) else integration_id
                            )
                        )
                        integration = result.scalar_one_or_none()
                        
                        config_result = db_session.execute(
                            select(IntegrationConfig).where(IntegrationConfig.platform == "twitter")
                        )
                        config = config_result.scalar_one_or_none()
                    
                    if integration and integration.meta_data:
                        oauth1_token = integration.meta_data.get("oauth1_token") or integration.meta_data.get("oauth_token")
                        oauth1_token_secret = integration.meta_data.get("oauth1_token_secret") or integration.meta_data.get("oauth_token_secret")
                        logger.debug(f"[Twitter] OAuth 1.0a tokens from meta_data: token={'present' if oauth1_token else 'missing'}, secret={'present' if oauth1_token_secret else 'missing'}")
                    
                    if config:
                        # Try OAuth 1.0a credentials from settings first
                        from app.config import settings
                        consumer_key = settings.TWITTER_API_KEY or config.client_id
                        consumer_secret = settings.TWITTER_API_SECRET or config.client_secret
                    else:
                        # Fallback to settings directly
                        from app.config import settings
                        consumer_key = settings.TWITTER_API_KEY
                        consumer_secret = settings.TWITTER_API_SECRET
                    
                    if oauth1_token and oauth1_token_secret and consumer_key and consumer_secret:
                        logger.info("[Twitter] ✓ OAuth 1.0a tokens found in integration meta_data - media uploads enabled")
                    else:
                        missing = []
                        if not oauth1_token:
                            missing.append("oauth1_token")
                        if not oauth1_token_secret:
                            missing.append("oauth1_token_secret")
                        if not consumer_key:
                            missing.append("consumer_key (TWITTER_API_KEY)")
                        if not consumer_secret:
                            missing.append("consumer_secret (TWITTER_API_SECRET)")
                        logger.warning(f"[Twitter] ⚠ OAuth 1.0a tokens incomplete. Missing: {', '.join(missing)}. Media uploads will fail with 403.")
                except Exception as token_error:
                    logger.error(f"[Twitter] Failed to extract OAuth 1.0a tokens: {str(token_error)}", exc_info=True)
            elif image_urls:
                # If we have image URLs but no integration_id/db_session, we can't fetch tokens
                logger.warning("[Twitter] ⚠ Cannot fetch OAuth 1.0a tokens: integration_id or db_session not provided. Media uploads will fail.")
            
            media_ids = []
            if image_urls:
                logger.info(f"[Twitter] Uploading {len(image_urls)} media file(s)...")
                
                # Check if OAuth 1.0a tokens are available before attempting upload
                if not (oauth1_token and oauth1_token_secret and consumer_key and consumer_secret):
                    error_msg = (
                        "OAuth 1.0a tokens are required for Twitter media uploads. "
                        "Please complete the OAuth 1.0a authorization flow in the integrations settings. "
                        "Twitter's media upload endpoints require OAuth 1.0a authentication, not OAuth 2.0."
                    )
                    logger.error(f"[Twitter] {error_msg}")
                    return {"success": False, "error": error_msg}
                
                for url in image_urls:
                    media_id, error = TwitterPostingService.upload_media_v2(
                        url, 
                        bearer_token,
                        oauth1_token=oauth1_token,
                        oauth1_token_secret=oauth1_token_secret,
                        consumer_key=consumer_key,
                        consumer_secret=consumer_secret
                    )
                    if not media_id:
                        logger.error(f"[Twitter] Media upload failed for {url}: {error}")
                        return {"success": False, "error": f"Media upload failed: {error}"}
                    media_ids.append(media_id)
                    logger.info(f"[Twitter] Media uploaded successfully, media_id: {media_id}")
            
            # Use Twitter API v2 for posting
            tweet_url = "https://api.twitter.com/2/tweets"
            headers = {
                "Authorization": f"Bearer {bearer_token}",
                "Content-Type": "application/json",
            }
            
            payload = {"text": text}
            if media_ids:
                payload["media"] = {"media_ids": media_ids}
            
            logger.info(f"[Twitter] Posting tweet - text_length: {len(text)}, has_media: {bool(media_ids)}")
            logger.debug(f"[Twitter] Request URL: {tweet_url}")
            logger.debug(f"[Twitter] Request headers: Authorization=Bearer {bearer_token[:20]}...")
            logger.debug(f"[Twitter] Payload: {payload}")
            
            response = requests.post(tweet_url, headers=headers, json=payload)
            logger.info(f"[Twitter] Response status: {response.status_code}")
            
            if response.status_code in [200, 201]:
                response_data = response.json()
                post_id = response_data.get("data", {}).get("id")
                logger.info(f"[Twitter] Post successful, post_id: {post_id}")
                return {
                    "success": True,
                    "post_id": post_id,
                }
            
            # Log detailed error information
            error_text = response.text
            try:
                error_json = response.json()
                error_detail = error_json.get("detail", error_json.get("error", error_text))
                logger.error(f"[Twitter] Post failed with status {response.status_code}: {error_detail}")
                logger.debug(f"[Twitter] Full error response: {error_json}")
            except (ValueError, KeyError):
                logger.error(f"[Twitter] Post failed with status {response.status_code}: {error_text}")
            
            logger.debug(f"[Twitter] Request URL: {tweet_url}")
            logger.debug(f"[Twitter] Request headers: {dict(headers)}")
            logger.debug(f"[Twitter] Payload: {payload}")
            
            return {"success": False, "error": error_text}
        
        except requests.exceptions.RequestException as e:
            logger.error(f"[Twitter] Request exception: {str(e)}")
            return {"success": False, "error": f"Request failed: {str(e)}"}
        except Exception as e:
            logger.error(f"[Twitter] Posting error: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}

