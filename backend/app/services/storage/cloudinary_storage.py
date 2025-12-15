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
    import cloudinary.utils
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
            folder = "documents"  # Default folder
            if "tenants/" in key:
                # Extract tenant folder structure
                # Handle both leading slash and no leading slash
                if key.startswith("tenants/"):
                    parts = key.split("tenants/")[1].split("/")
                elif "/tenants/" in key:
                    parts = key.split("/tenants/")[1].split("/")
                else:
                    parts = []
                    
                if len(parts) > 0:
                    folder = f"documents/tenants/{parts[0]}"

            # Helper to check if raw
            is_raw = (
                content_type.startswith("application/") or 
                content_type.startswith("text/") or
                content_type in ["application/pdf", "application/docx", "text/plain", "text/markdown"]
            )
            
            # Generate public_id from key
            # Replace slashes with underscores to flatten structure (optional, but consistent with previous logic)
            normalized_key = key.replace("/", "_")
            
            if is_raw:
                # For raw files, PRESERVE the extension
                public_id = normalized_key
            else:
                # For images/videos, STRIP the extension (Cloudinary adds it based on format)
                if "." in normalized_key:
                    public_id = normalized_key.rsplit(".", 1)[0]
                else:
                    public_id = normalized_key
            
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
        folder: str = "documents",
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
            
            # Determine resource type based on content_type
            is_video = content_type.startswith("video/")
            is_raw = (
                content_type.startswith("application/") or 
                content_type.startswith("text/") or
                content_type in ["application/pdf", "application/docx", "text/plain", "text/markdown"]
            )
            
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
            
            elif is_raw:
                # No strict validation for raw files (PDFs, docs, etc.)
                logger.info(f"✓ Treating as raw file (content_type: {content_type})")
                pass
                
            else:
                # Validate image formats
                if not (file_data.startswith(b'\x89PNG') or 
                        file_data.startswith(b'\xff\xd8\xff') or 
                        file_data.startswith(b'GIF8')):
                    logger.error(f"Invalid image data. First 20 bytes: {file_data[:20].hex()}")
                    # Fallback: if it's not a standard image but we're here, maybe it should have been raw?
                    # For now, restrict strictly to images if not identified as raw.
                    raise ValueError("Invalid image format. Expected PNG, JPEG, or GIF.")
            
            # Upload to Cloudinary
            media_buffer = BytesIO(file_data)
            
            resource_type = "image"
            if is_video:
                resource_type = "video"
            elif is_raw:
                resource_type = "raw"
            
            upload_options = {
                "folder": folder,
                "resource_type": resource_type,
            }
            
            # Set format and quality for images only
            if not is_video and not is_raw:
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
            
            logger.info(f"✓ Uploaded {resource_type} to Cloudinary: {upload_result['secure_url']}")
            return upload_result["secure_url"]
            
        except Exception as e:
            logger.error(f"Cloudinary upload failed: {str(e)}")
            raise StorageError(f"Failed to upload: {str(e)}")
    
    def upload_sync(
        self, 
        key: str, 
        file: BinaryIO, 
        content_type: str
    ) -> str:
        """
        Upload file to Cloudinary synchronously - for Celery workers.
        
        Args:
            key: Storage key/path for the file
            file: Binary file data
            content_type: MIME type of the file
        
        Returns:
            Public URL of the uploaded file
        """
        try:
            # Extract file data from BinaryIO
            file.seek(0)
            if hasattr(file, 'getvalue'):
                file_data = file.getvalue()
            else:
                file_data = file.read()
            
            if not isinstance(file_data, bytes):
                file_data = bytes(file_data)
            
            # Determine folder from key
            folder = "documents"
            if "tenants/" in key:
                if key.startswith("tenants/"):
                    parts = key.split("tenants/")[1].split("/")
                elif "/tenants/" in key:
                    parts = key.split("/tenants/")[1].split("/")
                else:
                    parts = []
                if len(parts) > 0:
                    folder = f"documents/tenants/{parts[0]}"
            
            # Determine resource type
            is_video = content_type.startswith("video/")
            is_raw = (
                content_type.startswith("application/") or 
                content_type.startswith("text/")
            )
            
            resource_type = "image"
            if is_video:
                resource_type = "video"
            elif is_raw:
                resource_type = "raw"
            
            # Generate public_id
            normalized_key = key.replace("/", "_")
            if is_raw:
                public_id = normalized_key
            else:
                if "." in normalized_key:
                    public_id = normalized_key.rsplit(".", 1)[0]
                else:
                    public_id = normalized_key
            
            # Upload options
            upload_options = {
                "folder": folder,
                "resource_type": resource_type,
                "public_id": public_id,
            }
            
            if not is_video and not is_raw:
                upload_options["format"] = "jpg"
                upload_options["quality"] = "auto:good"
            
            # Upload synchronously
            media_buffer = BytesIO(file_data)
            upload_result = cloudinary.uploader.upload(
                media_buffer,
                **upload_options
            )
            
            logger.info(f"[SYNC] Uploaded {resource_type} to Cloudinary: {upload_result['secure_url']}")
            return upload_result["secure_url"]
            
        except Exception as e:
            logger.error(f"[SYNC] Cloudinary upload failed: {str(e)}")
            raise StorageError(f"Failed to upload: {str(e)}")
    
    async def download(self, key: str) -> bytes:
        """Download file from Cloudinary"""
        try:
            import requests
            
            # Cloudinary uses public_id, not full key
            # Extract public_id from key if it's a URL
            if key.startswith("http"):
                # It's already a URL
                # Check if it's a Cloudinary URL that needs signing
                if "res.cloudinary.com" in key and self.cloud_name in key:
                    # Extract public_id and resource_type from URL
                    # URL format: https://res.cloudinary.com/{cloud}/{resource_type}/upload/{version}/{public_id}
                    try:
                        url_parts = key.split("/upload/")
                        if len(url_parts) == 2:
                            # Get resource_type from the first part
                            resource_type = "raw"  # default
                            if "/image/" in url_parts[0]:
                                resource_type = "image"
                            elif "/video/" in url_parts[0]:
                                resource_type = "video"
                            elif "/raw/" in url_parts[0]:
                                resource_type = "raw"
                            
                            # Get public_id (everything after version)
                            after_upload = url_parts[1]
                            # Remove version if present (format: v1234567890/...)
                            if after_upload.startswith("v") and "/" in after_upload:
                                public_id = after_upload.split("/", 1)[1]
                            else:
                                public_id = after_upload
                            
                            logger.info(f"Signing Cloudinary URL - resource_type: {resource_type}, public_id: {public_id}")
                            
                            # Generate signed URL
                            signed_url, options = cloudinary.utils.cloudinary_url(
                                public_id,
                                resource_type=resource_type,
                                sign_url=True,
                                secure=True
                            )
                            
                            logger.info(f"Signed URL: {signed_url}")
                            
                            response = requests.get(signed_url)
                            response.raise_for_status()
                            return response.content
                    except Exception as sign_error:
                        logger.warning(f"Failed to sign Cloudinary URL, trying unsigned: {str(sign_error)}")
                
                # Fallback: try unsigned URL
                response = requests.get(key)
                response.raise_for_status()
                return response.content
            else:
                # It's a storage key, need to derive public_id and construct URL
                # Key format: tenants/{tenant_id}/documents/{doc_id}/{filename}.pdf
                
                # Extract tenant_id from key
                tenant_id = None
                if "tenants/" in key:
                    try:
                        parts = key.split("tenants/")
                        if len(parts) > 1:
                            tenant_id = parts[1].split("/")[0]
                    except IndexError:
                        pass
                
                # Flatten the key to create public_id (replace / with _)
                # Keep the extension for raw files
                flattened_key = key.replace("/", "_")  # e.g., tenants_uuid_documents_uuid_file.pdf
                
                # Also create version without extension  
                if "." in flattened_key:
                    flattened_without_ext = flattened_key.rsplit(".", 1)[0]
                else:
                    flattened_without_ext = flattened_key
                
                # Legacy format (dots replaced with underscores)
                legacy_flat = key.replace("/", "_").replace(".", "_")
                
                logger.info(f"Download key: {key}")
                logger.info(f"Extracted tenant_id: {tenant_id}")
                logger.info(f"Flattened key: {flattened_key}")
                
                # Build list of full public_ids to try (folder/public_id format)
                attempts = []
                
                if tenant_id:
                    # PRIMARY: Current upload format - folder + public_id combined
                    attempts.append(("raw", f"documents/tenants/{tenant_id}/{flattened_key}"))
                    attempts.append(("raw", f"documents/tenants/{tenant_id}/{flattened_without_ext}"))
                
                # Fallback patterns
                attempts.extend([
                    ("raw", f"documents/{flattened_key}"),
                    ("raw", f"documents/{flattened_without_ext}"),
                    ("raw", f"social-media/{flattened_key}"),
                    ("raw", f"social-media/{flattened_without_ext}"),
                    ("raw", f"social-media/{legacy_flat}"),
                    ("raw", flattened_key),
                    ("raw", flattened_without_ext),
                    ("image", flattened_without_ext),
                    ("video", flattened_without_ext),
                ])
                
                for r_type, full_public_id in attempts:
                    try:
                        # Construct URL directly WITHOUT version prefix
                        # Format: https://res.cloudinary.com/{cloud}/{resource_type}/upload/{public_id}
                        # For signed URLs, we need to generate signature manually
                        
                        import hashlib
                        import time
                        
                        # Generate timestamp
                        timestamp = str(int(time.time()))
                        
                        # Generate signature for authenticated delivery
                        to_sign = f"timestamp={timestamp}{self.api_secret}"
                        signature = hashlib.sha1(to_sign.encode()).hexdigest()
                        
                        # Build signed URL
                        url = f"https://res.cloudinary.com/{self.cloud_name}/{r_type}/upload/{full_public_id}"
                        
                        logger.info(f"Trying: {url}")
                        
                        response = requests.get(url)
                        if response.status_code == 200:
                            logger.info(f"✓ SUCCESS: {url}")
                            return response.content
                        else:
                            logger.debug(f"Failed ({response.status_code}): {url}")
                                
                    except Exception as e:
                        logger.debug(f"Error: {str(e)}")
                        continue
                
                # If we get here, none worked
                raise StorageError(f"Could not find file in Cloudinary. Key: {key}")

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

