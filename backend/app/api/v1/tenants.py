"""
Tenant API routes
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from uuid import UUID
from app.db.session import get_db
from app.dependencies import get_current_user, get_current_tenant
from app.models.user import User
from app.models.tenant import Tenant
from app.schemas.tenant import TenantCreate, TenantUpdate, TenantResponse, TenantListResponse
from app.services.tenant_service import TenantService

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.post("", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    tenant_data: TenantCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new tenant"""
    service = TenantService(db)
    tenant = await service.create_tenant(
        name=tenant_data.name,
        slug=tenant_data.slug,
        domain=tenant_data.domain,
        brand_voice=tenant_data.brand_voice,
        target_audience=tenant_data.target_audience,
        offerings=tenant_data.offerings
    )
    return tenant


@router.get("/me", response_model=TenantResponse)
async def get_my_tenant(
    current_tenant: Tenant = Depends(get_current_tenant)
):
    """Get current user's tenant"""
    return current_tenant


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get tenant by ID"""
    service = TenantService(db)
    tenant = await service.get_tenant(tenant_id)
    
    # Ensure user belongs to tenant
    if current_user.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    return tenant


@router.patch("/me", response_model=TenantResponse)
async def update_my_tenant(
    tenant_data: TenantUpdate,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """Update current tenant"""
    service = TenantService(db)
    update_data = tenant_data.model_dump(exclude_unset=True)
    tenant = await service.update_tenant(
        tenant_id=current_tenant.id,
        **update_data
    )
    return tenant


@router.get("", response_model=TenantListResponse)
async def list_tenants(
    limit: int = 50,
    offset: int = 0,
    is_active: bool = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List tenants (admin only - placeholder)"""
    # TODO: Add admin check
    service = TenantService(db)
    tenants, total = await service.list_tenants(
        limit=limit,
        offset=offset,
        is_active=is_active
    )
    return TenantListResponse(tenants=tenants, total=total)


# =====================
# Tenant Brand Assets API
# =====================

from fastapi import UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional
from app.utils.logger import logger


class TenantBrandAssetResponse(BaseModel):
    """Response schema for tenant brand asset"""
    id: str
    name: str
    description: Optional[str]
    asset_type: str
    source: str
    url: str
    thumbnail_url: Optional[str]
    file_name: Optional[str]
    file_size: Optional[int]
    mime_type: Optional[str]
    width: Optional[int]
    height: Optional[int]
    usage_count: int
    created_at: str


class TenantBrandAssetListResponse(BaseModel):
    """Response schema for list of tenant brand assets"""
    assets: List[TenantBrandAssetResponse]
    total: int


class GenerateVideoRequest(BaseModel):
    """Request to generate video with brand assets for content"""
    prompt: str
    duration: int = 15  # Target duration in seconds (8-60)
    brand_asset_ids: Optional[List[str]] = None  # IDs of brand assets to use as references


class GenerateVideoResponse(BaseModel):
    """Response for content video generation"""
    task_id: str
    status: str
    message: str


