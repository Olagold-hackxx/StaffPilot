"""
LinkedIn posting service
"""
import requests
from io import BytesIO
import logging
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse
from app.utils.logger import logger
from app.config import settings

LINKEDIN_API_URL = "https://api.linkedin.com/v2"


class LinkedInPostingService:
    """Service for posting to LinkedIn"""
    
    @staticmethod
    def _detect_media_type(url: str, content_type: Optional[str] = None) -> Tuple[str, bool]:
        """
        Detect if URL is an image or video
        
        Returns:
            Tuple of (media_type, is_video)
            media_type: "image" or "video"
            is_video: True if video, False if image
        """
        url_lower = url.lower()
        
        # Check content type first if available
        if content_type:
            if content_type.startswith("video/"):
                return ("video", True)
            elif content_type.startswith("image/"):
                return ("image", False)
        
        # Check URL patterns
        # Cloudinary video URLs
        if "cloudinary" in url_lower and "/video/upload/" in url_lower:
            return ("video", True)
        
        # Cloudinary image URLs
        if "cloudinary" in url_lower and "/image/upload/" in url_lower:
            return ("image", False)
        
        # Check file extensions
        video_extensions = ['.mp4', '.mov', '.avi', '.webm', '.mkv', '.flv']
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']
        
        if any(url_lower.endswith(ext) for ext in video_extensions):
            return ("video", True)
        elif any(url_lower.endswith(ext) for ext in image_extensions):
            return ("image", False)
        
        # Default to image if uncertain
        logger.warning(f"[LinkedIn] Could not determine media type for {url}, defaulting to image")
        return ("image", False)
    
    @staticmethod
    def _normalize_url(url: str) -> str:
        """
        Normalize URL - convert relative URLs to full URLs
        Handles Cloudinary URLs and local storage URLs
        """
        parsed = urlparse(url)
        
        # Already has scheme (http/https) - return as is
        if parsed.scheme:
            return url
        
        # Relative URL - need to convert to full URL
        if url.startswith('/storage/'):
            # Local storage path
            if settings.BACKEND_URL:
                base_url = settings.BACKEND_URL.rstrip('/')
                full_url = f"{base_url}{url}"
                logger.debug(f"[LinkedIn] Converted relative storage URL to: {full_url}")
                return full_url
            else:
                raise Exception(
                    f"Invalid storage URL: {url}. "
                    f"BACKEND_URL is not configured. Please set BACKEND_URL in your environment variables."
                )
        else:
            # Other relative URL - prepend BACKEND_URL
            if settings.BACKEND_URL:
                base_url = settings.BACKEND_URL.rstrip('/')
                full_url = f"{base_url}{url}"
                logger.debug(f"[LinkedIn] Converted relative URL to: {full_url}")
                return full_url
            else:
                raise Exception(
                    f"Invalid URL format: {url}. "
                    f"No scheme and BACKEND_URL not configured. Please set BACKEND_URL in your environment variables."
                )
    
    @staticmethod
    def upload_media(token: str, entity_urn: str, media_urls: List[str]) -> Tuple[List[Dict], Optional[str]]:
        """
        Upload images or videos to LinkedIn
        
        Args:
            token: LinkedIn access token
            entity_urn: LinkedIn entity URN (person or organization)
            media_urls: List of media URLs (images or videos)
        
        Returns:
            Tuple of (assets, error)
            assets: List of asset dictionaries
            error: Error message if upload failed, None if successful
        """
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }
        
        assets = []
        
        for url in media_urls:
            try:
                # Normalize URL (handle relative URLs and Cloudinary)
                normalized_url = LinkedInPostingService._normalize_url(url)
                logger.info(f"[LinkedIn] Processing media URL: {normalized_url[:100]}...")
                
                # Step 1: Download media to detect type
                media_resp = requests.get(normalized_url, timeout=30)
                if media_resp.status_code != 200:
                    error_msg = f"Failed to download media from {normalized_url}: HTTP {media_resp.status_code}"
                    logger.error(f"[LinkedIn] {error_msg}")
                    return None, error_msg
                
                content_type = media_resp.headers.get('Content-Type', '')
                media_type, is_video = LinkedInPostingService._detect_media_type(normalized_url, content_type)
                
                logger.info(f"[LinkedIn] Detected media type: {media_type} (is_video: {is_video}), content-type: {content_type}")
                
                # Step 2: Register upload with LinkedIn
                register_url = f"{LINKEDIN_API_URL}/assets?action=registerUpload"
                
                # Use appropriate recipe based on media type
                if is_video:
                    recipe = "urn:li:digitalmediaRecipe:feedshare-video"
                else:
                    recipe = "urn:li:digitalmediaRecipe:feedshare-image"
                
                register_payload = {
                    "registerUploadRequest": {
                        "owner": entity_urn,
                        "recipes": [recipe],
                        "serviceRelationships": [
                            {
                                "relationshipType": "OWNER",
                                "identifier": "urn:li:userGeneratedContent",
                            }
                        ],
                    }
                }
                
                logger.debug(f"[LinkedIn] Registering upload with recipe: {recipe}")
                register_response = requests.post(
                    register_url, json=register_payload, headers=headers, timeout=30
                )
                
                if register_response.status_code != 200:
                    error_msg = f"Register upload failed: {register_response.status_code} - {register_response.text}"
                    logger.error(f"[LinkedIn] {error_msg}")
                    return None, error_msg
                
                register_data = register_response.json()
                
                # Extract upload URL and asset
                upload_mechanism = register_data.get("value", {}).get("uploadMechanism", {})
                upload_url = upload_mechanism.get(
                    "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest", {}
                ).get("uploadUrl")
                
                asset = register_data.get("value", {}).get("asset")
                
                if not upload_url or not asset:
                    error_msg = f"Invalid register response: missing uploadUrl or asset. Response: {register_data}"
                    logger.error(f"[LinkedIn] {error_msg}")
                    return None, error_msg
                
                logger.debug(f"[LinkedIn] Got upload URL and asset. Uploading {media_type}...")
                
                # Step 3: Upload the media to LinkedIn
                media_data = BytesIO(media_resp.content)
                upload_headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": content_type or ("video/mp4" if is_video else "image/jpeg"),
                }
                
                upload_resp = requests.put(
                    upload_url, 
                    headers=upload_headers, 
                    data=media_data,
                    timeout=120  # Longer timeout for videos
                )
                
                if upload_resp.status_code not in [200, 201]:
                    error_msg = f"Media upload failed for {normalized_url}: {upload_resp.status_code} - {upload_resp.text}"
                    logger.error(f"[LinkedIn] {error_msg}")
                    return None, error_msg
                
                logger.info(f"[LinkedIn] ✓ Successfully uploaded {media_type}: {normalized_url[:100]}...")
                assets.append(asset)
                
            except Exception as e:
                error_msg = f"Error processing media URL {url}: {str(e)}"
                logger.error(f"[LinkedIn] {error_msg}", exc_info=True)
                return None, error_msg
        
        return assets, None
    
    @staticmethod
    def post(
        content: str,
        access_token: str,
        entity_id: str,
        is_organization: bool = False,
        media_urls: Optional[List[str]] = None
    ) -> Dict:
        """
        Post content (optionally with image or video) to LinkedIn
        
        Args:
            content: Post text content
            access_token: LinkedIn access token
            entity_id: LinkedIn person or organization ID
            is_organization: Whether posting as organization
            media_urls: Optional list of media URLs (images or videos)
        
        Returns:
            Dict with success status and post details
        """
        try:
            entity_urn = (
                f"urn:li:organization:{entity_id}"
                if is_organization
                else f"urn:li:person:{entity_id}"
            )
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0",
            }
            
            media = []
            share_media_category = "NONE"
            
            if media_urls:
                logger.info(f"[LinkedIn] Uploading {len(media_urls)} media file(s)...")
                assets, error = LinkedInPostingService.upload_media(access_token, entity_urn, media_urls)
                if error:
                    logger.error(f"[LinkedIn] Media upload failed: {error}")
                    return {"success": False, "error": error}
                
                if not assets:
                    logger.warning(f"[LinkedIn] No assets returned from upload")
                    return {"success": False, "error": "Media upload returned no assets"}
                
                # Determine media category based on uploaded assets
                # Check if any are videos by looking at the first URL
                if media_urls:
                    _, is_video = LinkedInPostingService._detect_media_type(media_urls[0])
                    share_media_category = "VIDEO" if is_video else "IMAGE"
                
                for asset in assets:
                    media.append(
                        {
                            "status": "READY",
                            "description": {"text": "Media attachment"},
                            "media": asset,
                            "title": {"text": "Attached Media"},
                        }
                    )
                
                logger.info(f"[LinkedIn] Prepared {len(media)} media asset(s), category: {share_media_category}")
            
            # Build post payload
            post_url = f"{LINKEDIN_API_URL}/ugcPosts"
            payload = {
                "author": entity_urn,
                "lifecycleState": "PUBLISHED",
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary": {"text": content},
                        "shareMediaCategory": share_media_category,
                    }
                },
                "visibility": {
                    "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
                },
            }
            
            # Add media only if we have media
            if media:
                payload["specificContent"]["com.linkedin.ugc.ShareContent"]["media"] = media
            
            logger.info(f"[LinkedIn] Posting to {post_url}")
            logger.debug(f"[LinkedIn] Entity URN: {entity_urn}")
            logger.debug(f"[LinkedIn] Content length: {len(content)}")
            logger.debug(f"[LinkedIn] Media category: {share_media_category}")
            logger.debug(f"[LinkedIn] Media count: {len(media)}")
            logger.debug(f"[LinkedIn] Payload: {payload}")
            
            resp = requests.post(post_url, json=payload, headers=headers, timeout=60)
            logger.info(f"[LinkedIn] Response status: {resp.status_code}")
            logger.debug(f"[LinkedIn] Response headers: {dict(resp.headers)}")
            logger.debug(f"[LinkedIn] Response body: {resp.text[:1000]}")
            
            if resp.status_code in [200, 201]:
                try:
                    response_data = resp.json()
                    post_urn = response_data.get("id")
                    
                    if post_urn:
                        logger.info(f"[LinkedIn] ✓ Post successful! Post URN: {post_urn}")
                        return {
                            "success": True,
                            "post_id": post_urn,
                        }
                    else:
                        # Response is 200/201 but no post_id
                        logger.warning(f"[LinkedIn] Post returned {resp.status_code} but no post_id. Response: {response_data}")
                        
                        # Check if there's an error in the response
                        if "error" in response_data or "message" in response_data:
                            error_msg = response_data.get("message") or response_data.get("error")
                            logger.error(f"[LinkedIn] Post failed: {error_msg}")
                            return {"success": False, "error": error_msg}
                        
                        # Check for LinkedIn-specific error format
                        if "serviceErrorCode" in response_data:
                            error_msg = response_data.get("message", "Unknown LinkedIn API error")
                            logger.error(f"[LinkedIn] LinkedIn API error: {error_msg}")
                            return {"success": False, "error": error_msg}
                        
                        # Still return success but log warning
                        return {
                            "success": True,
                            "post_id": None,
                            "warning": "Post created but no post_id returned. Check LinkedIn to verify."
                        }
                except (ValueError, KeyError) as parse_error:
                    logger.error(f"[LinkedIn] Failed to parse response JSON: {str(parse_error)}")
                    logger.error(f"[LinkedIn] Response text: {resp.text[:1000]}")
                    return {"success": False, "error": f"Failed to parse response: {str(parse_error)}"}
            
            # Non-200/201 status code
            error_text = resp.text
            logger.error(f"[LinkedIn] Post failed with status {resp.status_code}: {error_text}")
            logger.debug(f"[LinkedIn] Request payload: {payload}")
            logger.debug(f"[LinkedIn] Request headers: {dict(headers)}")
            
            # Try to extract error message from JSON response
            try:
                error_json = resp.json()
                error_msg = (
                    error_json.get("message") 
                    or error_json.get("error") 
                    or error_json.get("serviceErrorCode")
                    or error_text
                )
            except (ValueError, KeyError):
                error_msg = error_text
            
            return {"success": False, "error": error_msg}
            
        except Exception as e:
            logger.error(f"[LinkedIn] Exception in post: {str(e)}", exc_info=True)
            return {"success": False, "error": f"LinkedIn posting exception: {str(e)}"}
