"""
Facebook posting service
"""
import requests
import time
import logging
from typing import Dict, List, Optional
from app.utils.logger import logger


class FacebookPostingService:
    """Service for posting to Facebook Pages"""
    
    @staticmethod
    def post(
        content: str,
        access_token: str,
        page_id: str,
        media_urls: Optional[List[str]] = None,
        is_personal_account: bool = False  # DEPRECATED: kept for backward compatibility, always ignored
    ) -> Dict:
        """
        Post content to a Facebook Page.
        
        NOTE: Facebook deprecated personal account posting via API (publish_actions permission).
        Only Facebook Pages can post via Graph API.
        
        Args:
            content: Post text content
            access_token: Facebook Page access token
            page_id: Facebook Page ID
            media_urls: Optional list of media URLs
            is_personal_account: DEPRECATED - ignored, only Pages are supported
        
        Returns:
            Dict with success status and post details
        """
        try:
            # Always use page_id - personal account posting is not supported by Facebook API
            logger.info(f"[Facebook] Starting post - page_id: {page_id}, content_length: {len(content)}, has_media: {bool(media_urls)}")
            base_url = f"https://graph.facebook.com/v19.0/{page_id}"
            
            # No media - text only post
            if not media_urls:
                logger.info(f"[Facebook] Posting text-only post to {base_url}")
                return FacebookPostingService._post_text(base_url, access_token, content)
            
            # Filter valid image URLs
            image_urls = [
                url for url in media_urls 
                if any(url.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp'])
            ]
            
            # Filter valid video URLs  
            video_urls = [
                url for url in media_urls
                if any(url.lower().endswith(ext) for ext in ['.mp4', '.mov', '.avi', '.mkv'])
            ]
            
            # Single image
            if len(image_urls) == 1 and len(video_urls) == 0:
                return FacebookPostingService._post_single_photo(base_url, access_token, content, image_urls[0])
            
            # Single video
            elif len(video_urls) == 1 and len(image_urls) == 0:
                return FacebookPostingService._post_single_video(base_url, access_token, content, video_urls[0])
            
            # Multiple images (carousel/album)
            elif len(image_urls) > 1:
                return FacebookPostingService._post_photo_album(base_url, access_token, content, image_urls)
            
            # Mixed media or unsupported - fall back to text
            else:
                logger.warning(f"Unsupported media combination, posting as text only")
                return FacebookPostingService._post_text(base_url, access_token, content)
                
        except Exception as e:
            logger.error(f"Facebook posting error: {str(e)}")
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def _post_text(base_url: str, access_token: str, content: str) -> Dict:
        """Post text-only content to Facebook"""
        try:
            url = f"{base_url}/feed"
            data = {
                "message": content,
                "access_token": access_token
            }
            
            logger.info(f"[Facebook] Posting text to {url}, content_length: {len(content)}")
            response = requests.post(url, data=data)
            result = response.json()
            logger.info(f"[Facebook] Response status: {response.status_code}")
            
            if response.status_code in [200, 201] and "id" in result:
                logger.info(f"[Facebook] Post successful, post_id: {result['id']}")
                return {
                    "success": True, 
                    "post_id": result["id"],
                    "post_type": "text"
                }
            else:
                logger.error(f"[Facebook] Post failed: {result}")
                return {"success": False, "error": result}
                
        except Exception as e:
            logger.error(f"[Facebook] Exception in _post_text: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def _post_single_photo(base_url: str, access_token: str, content: str, image_url: str) -> Dict:
        """Post single photo to Facebook"""
        try:
            url = f"{base_url}/photos"
            data = {
                "url": image_url,
                "caption": content,
                "access_token": access_token,
                "published": "true",
            }
            
            logger.info(f"[Facebook] Posting photo to {url}, image_url: {image_url[:50]}..., caption_length: {len(content)}")
            response = requests.post(url, data=data)
            result = response.json()
            logger.info(f"[Facebook] Response status: {response.status_code}")
            
            if response.status_code in [200, 201] and "id" in result:
                logger.info(f"[Facebook] Photo post successful, post_id: {result['id']}")
                return {
                    "success": True, 
                    "post_id": result["id"],
                    "post_type": "single_photo"
                }
            else:
                logger.error(f"[Facebook] Photo post failed: {result}")
                return {"success": False, "error": result}
                
        except Exception as e:
            logger.error(f"[Facebook] Exception in _post_single_photo: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def _post_single_video(base_url: str, access_token: str, content: str, video_url: str) -> Dict:
        """Post single video to Facebook"""
        try:
            logger.info(f"[Facebook] Posting video to {base_url}/videos, video_url: {video_url[:50]}..., caption_length: {len(content)}")
            url = f"{base_url}/videos"
            data = {
                "file_url": video_url,
                "description": content,
                "access_token": access_token,
                "published": "true",
            }
            
            response = requests.post(url, data=data)
            result = response.json()
            logger.info(f"[Facebook] Video post response status: {response.status_code}")
            
            if response.status_code in [200, 201] and "id" in result:
                logger.info(f"[Facebook] Video post successful, post_id: {result['id']}")
                return {
                    "success": True, 
                    "post_id": result["id"],
                    "post_type": "single_video"
                }
            else:
                logger.error(f"[Facebook] Video post failed: {result}")
                return {"success": False, "error": result}
                
        except Exception as e:
            logger.error(f"[Facebook] Exception in _post_single_video: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def _post_photo_album(base_url: str, access_token: str, content: str, image_urls: List[str]) -> Dict:
        """Create Facebook photo album with multiple images"""
        try:
            # Step 1: Create album
            album_url = f"{base_url}/albums"
            album_data = {
                "name": f"Album {int(time.time())}",
                "message": content,
                "access_token": access_token,
            }
            
            logger.info(f"[Facebook] Creating photo album with {len(image_urls)} images...")
            album_response = requests.post(album_url, data=album_data)
            album_result = album_response.json()
            logger.info(f"[Facebook] Album creation response status: {album_response.status_code}")
            
            if "id" not in album_result:
                logger.error(f"[Facebook] Failed to create album: {album_result}")
                return {"success": False, "error": f"Failed to create album: {album_result}"}
            
            album_id = album_result["id"]
            logger.info(f"[Facebook] Album created, album_id: {album_id}")
            
            # Step 2: Add photos to album
            photo_ids = []
            for idx, image_url in enumerate(image_urls[:50], 1):  # Facebook limit
                photo_data = {
                    "url": image_url,
                    "access_token": access_token,
                }
                
                logger.debug(f"[Facebook] Adding photo {idx}/{len(image_urls)} to album...")
                photo_response = requests.post(f"{base_url}/{album_id}/photos", data=photo_data)
                photo_result = photo_response.json()
                
                if "id" in photo_result:
                    photo_ids.append(photo_result["id"])
                    logger.debug(f"[Facebook] Photo {idx} added successfully")
                else:
                    logger.warning(f"[Facebook] Failed to add photo {idx} ({image_url[:50]}...): {photo_result}")
            
            if photo_ids:
                logger.info(f"[Facebook] Photo album created successfully with {len(photo_ids)} photos, album_id: {album_id}")
                return {
                    "success": True, 
                    "post_id": album_id,
                    "photo_ids": photo_ids,
                    "post_type": "photo_album",
                    "photo_count": len(photo_ids)
                }
            else:
                logger.error(f"[Facebook] Failed to add any photos to album {album_id}")
                return {"success": False, "error": "Failed to add any photos to album"}
                
        except Exception as e:
            logger.error(f"[Facebook] Exception in _post_photo_album: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}