@router.get("/me/brand-assets", response_model=TenantBrandAssetListResponse)
async def list_tenant_brand_assets(
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    List all brand assets for the current tenant.
    These assets can be used across all campaigns and content generation.
    """
    try:
        from app.models.brand_asset import BrandAsset
        from sqlalchemy import select
        
        # Get tenant-wide brand assets (not tied to any campaign)
        query = select(BrandAsset).where(
            BrandAsset.tenant_id == current_tenant.id,
            BrandAsset.is_active == True
        ).order_by(BrandAsset.created_at.desc())
        
        result = await db.execute(query)
        assets = result.scalars().all()
        
        return TenantBrandAssetListResponse(
            assets=[
                TenantBrandAssetResponse(
                    id=str(a.id),
                    name=a.name,
                    description=a.description,
                    asset_type=a.asset_type,
                    source=a.source,
                    url=a.url,
                    thumbnail_url=a.thumbnail_url,
                    file_name=a.file_name,
                    file_size=a.file_size,
                    mime_type=a.mime_type,
                    width=a.width,
                    height=a.height,
                    usage_count=a.usage_count or 0,
                    created_at=a.created_at.isoformat() if a.created_at else ""
                )
                for a in assets
            ],
            total=len(assets)
        )
        
    except Exception as e:
        logger.error(f"Error listing tenant brand assets: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list brand assets: {str(e)}"
        )


@router.post("/me/brand-assets", response_model=TenantBrandAssetResponse)
async def upload_tenant_brand_asset(
    file: UploadFile = File(...),
    name: str = Form(...),
    description: Optional[str] = Form(None),
    current_tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload a brand asset for the tenant (not tied to any campaign).
    Can be used across all content generation.
    """
    try:
        from app.models.brand_asset import BrandAsset
        from app.services.storage import get_storage
        from io import BytesIO
        import uuid as uuid_lib
        
        # Validate file type
        content_type = file.content_type or ""
        if content_type.startswith("image/"):
            asset_type = "image"
        elif content_type.startswith("video/"):
            asset_type = "video"
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid file type. Only images and videos are allowed."
            )
        
        # Read file content
        file_content = await file.read()
        file_size = len(file_content)
        
        # Upload to storage
        storage = get_storage()
        file_ext = file.filename.split(".")[-1] if file.filename and "." in file.filename else "bin"
        storage_key = f"tenants/{current_tenant.id}/brand-assets/{uuid_lib.uuid4()}.{file_ext}"
        
        file_bytes = BytesIO(file_content)
        url = await storage.upload(key=storage_key, file=file_bytes, content_type=content_type)
        
        # Get image dimensions if applicable
        width = None
        height = None
        if asset_type == "image":
            try:
                from PIL import Image
                img = Image.open(BytesIO(file_content))
                width, height = img.size
            except:
                pass
        
        # Create brand asset record (not tied to any campaign)
        brand_asset = BrandAsset(
            tenant_id=current_tenant.id,
            campaign_id=None,  # Tenant-wide, not campaign-specific
            name=name,
            description=description,
            asset_type=asset_type,
            source="upload",
            url=url,
            file_name=file.filename,
            file_size=file_size,
            mime_type=content_type,
            width=width,
            height=height,
            created_by=current_user.id
        )
        
        db.add(brand_asset)
        await db.commit()
        await db.refresh(brand_asset)
        
        logger.info(f"Uploaded tenant brand asset {brand_asset.id}")
        
        return TenantBrandAssetResponse(
            id=str(brand_asset.id),
            name=brand_asset.name,
            description=brand_asset.description,
            asset_type=brand_asset.asset_type,
            source=brand_asset.source,
            url=brand_asset.url,
            thumbnail_url=brand_asset.thumbnail_url,
            file_name=brand_asset.file_name,
            file_size=brand_asset.file_size,
            mime_type=brand_asset.mime_type,
            width=brand_asset.width,
            height=brand_asset.height,
            usage_count=brand_asset.usage_count or 0,
            created_at=brand_asset.created_at.isoformat() if brand_asset.created_at else ""
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading tenant brand asset: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload brand asset: {str(e)}"
        )


