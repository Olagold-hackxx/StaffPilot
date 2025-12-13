"""
Local filesystem storage (for development)
"""
import os
import aiofiles
from pathlib import Path
from typing import BinaryIO
from app.services.storage.base import StorageBackend
from app.utils.errors import StorageError


class LocalStorage(StorageBackend):
    """Local filesystem storage (for development)"""
    
    def __init__(self, base_path: str = "./storage"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    async def upload(
        self, 
        key: str, 
        file: BinaryIO, 
        content_type: str
    ) -> str:
        """Upload file to local storage"""
        try:
            file_path = self.base_path / key
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Get content from file object
            # For BytesIO, use getvalue() to get all bytes
            # For other file-like objects, use read()
            if hasattr(file, 'getvalue'):
                # BytesIO object - use getvalue() to get all bytes
                content = file.getvalue()
            else:
                # Regular file-like object - ensure pointer is at beginning
                if hasattr(file, 'seek'):
                    file.seek(0)
                # Read all content
                content = file.read()
                # If read() returns empty or None, try reading in chunks
                if not content:
                    chunks = []
                    while True:
                        chunk = file.read(8192)  # Read 8KB chunks
                        if not chunk:
                            break
                        chunks.append(chunk)
                    content = b''.join(chunks) if chunks else b''
            
            # Ensure content is bytes, not string
            if isinstance(content, str):
                content = content.encode('utf-8')
            elif not isinstance(content, bytes):
                content = bytes(content)
            
            # Validate PNG files have correct header (for debugging)
            if content_type == "image/png" and len(content) > 8:
                png_header = b'\x89PNG\r\n\x1a\n'
                if not content.startswith(png_header):
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"PNG file {key} doesn't start with PNG magic bytes. First 8 bytes: {content[:8].hex()}")
            
            # Write binary content to file
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(content)
            
            return f"/storage/{key}"
        except Exception as e:
            raise StorageError(f"Failed to upload file: {str(e)}")
    
    async def download(self, key: str) -> bytes:
        """Download file from local storage"""
        try:
            file_path = self.base_path / key
            if not file_path.exists():
                raise StorageError(f"File not found: {key}")
            
            async with aiofiles.open(file_path, 'rb') as f:
                return await f.read()
        except Exception as e:
            raise StorageError(f"Failed to download file: {str(e)}")
    
    async def delete(self, key: str) -> bool:
        """Delete file from local storage"""
        try:
            file_path = self.base_path / key
            if file_path.exists():
                file_path.unlink()
                return True
            return False
        except Exception as e:
            raise StorageError(f"Failed to delete file: {str(e)}")
    
    async def exists(self, key: str) -> bool:
        """Check if file exists"""
        file_path = self.base_path / key
        return file_path.exists()
    
    async def get_url(self, key: str, expires_in: int = 3600) -> str:
        """Get file URL (for local, just return the path)"""
        return f"/storage/{key}"

