"""
Google Drive Integration Service
Handles OAuth flow and file operations for importing brand assets
"""
import json
import base64
from typing import Optional, Dict, List, Any
from datetime import datetime, timezone, timedelta

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io

from app.config import settings
from app.utils.logger import logger


class GoogleDriveService:
    """Service for Google Drive OAuth and file operations"""
    
    SCOPES = [
        'https://www.googleapis.com/auth/drive.readonly',
        'https://www.googleapis.com/auth/drive.metadata.readonly'
    ]
    
    # Supported MIME types for brand assets
    SUPPORTED_IMAGE_TYPES = [
        'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/svg+xml'
    ]
    SUPPORTED_VIDEO_TYPES = [
        'video/mp4', 'video/quicktime', 'video/x-msvideo', 'video/webm'
    ]
    
    def __init__(self, tenant_id: str, tokens: Optional[Dict[str, Any]] = None):
        """
        Initialize Google Drive service
        
        Args:
            tenant_id: Tenant UUID string
            tokens: OAuth tokens dict with access_token, refresh_token, etc.
        """
        self.tenant_id = tenant_id
        self.tokens = tokens
        self._service = None
        self._credentials = None
        
    @property
    def is_connected(self) -> bool:
        """Check if valid tokens exist"""
        return self.tokens is not None and 'refresh_token' in self.tokens
    
    def get_auth_url(self, redirect_uri: str, state: Optional[str] = None) -> str:
        """
        Generate OAuth authorization URL
        
        Args:
            redirect_uri: OAuth callback URL
            state: Optional state parameter for CSRF protection
            
        Returns:
            Authorization URL string
        """
        client_config = {
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri]
            }
        }
        
        flow = Flow.from_client_config(
            client_config,
            scopes=self.SCOPES,
            redirect_uri=redirect_uri
        )
        
        auth_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent',
            state=state or self.tenant_id
        )
        
        return auth_url
    
    def exchange_code(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        """
        Exchange authorization code for tokens
        
        Args:
            code: Authorization code from OAuth callback
            redirect_uri: Same redirect URI used in auth request
            
        Returns:
            Token dictionary with access_token, refresh_token, etc.
        """
        client_config = {
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri]
            }
        }
        
        flow = Flow.from_client_config(
            client_config,
            scopes=self.SCOPES,
            redirect_uri=redirect_uri
        )
        
        flow.fetch_token(code=code)
        credentials = flow.credentials
        
        tokens = {
            'access_token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': list(credentials.scopes) if credentials.scopes else self.SCOPES,
            'expiry': credentials.expiry.isoformat() if credentials.expiry else None,
            'connected_at': datetime.now(timezone.utc).isoformat()
        }
        
        self.tokens = tokens
        return tokens
    
    def _get_credentials(self) -> Credentials:
        """Get or refresh OAuth credentials"""
        if not self.tokens:
            raise ValueError("No tokens available. Connect Google Drive first.")
        
        if self._credentials and self._credentials.valid:
            return self._credentials
        
        self._credentials = Credentials(
            token=self.tokens.get('access_token'),
            refresh_token=self.tokens.get('refresh_token'),
            token_uri=self.tokens.get('token_uri', 'https://oauth2.googleapis.com/token'),
            client_id=self.tokens.get('client_id', settings.GOOGLE_CLIENT_ID),
            client_secret=self.tokens.get('client_secret', settings.GOOGLE_CLIENT_SECRET),
            scopes=self.tokens.get('scopes', self.SCOPES)
        )
        
        return self._credentials
    
    def _get_service(self):
        """Get or create Drive API service"""
        if self._service:
            return self._service
        
        credentials = self._get_credentials()
        self._service = build('drive', 'v3', credentials=credentials)
        return self._service
    
    def list_files(
        self,
        folder_id: Optional[str] = None,
        page_token: Optional[str] = None,
        page_size: int = 50
    ) -> Dict[str, Any]:
        """
        List files in Google Drive (images and videos only)
        
        Args:
            folder_id: Optional folder ID to list contents of (None = root)
            page_token: Pagination token for next page
            page_size: Number of files per page
            
        Returns:
            Dict with files list and nextPageToken
        """
        service = self._get_service()
        
        # Build query for images and videos
        mime_types = self.SUPPORTED_IMAGE_TYPES + self.SUPPORTED_VIDEO_TYPES
        mime_query = " or ".join([f"mimeType='{mt}'" for mt in mime_types])
        
        # Include folders for navigation
        folder_query = "mimeType='application/vnd.google-apps.folder'"
        
        query = f"({mime_query} or {folder_query}) and trashed=false"
        
        if folder_id:
            query += f" and '{folder_id}' in parents"
        else:
            query += " and 'root' in parents"
        
        result = service.files().list(
            q=query,
            pageSize=page_size,
            pageToken=page_token,
            fields="nextPageToken, files(id, name, mimeType, size, thumbnailLink, createdTime, modifiedTime, parents)",
            orderBy="folder,name"
        ).execute()
        
        files = []
        for f in result.get('files', []):
            is_folder = f.get('mimeType') == 'application/vnd.google-apps.folder'
            file_type = 'folder' if is_folder else ('video' if f.get('mimeType', '').startswith('video/') else 'image')
            
            files.append({
                'id': f.get('id'),
                'name': f.get('name'),
                'mime_type': f.get('mimeType'),
                'type': file_type,
                'size': int(f.get('size', 0)) if f.get('size') else None,
                'thumbnail_url': f.get('thumbnailLink'),
                'created_at': f.get('createdTime'),
                'modified_at': f.get('modifiedTime'),
                'parent_id': f.get('parents', [None])[0]
            })
        
        return {
            'files': files,
            'next_page_token': result.get('nextPageToken')
        }
    
    def download_file(self, file_id: str) -> tuple[bytes, str, str]:
        """
        Download a file from Google Drive
        
        Args:
            file_id: Google Drive file ID
            
        Returns:
            Tuple of (file_bytes, filename, mime_type)
        """
        service = self._get_service()
        
        # Get file metadata
        file_metadata = service.files().get(
            fileId=file_id,
            fields="name, mimeType, size"
        ).execute()
        
        filename = file_metadata.get('name', 'untitled')
        mime_type = file_metadata.get('mimeType', 'application/octet-stream')
        
        # Download file content
        request = service.files().get_media(fileId=file_id)
        file_buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(file_buffer, request)
        
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                logger.info(f"Download progress: {int(status.progress() * 100)}%")
        
        file_buffer.seek(0)
        file_bytes = file_buffer.read()
        
        logger.info(f"Downloaded file: {filename} ({len(file_bytes)} bytes)")
        
        return file_bytes, filename, mime_type
    
    def get_file_info(self, file_id: str) -> Dict[str, Any]:
        """
        Get metadata for a single file
        
        Args:
            file_id: Google Drive file ID
            
        Returns:
            File metadata dict
        """
        service = self._get_service()
        
        result = service.files().get(
            fileId=file_id,
            fields="id, name, mimeType, size, thumbnailLink, createdTime, modifiedTime"
        ).execute()
        
        is_video = result.get('mimeType', '').startswith('video/')
        
        return {
            'id': result.get('id'),
            'name': result.get('name'),
            'mime_type': result.get('mimeType'),
            'type': 'video' if is_video else 'image',
            'size': int(result.get('size', 0)) if result.get('size') else None,
            'thumbnail_url': result.get('thumbnailLink'),
            'created_at': result.get('createdTime'),
            'modified_at': result.get('modifiedTime')
        }


def create_google_drive_service(tenant_id: str, tokens: Optional[Dict[str, Any]] = None) -> GoogleDriveService:
    """Factory function to create GoogleDriveService"""
    return GoogleDriveService(tenant_id=tenant_id, tokens=tokens)
