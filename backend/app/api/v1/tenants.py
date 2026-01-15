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
        
        # Delete from storage (fire and forget or await?)
        # Since we want to ensure cleanup, we await it.
        # If it fails, we log it but don't fail the API call since the DB record is already "deleted"
        if asset.url:
            try:
                from app.services.storage import get_storage
                storage = get_storage()
                await storage.delete(asset.url)
                logger.info(f"Deleted storage file for asset {asset_id}")
            except Exception as e:
                logger.error(f"Failed to delete storage file for asset {asset_id}: {e}")
        
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


# =====================
# Quick Setup AI-Powered Onboarding API
# =====================

class QuickSetupResearchRequest(BaseModel):
    """Optional request body for research endpoint"""
    website_url: Optional[str] = None  # Override tenant's website_url


class QuickSetupResearchResponse(BaseModel):
    """Response from AI website research"""
    description: str
    company_name: Optional[str] = None
    industry: Optional[str] = None
    products_services: Optional[str] = None
    target_audience: Optional[str] = None
    brand_voice: Optional[str] = None
    sources: List[dict] = []


class QuickSetupSaveRequest(BaseModel):
    """Request to save AI-generated description as knowledge chunk"""
    description: str
    category: str = "company_overview"  # company_overview, brand_guidelines, product_catalog, target_audience


class QuickSetupSaveResponse(BaseModel):
    """Response from saving Quick Setup description"""
    success: bool
    document_id: Optional[str] = None
    chunk_count: int = 0
    message: str


