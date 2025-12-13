"""
Cloudinary storage backend
"""
from typing import BinaryIO, Optional
from io import BytesIO
from app.services.storage.base import StorageBackend
from app.utils.errors import StorageError
from app.utils.logger import logger

try:
    import cloudinary
    import cloudinary.uploader
    import cloudinary.api
    CLOUDINARY_AVAILABLE = True
except ImportError:
    CLOUDINARY_AVAILABLE = False
    logger.warning("cloudinary library not installed. Install with: pip install cloudinary")


class CloudinaryStorage(StorageBackend):
    """Cloudinary storage backend for images and videos"""
    
    def __init__(
        self,
        cloud_name: str,
        api_key: str,
        api_secret: str
    ):
        if not CLOUDINARY_AVAILABLE:
            raise ImportError("cloudinary library not installed. Install with: pip install cloudinary")
        
        cloudinary.config(
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret
        )
        self.cloud_name = cloud_name
        self.api_key = api_key
        self.api_secret = api_secret
    
    async def upload(
        self, 
        key: str, 
        file: BinaryIO, 
        content_type: str
    ) -> str:
        """Upload file to Cloudinary and return public URL"""
        try:
            # Extract file data from BinaryIO
            file.seek(0)
            if hasattr(file, 'getvalue'):
                file_data = file.getvalue()
            else:
                file_data = file.read()
            
            # Ensure file_data is bytes
            if not isinstance(file_data, bytes):
                file_data = bytes(file_data)
            
            # Determine folder from key (extract tenant path if available)
            folder = "social-media"  # Default folder
            if "/tenants/" in key:
                # Extract tenant folder structure
                parts = key.split("/tenants/")[1].split("/")
                if len(parts) > 0:
                    folder = f"tenants/{parts[0]}"
            
            # Generate public_id from key
            public_id = key.replace("/", "_").replace(".", "_")
            if "." in public_id:
                public_id = public_id.rsplit(".", 1)[0]
            
            # Use the improved upload logic
            return await self._upload_bytes(
                file_data=file_data,
                folder=folder,
                public_id=public_id,
                content_type=content_type
            )
            
        except Exception as e:
            logger.error(f"Cloudinary upload failed: {str(e)}", exc_info=True)
            raise StorageError(f"Failed to upload to Cloudinary: {str(e)}")
    
    async def _upload_bytes(
        self,
        file_data: bytes,
        folder: str = "social-media",
        public_id: Optional[str] = None,
        content_type: str = "image/png",
        **kwargs
    ) -> str:
        """Upload binary image or video data to Cloudinary"""
        
        try:
            # Ensure file_data is bytes
            if not isinstance(file_data, bytes):
                if isinstance(file_data, str):
                    # Try to decode as base64 string
                    import base64
                    try:
                        file_data = base64.b64decode(file_data)
                        logger.info("✓ Decoded base64 string before upload")
                    except Exception:
                        # Not base64, convert to bytes
                        file_data = file_data.encode('utf-8')
                else:
                    file_data = bytes(file_data)
            
            # Determine if this is a video or image based on content_type
            is_video = content_type.startswith("video/")
            
            # Validate it's actual media data (not base64)
            # Check if data looks like base64-encoded bytes (starts with base64 magic bytes)
            if file_data.startswith(b'iVBORw0K') or file_data.startswith(b'/9j/'):
                logger.warning("Received data that looks like base64-encoded. Attempting to decode...")
                import base64
                try:
                    file_data = base64.b64decode(file_data)
                    logger.info("✓ Decoded base64 before upload")
                except Exception as decode_error:
                    logger.warning(f"Failed to decode as base64, using as-is: {str(decode_error)}")
            
            # Validate file format based on type
            if is_video:
                # Validate video formats (MP4, MOV, etc.)
                # MP4 files start with ftyp at offset 4: bytes 4-8 should be "ftyp"
                # MOV files also use ftyp
                # WebM starts with "webm" or has "matroska" signature
                is_valid_video = False
                
                if len(file_data) >= 12:
                    # Check for MP4/MOV (ftyp at offset 4)
                    if file_data[4:8] == b'ftyp':
                        is_valid_video = True
                        logger.info("✓ Valid MP4/MOV video detected")
                    # Check for WebM (starts with 1A 45 DF A3)
                    elif file_data[:4] == b'\x1a\x45\xdf\xa3':
                        is_valid_video = True
                        logger.info("✓ Valid WebM video detected")
                    # Check for AVI (RIFF...AVI)
                    elif file_data[:4] == b'RIFF' and b'AVI ' in file_data[8:12]:
                        is_valid_video = True
                        logger.info("✓ Valid AVI video detected")
                
                if not is_valid_video:
                    logger.error(f"Invalid video data. First 20 bytes: {file_data[:20].hex()}")
                    raise ValueError("Invalid video format. Expected MP4, MOV, WebM, or AVI.")
            else:
                # Validate image formats
                if not (file_data.startswith(b'\x89PNG') or 
                        file_data.startswith(b'\xff\xd8\xff') or 
                        file_data.startswith(b'GIF8')):
                    logger.error(f"Invalid image data. First 20 bytes: {file_data[:20].hex()}")
                    raise ValueError("Invalid image format. Expected PNG, JPEG, or GIF.")
            
            # Upload to Cloudinary
            media_buffer = BytesIO(file_data)
            
            upload_options = {
                "folder": folder,
                "resource_type": "video" if is_video else "image",
            }
            
            # Set format and quality for images only
            if not is_video:
                upload_options["format"] = "jpg"
                upload_options["quality"] = "auto:good"
            
            if public_id:
                upload_options["public_id"] = public_id
            
            # Merge any additional kwargs
            upload_options.update(kwargs)
            
            upload_result = cloudinary.uploader.upload(
                media_buffer,
                **upload_options
            )
            
            logger.info(f"✓ Uploaded {'video' if is_video else 'image'} to Cloudinary: {upload_result['secure_url']}")
            return upload_result["secure_url"]
            
        except Exception as e:
            logger.error(f"Cloudinary upload failed: {str(e)}")
            raise StorageError(f"Failed to upload: {str(e)}")
    
    async def download(self, key: str) -> bytes:
        """Download file from Cloudinary"""
        try:
            # Cloudinary uses public_id, not full key
            # Extract public_id from key if it's a URL
            if key.startswith("http"):
                # It's already a URL, download it
                import requests
                response = requests.get(key)
                response.raise_for_status()
                return response.content
            else:
                # It's a public_id, construct URL and download
                import requests
                url = f"https://res.cloudinary.com/{self.cloud_name}/image/upload/{key}"
                response = requests.get(url)
                response.raise_for_status()
                return response.content
        except Exception as e:
            raise StorageError(f"Failed to download from Cloudinary: {str(e)}")
    
    async def delete(self, key: str) -> bool:
        """Delete file from Cloudinary"""
        try:
            # Extract public_id from key or URL
            if key.startswith("http"):
                # Extract public_id from Cloudinary URL
                # Format: https://res.cloudinary.com/{cloud_name}/{resource_type}/upload/{public_id}.{ext}
                parts = key.split("/upload/")
                if len(parts) > 1:
                    public_id_with_ext = parts[1].split("?")[0]  # Remove query params
                    public_id = public_id_with_ext.rsplit(".", 1)[0]  # Remove extension
                else:
                    logger.warning(f"Could not extract public_id from Cloudinary URL: {key}")
                    return False
            else:
                public_id = key
            
            # Delete from Cloudinary
            result = cloudinary.uploader.destroy(public_id)
            if result.get("result") == "ok":
                return True
            else:
                logger.warning(f"Cloudinary delete returned: {result}")
                return False
        except Exception as e:
            logger.error(f"Cloudinary delete failed: {str(e)}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if file exists in Cloudinary"""
        try:
            # Extract public_id from key or URL
            if key.startswith("http"):
                parts = key.split("/upload/")
                if len(parts) > 1:
                    public_id_with_ext = parts[1].split("?")[0]
                    public_id = public_id_with_ext.rsplit(".", 1)[0]
                else:
                    return False
            else:
                public_id = key
            
            # Try to get resource info
            result = cloudinary.api.resource(public_id)
            return result is not None
        except Exception:
            return False
    
    async def get_url(self, key: str, expires_in: int = 3600) -> str:
        """Get Cloudinary URL (already public URLs, no signing needed)"""
        # If key is already a URL, return it
        if key.startswith("http"):
            return key
        
        # Otherwise construct URL from public_id
        return f"https://res.cloudinary.com/{self.cloud_name}/image/upload/{key}"