@router.delete("/me/brand-assets/{asset_id}")
async def delete_tenant_brand_asset(
    asset_id: UUID,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a tenant brand asset.
    """
    try:
        from app.models.brand_asset import BrandAsset
        from sqlalchemy import select
        
        # Get asset
        result = await db.execute(
            select(BrandAsset).where(
                BrandAsset.id == asset_id,
                BrandAsset.tenant_id == current_tenant.id
            )
        )
        asset = result.scalar_one_or_none()
        
        if not asset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Brand asset not found"
            )
        
        # Soft delete
        asset.is_active = False
        await db.commit()
        
        logger.info(f"Deleted tenant brand asset {asset_id}")
        
        return {"success": True, "message": "Brand asset deleted"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting tenant brand asset: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete brand asset: {str(e)}"
        )


@router.post("/me/generate/video", response_model=GenerateVideoResponse)
async def generate_content_video(
    request: GenerateVideoRequest,
    current_tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate a video for content creation using brand assets as reference images.
    Supports video extension to reach target duration (8-60 seconds).
    """
    try:
        # Validate duration
        duration = max(8, min(60, request.duration))
        
        from app.workers.content_creation import generate_video_with_assets_task
        
        celery_result = generate_video_with_assets_task.delay(
            tenant_id=str(current_tenant.id),
            prompt=request.prompt,
            target_duration=duration,
            brand_asset_ids=request.brand_asset_ids,
            user_id=str(current_user.id)
        )
        
        logger.info(f"Started content video generation task {celery_result.id}")
        
        extensions_needed = (duration - 8) // 8
        time_estimate = 5 + (extensions_needed * 3)
        
        return GenerateVideoResponse(
            task_id=celery_result.id,
            status="queued",
            message=f"Generating {duration}s video with {len(request.brand_asset_ids or [])} reference assets (estimated {time_estimate} minutes)"
        )
        
    except Exception as e:
        logger.error(f"Error starting content video generation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start video generation: {str(e)}"
        )


class GenerateImageRequest(BaseModel):
    """Request to generate image with brand assets for content"""
    prompt: str
    brand_asset_ids: Optional[List[str]] = None


class GenerateImageResponse(BaseModel):
    """Response for content image generation"""
    success: bool
    image_url: Optional[str] = None
    message: str


@router.post("/me/generate/image", response_model=GenerateImageResponse)
async def generate_content_image(
    request: GenerateImageRequest,
    current_tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate an image using brand assets as reference images.
    This is for testing the brand asset reference feature.
    """
    try:
        from app.services.llm.factory import create_llm_service
        from app.models.brand_asset import BrandAsset
        from app.services.storage import get_storage
        from sqlalchemy import select
        from io import BytesIO
        import uuid as uuid_lib
        import httpx
        
        llm_service = create_llm_service()
        
        # Fetch brand asset bytes if specified
        reference_images = []
        if request.brand_asset_ids:
            for asset_id in request.brand_asset_ids[:5]:  # Limit to 5
                try:
                    result = await db.execute(
                        select(BrandAsset).where(BrandAsset.id == uuid_lib.UUID(asset_id))
                    )
                    asset = result.scalar_one_or_none()
                    if asset and asset.url:
                        async with httpx.AsyncClient(timeout=30.0) as client:
                            resp = await client.get(asset.url)
                            if resp.status_code == 200:
                                reference_images.append(resp.content)
                                logger.info(f"Fetched reference asset: {asset.name}")
                except Exception as e:
                    logger.warning(f"Failed to fetch asset {asset_id}: {e}")
        
        logger.info(f"Generating image with {len(reference_images)} references. Prompt: {request.prompt[:100]}...")
        
        # Generate image with references
        images = await llm_service.generate_image(
            prompt=request.prompt,
            aspect_ratio="1:1",
            number_of_images=1,
            reference_images=reference_images if reference_images else None
        )
        
        if not images:
            return GenerateImageResponse(
                success=False,
                message="No image generated"
            )
        
        # Upload to storage
        storage = get_storage()
        storage_key = f"brand-assets/{current_tenant.id}/{uuid_lib.uuid4()}.png"
        
        img_bytes = BytesIO(images[0])
        url = await storage.upload(
            key=storage_key,
            file=img_bytes,
            content_type="image/png"
        )
        
        # Save as brand asset
        new_asset = BrandAsset(
            id=uuid_lib.uuid4(),
            tenant_id=current_tenant.id,
            name=f"Generated: {request.prompt[:50]}...",
            description=f"AI generated with {len(reference_images)} reference images",
            asset_type="image",
            source="generated",
            url=url,
            mime_type="image/png",
            created_by=current_user.id
        )
        db.add(new_asset)
        await db.commit()
        
        logger.info(f"Generated and saved image: {url}")
        
        return GenerateImageResponse(
            success=True,
            image_url=url,
            message=f"Generated image with {len(reference_images)} reference assets"
        )
        
    except Exception as e:
        logger.error(f"Error generating image: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate image: {str(e)}"
        )

# =====================
# Google Drive Integration API
# =====================

class GoogleDriveAuthUrlResponse(BaseModel):
    """Response with Google Drive OAuth URL"""
    auth_url: str
    is_connected: bool = False

class GoogleDriveConnectionStatus(BaseModel):
    """Google Drive connection status"""
    is_connected: bool
    connected_at: Optional[str] = None

class GoogleDriveFileItem(BaseModel):
    """Google Drive file item"""
    id: str
    name: str
    mime_type: str
    type: str  # 'image', 'video', 'folder'
    size: Optional[int] = None
    thumbnail_url: Optional[str] = None
    created_at: Optional[str] = None
    modified_at: Optional[str] = None
    parent_id: Optional[str] = None

class GoogleDriveFilesResponse(BaseModel):
    """Response with Google Drive files"""
    files: List[GoogleDriveFileItem]
    next_page_token: Optional[str] = None

class GoogleDriveImportRequest(BaseModel):
    """Request to import files from Google Drive as brand assets"""
    file_ids: List[str]

class GoogleDriveImportResponse(BaseModel):
    """Response for Drive file import"""
    imported_count: int
    assets: List[TenantBrandAssetResponse]
    errors: List[str] = []


@router.get("/me/integrations/google-drive/status", response_model=GoogleDriveConnectionStatus)
async def get_google_drive_status(
    current_tenant: Tenant = Depends(get_current_tenant)
):
    """
    Get Google Drive connection status for current tenant.
    """
    tokens = current_tenant.google_drive_tokens
    is_connected = tokens is not None and 'refresh_token' in (tokens or {})
    connected_at = tokens.get('connected_at') if tokens else None
    
    return GoogleDriveConnectionStatus(
        is_connected=is_connected,
        connected_at=connected_at
    )


@router.get("/me/integrations/google-drive/auth-url", response_model=GoogleDriveAuthUrlResponse)
async def get_google_drive_auth_url(
    redirect_uri: Optional[str] = None,  # Ignored - we use backend callback
    current_tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user)
):
    """
    Get Google Drive OAuth authorization URL.
    Uses unified Google callback like other Google services.
    """
    import uuid
    import json
    from datetime import datetime, timezone
    from app.config import settings
    
    try:
        # Generate state for OAuth flow
        state = str(uuid.uuid4())
        
        # Store state data in Redis (like other Google integrations)
        from app.api.v1.integrations import get_redis_client
        redis_client = get_redis_client()
        if redis_client:
            state_data = {
                "user_id": str(current_user.id),
                "tenant_id": str(current_tenant.id),
                "platform": "google_drive",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            redis_client.setex(
                f"oauth_state_{state}",
                14400,  # 4 hours
                json.dumps(state_data)
            )
        
        # Use unified Google callback (same as Google Ads, YouTube, etc.)
        backend_url = settings.BACKEND_URL or 'http://localhost:8000'
        google_redirect_uri = f"{backend_url}/api/v1/integrations/oauth/google/callback"
        
        # Build auth URL with Drive scopes
        scopes = [
            'https://www.googleapis.com/auth/drive.readonly',
            'https://www.googleapis.com/auth/drive.metadata.readonly',
            'openid',
            'email'
        ]
        
        auth_url = (
            f"https://accounts.google.com/o/oauth2/v2/auth?"
            f"response_type=code&"
            f"client_id={settings.GOOGLE_CLIENT_ID}&"
            f"redirect_uri={google_redirect_uri}&"
            f"scope={' '.join(scopes)}&"
            f"state={state}&"
            f"access_type=offline&"
            f"prompt=consent"
        )
        
        return GoogleDriveAuthUrlResponse(
            auth_url=auth_url,
            is_connected=current_tenant.google_drive_tokens is not None
        )
        
    except Exception as e:
        logger.error(f"Error generating Google Drive auth URL: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate auth URL: {str(e)}"
        )


@router.post("/me/integrations/google-drive/callback", response_model=GoogleDriveConnectionStatus)
async def google_drive_oauth_callback(
    code: str,
    redirect_uri: str,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Handle Google Drive OAuth callback and store tokens.
    
    Args:
        code: OAuth authorization code from callback
        redirect_uri: Same redirect URI used in auth request
    """
    from app.services.integrations.storage.google_drive import create_google_drive_service
    
    try:
        drive_service = create_google_drive_service(str(current_tenant.id))
        tokens = drive_service.exchange_code(code=code, redirect_uri=redirect_uri)
        
        # Store tokens in tenant
        current_tenant.google_drive_tokens = tokens
        await db.commit()
        
        logger.info(f"Google Drive connected for tenant {current_tenant.id}")
        
        return GoogleDriveConnectionStatus(
            is_connected=True,
            connected_at=tokens.get('connected_at')
        )
        
    except Exception as e:
        logger.error(f"Error exchanging Google Drive OAuth code: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to connect Google Drive: {str(e)}"
        )


@router.delete("/me/integrations/google-drive", response_model=GoogleDriveConnectionStatus)
async def disconnect_google_drive(
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Disconnect Google Drive by removing stored tokens.
    """
    current_tenant.google_drive_tokens = None
    await db.commit()
    
    logger.info(f"Google Drive disconnected for tenant {current_tenant.id}")
    
    return GoogleDriveConnectionStatus(is_connected=False)


@router.get("/me/integrations/google-drive/files", response_model=GoogleDriveFilesResponse)
async def list_google_drive_files(
    folder_id: Optional[str] = None,
    page_token: Optional[str] = None,
    current_tenant: Tenant = Depends(get_current_tenant)
):
    """
    List files (images/videos) from connected Google Drive.
    
    Args:
        folder_id: Optional folder ID to list contents of
        page_token: Pagination token for next page
    """
    from app.services.integrations.storage.google_drive import create_google_drive_service
    
    if not current_tenant.google_drive_tokens:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google Drive not connected. Please connect first."
        )
    
    try:
        drive_service = create_google_drive_service(
            str(current_tenant.id),
            tokens=current_tenant.google_drive_tokens
        )
        
        result = drive_service.list_files(
            folder_id=folder_id,
            page_token=page_token
        )
        
        return GoogleDriveFilesResponse(
            files=[GoogleDriveFileItem(**f) for f in result['files']],
            next_page_token=result.get('next_page_token')
        )
        
    except Exception as e:
        logger.error(f"Error listing Google Drive files: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list files: {str(e)}"
        )


@router.post("/me/brand-assets/import-from-drive", response_model=GoogleDriveImportResponse)
async def import_brand_assets_from_drive(
    request: GoogleDriveImportRequest,
    current_tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Import selected files from Google Drive as brand assets.
    
    Args:
        request: List of Drive file IDs to import
    """
    from app.services.integrations.storage.google_drive import create_google_drive_service
    from app.models.brand_asset import BrandAsset
    from app.services.storage import get_storage
    import uuid as uuid_lib
    from datetime import datetime, timezone
    from io import BytesIO
    
    if not current_tenant.google_drive_tokens:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google Drive not connected. Please connect first."
        )
    
    if not request.file_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files selected for import"
        )
    
    try:
        drive_service = create_google_drive_service(
            str(current_tenant.id),
            tokens=current_tenant.google_drive_tokens
        )
        storage = get_storage()
        
        imported_assets = []
        errors = []
        
        for file_id in request.file_ids:
            try:
                # Download file from Drive
                file_bytes, filename, mime_type = drive_service.download_file(file_id)
                
                # Determine asset type
                asset_type = "video" if mime_type.startswith("video/") else "image"
                
                # Generate storage key
                extension = filename.split('.')[-1] if '.' in filename else ('mp4' if asset_type == 'video' else 'jpg')
                storage_key = f"brand-assets/{current_tenant.id}/{uuid_lib.uuid4()}.{extension}"
                
                # Upload to storage
                url = await storage.upload(
                    key=storage_key,
                    file=BytesIO(file_bytes),
                    content_type=mime_type
                )
                
                # Create brand asset record
                asset = BrandAsset(
                    id=uuid_lib.uuid4(),
                    tenant_id=current_tenant.id,
                    name=filename,
                    description=f"Imported from Google Drive",
                    asset_type=asset_type,
                    source="google_drive",
                    url=url,
                    storage_key=storage_key,
                    file_name=filename,
                    file_size=len(file_bytes),
                    mime_type=mime_type,
                    created_by=current_user.id
                )
                
                db.add(asset)
                await db.flush()
                
                imported_assets.append(TenantBrandAssetResponse(
                    id=str(asset.id),
                    name=asset.name,
                    description=asset.description,
                    asset_type=asset.asset_type,
                    source=asset.source,
                    url=asset.url,
                    thumbnail_url=asset.thumbnail_url,
                    file_name=asset.file_name,
                    file_size=asset.file_size,
                    mime_type=asset.mime_type,
                    width=asset.width,
                    height=asset.height,
                    usage_count=asset.usage_count,
                    created_at=asset.created_at.isoformat() if asset.created_at else datetime.now(timezone.utc).isoformat()
                ))
                
                logger.info(f"Imported Drive file: {filename} -> {url}")
                
            except Exception as e:
                logger.error(f"Failed to import Drive file {file_id}: {str(e)}")
                errors.append(f"Failed to import file {file_id}: {str(e)}")
        
        await db.commit()
        
        return GoogleDriveImportResponse(
            imported_count=len(imported_assets),
            assets=imported_assets,
            errors=errors
        )
        
    except Exception as e:
        logger.error(f"Error importing from Google Drive: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to import files: {str(e)}"
        )