@router.post("/me/quick-setup/research", response_model=QuickSetupResearchResponse)
async def quick_setup_research(
    request: Optional[QuickSetupResearchRequest] = None,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Research tenant's website using Gemini Search Grounding to generate
    an AI-powered business description for quick onboarding setup.
    
    Uses the website_url from tenant settings (or override in request body).
    """
    from google import genai
    from google.genai import types
    from app.config import settings
    
    # Get website URL from request or tenant
    website_url = None
    if request and request.website_url:
        website_url = request.website_url
    elif current_tenant.website_url:
        website_url = current_tenant.website_url
    
    if not website_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No website URL found. Please provide a website URL in settings first."
        )
    
    try:
        api_key = settings.GOOGLE_API_KEY
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Gemini API key not configured"
            )
        
        client = genai.Client(api_key=api_key)
        
        # Research prompt with structured output request
        research_prompt = f"""You are a business analyst. Research the following website and provide structured business information.

Website: {website_url}

IMPORTANT: Do NOT include any preamble, introduction, or acknowledgment. Start DIRECTLY with the content. Do NOT say things like "Okay, I will research..." or "Here's a breakdown...". Just provide the information.

Provide the following information in a structured markdown format:

## Company Overview
A comprehensive 2-3 paragraph description of what the company does, their mission, and key value propositions.

## Company Name
The official name of the company.

## Industry
The primary industry or sector they operate in.

## Products/Services
A detailed description of their main products or services.

## Target Audience
Who are their ideal customers? Include demographics, business types, or user personas if identifiable.

## Brand Voice
Based on their website content and messaging, describe their brand voice and tone (e.g., professional, friendly, innovative, authoritative, casual, etc.).

Be thorough and accurate. Include specific details found on their website. This information will be used to train an AI marketing assistant."""

        # Call Gemini with Google Search grounding
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=research_prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.3
            )
        )
        
        # Extract content
        full_content = ""
        if hasattr(response, 'text') and response.text:
            full_content = response.text
        elif hasattr(response, 'parts') and response.parts:
            full_content = " ".join([p.text for p in response.parts if hasattr(p, 'text')])
        
        # Extract grounding sources
        sources = []
        if hasattr(response, 'candidates') and response.candidates:
            for candidate in response.candidates:
                if hasattr(candidate, 'grounding_metadata') and candidate.grounding_metadata:
                    metadata = candidate.grounding_metadata
                    if hasattr(metadata, 'grounding_chunks') and metadata.grounding_chunks:
                        for chunk in metadata.grounding_chunks:
                            if hasattr(chunk, 'web') and chunk.web:
                                sources.append({
                                    "title": getattr(chunk.web, 'title', ''),
                                    "uri": getattr(chunk.web, 'uri', '')
                                })
        
        # Parse structured sections from the response
        company_name = None
        industry = None
        products_services = None
        target_audience = None
        brand_voice = None
        
        # Simple parsing - look for section headers
        content_lower = full_content.lower()
        lines = full_content.split('\n')
        
        current_section = None
        section_content = {}
        
        for line in lines:
            line_lower = line.lower().strip()
            if 'company name' in line_lower:
                current_section = 'company_name'
            elif 'industry' in line_lower:
                current_section = 'industry'
            elif 'products' in line_lower or 'services' in line_lower:
                current_section = 'products_services'
            elif 'target audience' in line_lower:
                current_section = 'target_audience'
            elif 'brand voice' in line_lower:
                current_section = 'brand_voice'
            elif 'company overview' in line_lower:
                current_section = 'overview'
            elif current_section and line.strip():
                if current_section not in section_content:
                    section_content[current_section] = []
                # Clean the line (remove ** markdown)
                clean_line = line.strip().lstrip('*').rstrip('*').strip()
                if clean_line and not clean_line.startswith('**'):
                    section_content[current_section].append(clean_line)
        
        # Extract values
        company_name = '\n'.join(section_content.get('company_name', []))[:200] if section_content.get('company_name') else None
        industry = '\n'.join(section_content.get('industry', []))[:200] if section_content.get('industry') else None
        products_services = '\n'.join(section_content.get('products_services', []))[:1000] if section_content.get('products_services') else None
        target_audience = '\n'.join(section_content.get('target_audience', []))[:500] if section_content.get('target_audience') else None
        brand_voice = '\n'.join(section_content.get('brand_voice', []))[:300] if section_content.get('brand_voice') else None
        
        logger.info(f"Quick Setup research completed for {website_url} with {len(sources)} sources")
        
        return QuickSetupResearchResponse(
            description=full_content,
            company_name=company_name,
            industry=industry,
            products_services=products_services,
            target_audience=target_audience,
            brand_voice=brand_voice,
            sources=sources
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Quick Setup research failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to research website. Please check the URL and try again."
        )


@router.post("/me/quick-setup/save", response_model=QuickSetupSaveResponse)
async def quick_setup_save(
    request: QuickSetupSaveRequest,
    current_tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Save AI-generated business description as a knowledge chunk.
    
    This creates a pseudo-document and stores its embeddings in ChromaDB,
    making the content available for RAG retrieval in campaigns and content creation.
    """
    from app.models.document import Document, DocumentStatus, DocumentType
    from app.services.llm.factory import create_llm_service
    from app.services.vector_store import get_vector_store_service
    from datetime import datetime, timezone
    import uuid as uuid_lib
    
    if not request.description or len(request.description.strip()) < 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Description must be at least 50 characters"
        )
    
    try:
        # Create pseudo-document record
        doc_id = uuid_lib.uuid4()
        filename = f"quick_setup_{request.category}_{doc_id.hex[:8]}.txt"
        
        document = Document(
            id=doc_id,
            tenant_id=current_tenant.id,
            assistant_id=None,
            uploaded_by=current_user.id,
            filename=filename,
            original_filename=filename,
            file_type=DocumentType.TXT,  # Use TXT type; ai_generated flag is in meta_data
            file_size=len(request.description.encode('utf-8')),
            storage_key=f"virtual/quick_setup/{current_tenant.id}/{doc_id}",
            storage_url=None,  # No actual file stored
            content_preview=request.description[:500],
            extracted_text=request.description,
            meta_data={
                "source": "quick_setup",
                "category": request.category,
                "required_type": request.category,
                "document_category": "required",
                "ai_generated": True
            },
            status=DocumentStatus.PROCESSING
        )
        
        db.add(document)
        await db.commit()
        await db.refresh(document)
        
        # Generate embeddings and store in ChromaDB
        llm_service = create_llm_service()
        
        # Split into chunks if content is large
        text = request.description
        chunk_size = 1000
        overlap = 200
        chunks = []
        
        if len(text) <= chunk_size:
            chunks = [text]
        else:
            start = 0
            while start < len(text):
                end = min(start + chunk_size, len(text))
                chunk = text[start:end]
                if chunk.strip():
                    chunks.append(chunk.strip())
                start = end - overlap if end < len(text) else len(text)
        
        # Generate embeddings for each chunk
        chunk_embeddings = []
        for i, chunk_text in enumerate(chunks):
            try:
                embeddings_result = await llm_service.generate_embeddings([chunk_text])
                embedding = embeddings_result[0] if embeddings_result else None
                
                if embedding:
                    chunk_embeddings.append({
                        "chunk_index": i,
                        "content": chunk_text,
                        "embedding": embedding,
                        "token_count": len(chunk_text.split())
                    })
            except Exception as e:
                logger.warning(f"Failed to generate embedding for chunk {i}: {str(e)}")
        
        # Store in ChromaDB
        if chunk_embeddings:
            vector_store = get_vector_store_service()
            vector_store.add_document_chunks(
                tenant_id=current_tenant.id,
                document_id=document.id,
                chunks=chunk_embeddings,
                assistant_id=None
            )
            logger.info(f"Stored {len(chunk_embeddings)} chunks in ChromaDB for Quick Setup document {doc_id}")
        
        # Update document status
        document.chunk_count = len(chunks)
        document.embedding_count = len(chunk_embeddings)
        document.status = DocumentStatus.COMPLETED
        document.processed_at = datetime.now(timezone.utc)
        
        await db.commit()
        await db.refresh(document)
        
        logger.info(f"Quick Setup save completed: doc={doc_id}, chunks={len(chunks)}, embeddings={len(chunk_embeddings)}")
        
        return QuickSetupSaveResponse(
            success=True,
            document_id=str(document.id),
            chunk_count=len(chunk_embeddings),
            message=f"Successfully saved business information as {len(chunk_embeddings)} knowledge chunks"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Quick Setup save failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save business information. Please try again."
        )

