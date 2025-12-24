"""
Social media integration API routes
Handles OAuth flows for connecting social media platforms
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID
import uuid
import json
import hashlib
import base64
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
import httpx
from app.db.session import get_db
from app.dependencies import get_current_user, get_current_tenant
from app.models.user import User
from app.models.tenant import Tenant
from app.schemas.integration import (
    SocialIntegrationResponse,
    SocialIntegrationListResponse,
    PlatformStatusListResponse,
    IntegrationStatusResponse,
    DisconnectIntegrationRequest,
    SetDefaultPageRequest
)
from app.services.integration_service import IntegrationService
from app.config import settings
from app.utils.logger import logger

router = APIRouter(prefix="/integrations", tags=["integrations"])

# Redis client for OAuth state storage (lazy initialization)
_redis_client = None

def get_redis_client():
    """Get Redis client (lazy initialization)"""
    global _redis_client
    if _redis_client is None:
        try:
            import redis
            import ssl
            if not settings.REDIS_URL:
                _redis_client = False
                return None
            
            # Dynamically build the Redis configuration
            # Check if URL uses rediss:// or if REDIS_USE_SSL is set
            use_ssl = settings.REDIS_USE_SSL or settings.REDIS_URL.startswith('rediss://')
            
            # Only include SSL settings if SSL is required
            if use_ssl:
                _redis_client = redis.from_url(
                    settings.REDIS_URL,
                    ssl_cert_reqs=ssl.CERT_NONE
                )
            else:
                _redis_client = redis.from_url(settings.REDIS_URL)
        except ImportError:
            logger.warning("Redis not installed, OAuth state will not be persisted")
            _redis_client = False
    return _redis_client if _redis_client else None


def generate_code_verifier() -> str:
    """Generate PKCE code verifier"""
    return secrets.token_urlsafe(64)[:128]


def generate_code_challenge(code_verifier: str) -> str:
    """Generate PKCE code challenge"""
    code_challenge = hashlib.sha256(code_verifier.encode('utf-8')).digest()
    code_challenge = base64.urlsafe_b64encode(code_challenge).decode('utf-8')
    return code_challenge.rstrip('=')


@router.get("/status")
async def get_integration_status(
    assistant_id: Optional[UUID] = Query(None),
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """Get connection status for all platforms"""
    service = IntegrationService(db)
    status_data = await service.get_platform_status(
        tenant_id=current_tenant.id,
        assistant_id=assistant_id
    )
    
    platforms = [
        IntegrationStatusResponse(
            platform=platform,
            **status_data[platform]
        )
        for platform in IntegrationService.SUPPORTED_PLATFORMS
    ]
    
    total_connected = sum(1 for p in platforms if p.is_connected)
    
    return PlatformStatusListResponse(
        platforms=platforms,
        total_connected=total_connected
    )


@router.get("")
async def list_integrations(
    assistant_id: Optional[UUID] = Query(None),
    platform: Optional[str] = Query(None),
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """List all integrations"""
    service = IntegrationService(db)
    integrations = await service.list_integrations(
        tenant_id=current_tenant.id,
        assistant_id=assistant_id,
        platform=platform
    )
    
    # Convert to response format with default_page_id
    integration_responses = [
        SocialIntegrationResponse.from_orm(integration)
        for integration in integrations
    ]
    
    return SocialIntegrationListResponse(
        integrations=integration_responses,
        total=len(integration_responses)
    )


@router.get("/{integration_id}")
async def get_integration(
    integration_id: UUID,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """Get integration by ID"""
    service = IntegrationService(db)
    integration = await service.get_integration(
        tenant_id=current_tenant.id,
        integration_id=integration_id
    )
    return SocialIntegrationResponse.from_orm(integration)


@router.get("/{integration_id}/oauth1/init-url")
async def get_oauth1_init_url(
    integration_id: UUID,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Get OAuth 1.0a initialization URL for Twitter integration.
    This endpoint returns the URL that the UI should redirect to for OAuth 1.0a flow.
    Only available for Twitter integrations that have completed OAuth 2.0.
    """
    service = IntegrationService(db)
    integration = await service.get_integration(
        tenant_id=current_tenant.id,
        integration_id=integration_id
    )
    
    if integration.platform != "twitter":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth 1.0a is only available for Twitter integrations"
        )
    
    if not integration.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Integration is not active"
        )
    
    # Check if OAuth 1.0a is already configured
    meta_data = integration.meta_data or {}
    oauth1_configured = meta_data.get("oauth1_configured", False) or bool(
        meta_data.get("oauth1_token") and meta_data.get("oauth1_token_secret")
    )
    
    if oauth1_configured:
        return {
            "oauth1_configured": True,
            "message": "OAuth 1.0a is already configured for this integration",
            "init_url": None
        }
    
    # Return the OAuth 1.0a init URL
    backend_url = settings.BACKEND_URL or 'http://localhost:8000'
    init_url = f"{backend_url}/api/v1/integrations/oauth/twitter/oauth1/init"
    
    return {
        "oauth1_configured": False,
        "message": "OAuth 1.0a is required for media uploads. Click to complete authorization.",
        "init_url": init_url,
        "required_for": "media_uploads"
    }


@router.post("/{integration_id}/disconnect")
async def disconnect_integration(
    integration_id: UUID,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """Disconnect an integration"""
    service = IntegrationService(db)
    
    # Get integration before disconnecting to check platform and revoke token if needed
    integration = await service.get_integration(
        tenant_id=current_tenant.id,
        integration_id=integration_id
    )
    
    # Revoke OAuth token for Google integrations
    if integration.platform in ["google_ads", "google_analytics"] and integration.refresh_token:
        try:
            from app.utils.google_ads import revoke_google_oauth_token
            revoked = await revoke_google_oauth_token(integration.refresh_token)
            if revoked:
                logger.info(f"Revoked Google OAuth token for integration {integration_id}")
            else:
                logger.warning(f"Failed to revoke Google OAuth token for integration {integration_id}")
        except Exception as e:
            logger.warning(f"Error revoking Google OAuth token: {e}")
    
    await service.disconnect_integration(
        tenant_id=current_tenant.id,
        integration_id=integration_id
    )
    return {"status": "disconnected"}


@router.delete("/{integration_id}")
async def delete_integration(
    integration_id: UUID,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """Permanently delete an integration"""
    service = IntegrationService(db)
    await service.delete_integration(
        tenant_id=current_tenant.id,
        integration_id=integration_id
    )
    return {"status": "deleted"}


@router.put("/{integration_id}/default-page")
async def set_default_page(
    integration_id: UUID,
    request: SetDefaultPageRequest,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """Set the default page/organization for an integration"""
    service = IntegrationService(db)
    
    try:
        integration = await service.set_default_page(
            tenant_id=current_tenant.id,
            integration_id=integration_id,
            page_id=request.page_id
        )
        return {
            "message": "Default page set successfully",
            "integration": SocialIntegrationResponse.from_orm(integration)
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# OAuth Initiation Routes
@router.get("/oauth/{platform}/init")
async def init_oauth(
    platform: str,
    assistant_id: Optional[UUID] = Query(None),
    redirect: bool = Query(False, description="If true, redirect directly. If false, return JSON with URL."),
    current_user: User = Depends(get_current_user),
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Initialize OAuth flow for a platform
    Supported platforms: facebook, instagram, linkedin, twitter, tiktok, google_ads, google_analytics, meta_ads
    """
    if platform not in IntegrationService.SUPPORTED_PLATFORMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported platform: {platform}"
        )
    
    service = IntegrationService(db)
    config = await service.get_integration_config(platform)
    
    if not config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{platform.title()} OAuth not configured"
        )
    
    # Generate state
    state = str(uuid.uuid4())
    
    # Store OAuth state in Redis
    state_data = {
        "user_id": str(current_user.id),
        "tenant_id": str(current_tenant.id),
        "assistant_id": str(assistant_id) if assistant_id else None,
        "platform": platform,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    redis_client = get_redis_client()
    if redis_client:
        redis_client.setex(
            f"oauth_state_{state}",
            14400,  # 4 hours
            json.dumps(state_data)
        )
    
    # Build redirect URI - point to backend callback endpoint
    # Must match exactly what's registered in the OAuth app settings
    backend_url = settings.BACKEND_URL or 'http://localhost:8000'
    redirect_uri = f"{backend_url}/api/v1/integrations/oauth/{platform}/callback"
    
    # Platform-specific OAuth URL generation
    if platform == "facebook":
        scopes = [
            "email",
            "public_profile",
            "pages_show_list",
            "pages_read_engagement",
            "pages_manage_posts",
            "pages_manage_metadata",
        ]
        auth_url = (
            f"https://www.facebook.com/v18.0/dialog/oauth?"
            f"response_type=code&"
            f"client_id={config.client_id}&"
            f"redirect_uri={redirect_uri}&"
            f"scope={' '.join(scopes)}&"
            f"state={state}"
        )
    
    elif platform == "instagram":
        # Instagram uses Facebook OAuth
        scopes = [
            "email",
            "public_profile",
            "instagram_basic",
            "instagram_content_publish",
        ]
        auth_url = (
            f"https://www.facebook.com/v18.0/dialog/oauth?"
            f"response_type=code&"
            f"client_id={config.client_id}&"
            f"redirect_uri={redirect_uri}&"
            f"scope={' '.join(scopes)}&"
            f"state={state}"
        )
    
    elif platform == "linkedin":
        scopes = [
            "w_member_social",
            "r_member_postAnalytics",
            "r_organization_followers",
            "r_organization_social",
            "rw_organization_admin",
            "w_organization_social",
            "r_basicprofile",
        ]
        # LinkedIn requires URL-encoded redirect_uri in authorization URL
        from urllib.parse import quote
        encoded_redirect_uri = quote(redirect_uri, safe='')
        auth_url = (
            f"https://www.linkedin.com/oauth/v2/authorization?"
            f"response_type=code&"
            f"client_id={config.client_id}&"
            f"redirect_uri={encoded_redirect_uri}&"
            f"scope={' '.join(scopes)}&"
            f"state={state}"
        )
    
    elif platform == "twitter":
        code_verifier = generate_code_verifier()
        code_challenge = generate_code_challenge(code_verifier)
        
        # Store code_verifier in state
        redis_client = get_redis_client()
        if redis_client:
            state_data["code_verifier"] = code_verifier
            redis_client.setex(
                f"oauth_state_{state}",
                14400,
                json.dumps(state_data)
            )
        
        scopes = "tweet.read tweet.write users.read offline.access"
        auth_url = (
            f"https://twitter.com/i/oauth2/authorize?"
            f"response_type=code&"
            f"client_id={config.client_id}&"
            f"redirect_uri={redirect_uri}&"
            f"scope={scopes}&"
            f"state={state}&"
            f"code_challenge_method=S256&"
            f"code_challenge={code_challenge}"
        )
    
    elif platform == "tiktok":
        code_verifier = generate_code_verifier()
        code_challenge = generate_code_challenge(code_verifier)

        # Store code_verifier in state
        redis_client = get_redis_client()
        if redis_client:
            state_data["code_verifier"] = code_verifier
            redis_client.setex(
                f"oauth_state_{state}",
                14400,
                json.dumps(state_data)
            )
        
        scopes = "user.info.basic,video.publish,video.upload,user.info.profile"
        auth_url = (
            f"https://www.tiktok.com/v2/auth/authorize/?"
            f"client_key={config.client_id}&"
            f"response_type=code&"
            f"scope={scopes}&"
            f"redirect_uri={redirect_uri}&"
            f"state={state}&"
            f"code_challenge={code_challenge}&"
            f"code_challenge_method=S256"
        )
    
    elif platform == "google_ads":
        scopes = [
            "https://www.googleapis.com/auth/adwords",
            "https://www.googleapis.com/auth/userinfo.email",
            "openid"
        ]
        # Use unified Google callback URL for all Google services
        backend_url = settings.BACKEND_URL or 'http://localhost:8000'
        google_redirect_uri = f"{backend_url}/api/v1/integrations/oauth/google/callback"
        auth_url = (
            f"https://accounts.google.com/o/oauth2/v2/auth?"
            f"response_type=code&"
            f"client_id={config.client_id}&"
            f"redirect_uri={google_redirect_uri}&"
            f"scope={' '.join(scopes)}&"
            f"state={state}&"
            f"access_type=offline&"
            f"prompt=consent"
        )
    
    elif platform == "google_analytics":
        scopes = [
            "https://www.googleapis.com/auth/analytics.readonly",
            "https://www.googleapis.com/auth/analytics",
            "openid",
            "email",
            "profile"
        ]
        # Use unified Google callback URL for all Google services
        backend_url = settings.BACKEND_URL or 'http://localhost:8000'
        google_redirect_uri = f"{backend_url}/api/v1/integrations/oauth/google/callback"
        auth_url = (
            f"https://accounts.google.com/o/oauth2/v2/auth?"
            f"response_type=code&"
            f"client_id={config.client_id}&"
            f"redirect_uri={google_redirect_uri}&"
            f"scope={' '.join(scopes)}&"
            f"state={state}&"
            f"access_type=offline&"
            f"prompt=consent"
        )
    
    elif platform == "youtube":
        scopes = [
            "https://www.googleapis.com/auth/youtube",
            "https://www.googleapis.com/auth/youtube.force-ssl",
            "https://www.googleapis.com/auth/youtube.readonly",
            "https://www.googleapis.com/auth/youtube.upload",
            "email",
            "profile",
            "openid"
        ]
        # Use unified Google callback URL for all Google services
        backend_url = settings.BACKEND_URL or 'http://localhost:8000'
        google_redirect_uri = f"{backend_url}/api/v1/integrations/oauth/google/callback"
        auth_url = (
            f"https://accounts.google.com/o/oauth2/v2/auth?"
            f"response_type=code&"
            f"client_id={config.client_id}&"
            f"redirect_uri={google_redirect_uri}&"
            f"scope={' '.join(scopes)}&"
            f"state={state}&"
            f"access_type=offline&"
            f"prompt=consent"
        )
    
    elif platform == "meta_ads":
        scopes = [
            "ads_read",
            "ads_management",
            "business_management",
            "pages_read_engagement",
            "pages_manage_ads"
        ]
        auth_url = (
            f"https://www.facebook.com/v18.0/dialog/oauth?"
            f"response_type=code&"
            f"client_id={config.client_id}&"
            f"redirect_uri={redirect_uri}&"
            f"scope={','.join(scopes)}&"
            f"state={state}"
        )
    
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth URL generation not implemented for platform: {platform}"
        )
    
    logger.info(f"OAuth init for {platform}: redirecting to {auth_url}")
    
    # If redirect parameter is true, redirect directly (for direct browser navigation)
    # Otherwise, return JSON with URL (for API calls)
    if redirect:
        return RedirectResponse(url=auth_url)
    else:
        return JSONResponse(content={"url": auth_url})



@router.get("/oauth/google/callback")
async def google_unified_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Unified OAuth callback for all Google services (Google Ads, Analytics, YouTube).
    The actual platform is determined from the state data stored in Redis.
    """
    frontend_url = settings.FRONTEND_URL or "http://localhost:3000"
    backend_url = settings.BACKEND_URL or "http://localhost:8000"
    
    logger.info(f"Google unified callback hit - code: {code[:20] if code else None}..., state: {state}")
    
    if error:
        logger.error(f"Google OAuth error: {error}")
        return RedirectResponse(
            url=f"{frontend_url}/dashboard/integrations?success=false&error={error}"
        )
    
    if not code or not state:
        return RedirectResponse(
            url=f"{frontend_url}/dashboard/integrations?success=false&error=Missing code or state"
        )
    
    # Retrieve state from Redis to get the actual platform
    redis_client = get_redis_client()
    if not redis_client:
        return RedirectResponse(
            url=f"{frontend_url}/dashboard/integrations?success=false&error=Redis not configured"
        )
    
    state_data_str = redis_client.get(f"oauth_state_{state}")
    if not state_data_str:
        return RedirectResponse(
            url=f"{frontend_url}/dashboard/integrations?success=false&error=Invalid or expired state"
        )
    
    state_data = json.loads(state_data_str)
    platform = state_data.get("platform")  # This will be google_ads, google_analytics, or youtube
    tenant_id = UUID(state_data["tenant_id"])
    user_id = UUID(state_data["user_id"])
    assistant_id = UUID(state_data["assistant_id"]) if state_data.get("assistant_id") else None
    
    # Handle Google Drive separately - stores tokens directly on tenant
    if platform == "google_drive":
        try:
            from app.services.integrations.storage.google_drive import create_google_drive_service
            from sqlalchemy import select
            from app.models.tenant import Tenant
            
            drive_service = create_google_drive_service(str(tenant_id))
            google_redirect_uri = f"{backend_url}/api/v1/integrations/oauth/google/callback"
            tokens = drive_service.exchange_code(code=code, redirect_uri=google_redirect_uri)
            
            # Store tokens in tenant
            result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
            tenant = result.scalar_one_or_none()
            if tenant:
                tenant.google_drive_tokens = tokens
                await db.commit()
                logger.info(f"Google Drive connected for tenant {tenant_id}")
            
            # Clean up state
            redis_client.delete(f"oauth_state_{state}")
            
            return RedirectResponse(
                url=f"{frontend_url}/dashboard/integrations?success=true&platform=google_drive"
            )
        except Exception as e:
            logger.error(f"Error connecting Google Drive: {e}", exc_info=True)
            return RedirectResponse(
                url=f"{frontend_url}/dashboard/integrations?success=false&error={str(e)[:100]}"
            )
    
    if platform not in ["google_ads", "google_analytics", "youtube"]:
        logger.error(f"Google callback received for non-Google platform: {platform}")
        return RedirectResponse(
            url=f"{frontend_url}/dashboard/integrations?success=false&error=Invalid platform for Google callback"
        )
    
    logger.info(f"Google unified callback for platform: {platform}, tenant: {tenant_id}, assistant_id: {assistant_id}")
    
    # Get integration config
    service = IntegrationService(db)
    config = await service.get_integration_config(platform)
    logger.info(f"Config for {platform}: {config}")
    
    if not config:
        logger.error(f"No config found for platform: {platform}")
        return RedirectResponse(
            url=f"{frontend_url}/dashboard/integrations?success=false&error=Platform not configured"
        )
    
    # Use the unified Google redirect URI
    redirect_uri = f"{backend_url}/api/v1/integrations/oauth/google/callback"
    
    try:
        # Exchange code for token (platform-specific)
        token_result = await _exchange_token(
            platform, code, config, redirect_uri, state_data
        )
        
        # Unpack token result
        if len(token_result) == 7:
            access_token, refresh_token, token_expires_at, profile_data, pages, organizations, refresh_token_expires_at = token_result
        else:
            access_token, refresh_token, token_expires_at, profile_data, pages, organizations = token_result
            refresh_token_expires_at = None
        
        # Create or update integration
        integration = await service.create_or_update_integration(
            tenant_id=tenant_id,
            platform=platform,
            platform_user_id=profile_data.get("id") or profile_data.get("channel_id") or str(uuid.uuid4()),
            access_token=access_token,
            profile_data=profile_data,
            assistant_id=assistant_id,
            connected_by=user_id,
            refresh_token=refresh_token,
            token_expires_at=token_expires_at,
            refresh_token_expires_at=refresh_token_expires_at,
            pages=pages,
            organizations=organizations
        )
        
        # Clean up state
        redis_client.delete(f"oauth_state_{state}")
        
        logger.info(f"Successfully connected {platform} for tenant {tenant_id}")
        
        # For YouTube, redirect to workspace if connected from campaign (for now, just use integrations page)
        if platform == "youtube":
            return RedirectResponse(
                url=f"{frontend_url}/dashboard/integrations?success=true&platform=youtube&linked=youtube&channel_id={profile_data.get('channel_id', '')}"
            )
        
        return RedirectResponse(
            url=f"{frontend_url}/dashboard/integrations?success=true&platform={platform}&integration_id={integration.id}"
        )
    
    except Exception as e:
        logger.error(f"Error in Google unified callback for {platform}: {str(e)}", exc_info=True)
        error_message = str(e)
        if len(error_message) > 200:
            error_message = error_message[:200] + "..."
        return RedirectResponse(
            url=f"{frontend_url}/dashboard/integrations?success=false&error={error_message}"
        )


@router.get("/oauth/{platform}/callback")
async def oauth_callback(
    platform: str,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Handle OAuth callback from platform
    This will be called by the frontend after OAuth redirect
    """
    frontend_url = settings.FRONTEND_URL or "http://localhost:3000"
    backend_url = settings.BACKEND_URL or "http://localhost:8000"
    
    if error:
        logger.error(f"OAuth error for {platform}: {error}")
        return RedirectResponse(
            url=f"{frontend_url}/dashboard/integrations?success=false&error={error}"
        )
    
    if not code or not state:
        return RedirectResponse(
            url=f"{frontend_url}/dashboard/integrations?success=false&error=Missing code or state"
        )
    
    # Retrieve state from Redis
    redis_client = get_redis_client()
    if not redis_client:
        return RedirectResponse(
            url=f"{frontend_url}/dashboard/integrations?success=false&error=Redis not configured"
        )
    
    state_data_str = redis_client.get(f"oauth_state_{state}")
    if not state_data_str:
        return RedirectResponse(
            url=f"{frontend_url}/dashboard/integrations?success=false&error=Invalid or expired state"
        )
    
    state_data = json.loads(state_data_str)
    tenant_id = UUID(state_data["tenant_id"])
    user_id = UUID(state_data["user_id"])
    assistant_id = UUID(state_data["assistant_id"]) if state_data.get("assistant_id") else None
    
    # Get integration config
    service = IntegrationService(db)
    config = await service.get_integration_config(platform)
    
    if not config:
        return RedirectResponse(
            url=f"{frontend_url}/dashboard/integrations?success=false&error=Platform not configured"
        )
    
    redirect_uri = f"{backend_url}/api/v1/integrations/oauth/{platform}/callback"
    
    try:
        # Exchange code for token (platform-specific)
        token_result = await _exchange_token(
            platform, code, config, redirect_uri, state_data
        )
        
        # Unpack token result - handle both old format (6 items) and new format (7 items with refresh_token_expires_at)
        if len(token_result) == 7:
            access_token, refresh_token, token_expires_at, profile_data, pages, organizations, refresh_token_expires_at = token_result
        else:
            access_token, refresh_token, token_expires_at, profile_data, pages, organizations = token_result
            refresh_token_expires_at = None
        
        # Create or update integration
        integration = await service.create_or_update_integration(
            tenant_id=tenant_id,
            platform=platform,
            platform_user_id=profile_data.get("id") or profile_data.get("open_id") or str(uuid.uuid4()),
            access_token=access_token,
            profile_data=profile_data,
            assistant_id=assistant_id,
            connected_by=user_id,
            refresh_token=refresh_token,
            token_expires_at=token_expires_at,
            refresh_token_expires_at=refresh_token_expires_at,
            pages=pages,
            organizations=organizations
        )
        
        # Clean up state
        redis_client = get_redis_client()
        if redis_client:
            redis_client.delete(f"oauth_state_{state}")
        
        logger.info(f"Successfully connected {platform} for tenant {tenant_id}")
        return RedirectResponse(
            url=f"{frontend_url}/dashboard/integrations?success=true&platform={platform}&integration_id={integration.id}"
        )
    
    except Exception as e:
        logger.error(f"Error in OAuth callback for {platform}: {str(e)}", exc_info=True)
        error_message = str(e)
        # Truncate long error messages for URL
        if len(error_message) > 200:
            error_message = error_message[:200] + "..."
        return RedirectResponse(
            url=f"{frontend_url}/dashboard/integrations?success=false&error={error_message}"
        )


@router.get("/oauth/google/callback")
async def google_unified_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Unified OAuth callback for all Google services (Google Ads, Analytics, YouTube).
    The actual platform is determined from the state data stored in Redis.
    """
    frontend_url = settings.FRONTEND_URL or "http://localhost:3000"
    backend_url = settings.BACKEND_URL or "http://localhost:8000"
    
    if error:
        logger.error(f"Google OAuth error: {error}")
        return RedirectResponse(
            url=f"{frontend_url}/dashboard/integrations?success=false&error={error}"
        )
    
    if not code or not state:
        return RedirectResponse(
            url=f"{frontend_url}/dashboard/integrations?success=false&error=Missing code or state"
        )
    
    # Retrieve state from Redis to get the actual platform
    redis_client = get_redis_client()
    if not redis_client:
        return RedirectResponse(
            url=f"{frontend_url}/dashboard/integrations?success=false&error=Redis not configured"
        )
    
    state_data_str = redis_client.get(f"oauth_state_{state}")
    if not state_data_str:
        return RedirectResponse(
            url=f"{frontend_url}/dashboard/integrations?success=false&error=Invalid or expired state"
        )
    
    state_data = json.loads(state_data_str)
    platform = state_data.get("platform")  # This will be google_ads, google_analytics, or youtube
    tenant_id = UUID(state_data["tenant_id"])
    user_id = UUID(state_data["user_id"])
    assistant_id = UUID(state_data["assistant_id"]) if state_data.get("assistant_id") else None
    
    if platform not in ["google_ads", "google_analytics", "youtube"]:
        logger.error(f"Google callback received for non-Google platform: {platform}")
        return RedirectResponse(
            url=f"{frontend_url}/dashboard/integrations?success=false&error=Invalid platform for Google callback"
        )
    
    logger.info(f"Google unified callback for platform: {platform}, tenant: {tenant_id}")
    
    # Get integration config
    service = IntegrationService(db)
    config = await service.get_integration_config(platform)
    logger.info(f"Config for {platform}: {config}")
    
    if not config:
        logger.error(f"No config found for platform: {platform}")
        return RedirectResponse(
            url=f"{frontend_url}/dashboard/integrations?success=false&error=Platform not configured"
        )
    
    # Use the unified Google redirect URI
    redirect_uri = f"{backend_url}/api/v1/integrations/oauth/google/callback"
    
    try:
        # Exchange code for token (platform-specific)
        token_result = await _exchange_token(
            platform, code, config, redirect_uri, state_data
        )
        
        # Unpack token result
        if len(token_result) == 7:
            access_token, refresh_token, token_expires_at, profile_data, pages, organizations, refresh_token_expires_at = token_result
        else:
            access_token, refresh_token, token_expires_at, profile_data, pages, organizations = token_result
            refresh_token_expires_at = None
        
        # Create or update integration
        integration = await service.create_or_update_integration(
            tenant_id=tenant_id,
            platform=platform,
            platform_user_id=profile_data.get("id") or profile_data.get("channel_id") or str(uuid.uuid4()),
            access_token=access_token,
            profile_data=profile_data,
            assistant_id=assistant_id,
            connected_by=user_id,
            refresh_token=refresh_token,
            token_expires_at=token_expires_at,
            refresh_token_expires_at=refresh_token_expires_at,
            pages=pages,
            organizations=organizations
        )
        
        # Clean up state
        redis_client.delete(f"oauth_state_{state}")
        
        logger.info(f"Successfully connected {platform} for tenant {tenant_id}")
        
        # For YouTube, redirect to workspace if connected from campaign (for now, just use integrations page)
        if platform == "youtube":
            return RedirectResponse(
                url=f"{frontend_url}/dashboard/integrations?success=true&platform=youtube&linked=youtube&channel_id={profile_data.get('channel_id', '')}"
            )
        
        return RedirectResponse(
            url=f"{frontend_url}/dashboard/integrations?success=true&platform={platform}&integration_id={integration.id}"
        )
    
    except Exception as e:
        logger.error(f"Error in Google unified callback for {platform}: {str(e)}", exc_info=True)
        error_message = str(e)
        if len(error_message) > 200:
            error_message = error_message[:200] + "..."
        return RedirectResponse(
            url=f"{frontend_url}/dashboard/integrations?success=false&error={error_message}"
        )


async def _exchange_token(
    platform: str,
    code: str,
    config,
    redirect_uri: str,
    state_data: dict
) -> tuple:
    """Exchange OAuth code for access token (platform-specific)"""
    async with httpx.AsyncClient() as client:
        if platform in ["facebook", "instagram"]:
            # Facebook/Instagram token exchange
            token_response = await client.post(
                "https://graph.facebook.com/v18.0/oauth/access_token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": config.client_id,
                    "client_secret": config.client_secret,
                }
            )
            token_data = token_response.json()
            
            if "error" in token_data:
                raise Exception(token_data.get("error_description", "Token exchange failed"))
            
            access_token = token_data["access_token"]
            expires_in = token_data.get("expires_in", 0)
            token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in) if expires_in else None
            
            # Get profile
            if platform == "facebook":
                profile_response = await client.get(
                    "https://graph.facebook.com/v18.0/me",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={"fields": "id,name,email,picture{url}"}
                )
                profile_data = profile_response.json()
                
                # Get pages
                pages_response = await client.get(
                    "https://graph.facebook.com/v18.0/me/accounts",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={"fields": "id,name,access_token,link,picture{url}", "limit": 100}
                )
                pages = pages_response.json().get("data", [])
                
                return access_token, None, token_expires_at, profile_data, pages, [], None
            
            else:  # Instagram
                # Get Instagram Business Account
                accounts_response = await client.get(
                    "https://graph.facebook.com/v18.0/me/accounts",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={"fields": "id,name,access_token,instagram_business_account"}
                )
                accounts_data = accounts_response.json()
                
                instagram_account = None
                for account in accounts_data.get("data", []):
                    if account.get("instagram_business_account"):
                        instagram_account = account
                        break
                
                if not instagram_account:
                    raise Exception("No Instagram Business Account found")
                
                ig_account_id = instagram_account["instagram_business_account"]["id"]
                ig_response = await client.get(
                    f"https://graph.facebook.com/v18.0/{ig_account_id}",
                    params={
                        "access_token": instagram_account["access_token"],
                        "fields": "id,username,media_count,followers_count,profile_picture_url"
                    }
                )
                profile_data = ig_response.json()
                profile_data["access_token"] = instagram_account["access_token"]
                
                return access_token, None, token_expires_at, profile_data, [], [], None
        
        elif platform == "linkedin":
            # LinkedIn requires exact redirect_uri match
            # The redirect_uri must match EXACTLY what was used in the authorization request
            # and what's registered in LinkedIn app settings (case-sensitive, no trailing slashes)
            logger.info(f"LinkedIn token exchange - redirect_uri: {redirect_uri}, client_id: {config.client_id[:10]}...")
            
            # Match requests library behavior exactly
            token_data = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,  # Must match exactly what was in auth request
                "client_id": config.client_id,
                "client_secret": config.client_secret,
            }
            
            # httpx automatically sets Content-Type when using data= dict
            # Explicitly setting it can cause issues, so let httpx handle it
            token_response = await client.post(
                "https://www.linkedin.com/oauth/v2/accessToken",
                data=token_data
            )
            
            # Check response status
            if token_response.status_code != 200:
                error_text = token_response.text
                logger.error(f"LinkedIn token exchange failed (status {token_response.status_code}): {error_text}")
                # Try to parse as JSON for better error message
                try:
                    error_data = token_response.json()
                    error_desc = error_data.get("error_description", error_data.get("error", error_text))
                    raise Exception(f"LinkedIn token exchange failed: {error_desc}")
                except:
                    raise Exception(f"LinkedIn token exchange failed: {error_text}")
            
            token_data = token_response.json()
            
            if "error" in token_data:
                error_desc = token_data.get("error_description", token_data.get("error", "Token exchange failed"))
                logger.error(f"LinkedIn OAuth error: {token_data.get('error')} - {error_desc}")
                raise Exception(f"LinkedIn OAuth error: {error_desc}")
            
            access_token = token_data["access_token"]
            expires_in = token_data.get("expires_in", 0)
            token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in) if expires_in else None
            
            # Get profile with more fields
            profile_response = await client.get(
                "https://api.linkedin.com/v2/me",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"projection": "(id,firstName,lastName,vanityName,profilePicture(displayImage~:playableStreams))"}
            )
            profile_json = profile_response.json()
            
            # Extract profile data in a more accessible format
            profile_data = {
                "id": profile_json.get("id"),
                "firstName": profile_json.get("firstName", {}).get("localized", {}).get("en_US", "") if profile_json.get("firstName") else "",
                "lastName": profile_json.get("lastName", {}).get("localized", {}).get("en_US", "") if profile_json.get("lastName") else "",
                "vanityName": profile_json.get("vanityName", ""),
                "name": f"{profile_json.get('firstName', {}).get('localized', {}).get('en_US', '') if profile_json.get('firstName') else ''} {profile_json.get('lastName', {}).get('localized', {}).get('en_US', '') if profile_json.get('lastName') else ''}".strip(),
                "username": profile_json.get("vanityName", ""),
                "display_name": f"{profile_json.get('firstName', {}).get('localized', {}).get('en_US', '') if profile_json.get('firstName') else ''} {profile_json.get('lastName', {}).get('localized', {}).get('en_US', '') if profile_json.get('lastName') else ''}".strip(),
            }
            
            # Get organizations with more details
            org_response = await client.get(
                "https://api.linkedin.com/v2/organizationAcls?q=roleAssignee&role=ADMINISTRATOR",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            org_data = org_response.json().get("elements", [])
            
            # Extract page details
            organizations = []
            for element in org_data:
                org_urn = element.get("organization", "")
                if not org_urn:
                    continue
                
                # Extract org_id from URN: "urn:li:organization:123456" -> "123456"
                org_id = org_urn.split(":")[-1]
                
                try:
                    # Get org details from LinkedIn
                    org_url = f"https://api.linkedin.com/v2/organizations/{org_id}"
                    projection = "?projection=(localizedName,vanityName,logoV2(original~:playableStreams))"
                    org_detail_response = await client.get(
                        org_url + projection,
                        headers={"Authorization": f"Bearer {access_token}"}
                    )
                    
                    if org_detail_response.status_code == 200:
                        org_detail = org_detail_response.json()
                        
                        # Extract logo URL using chained .get() calls
                        logo_url = None
                        try:
                            logo_url = (
                                org_detail.get("logoV2", {})
                                .get("original~", {})
                                .get("elements", [{}])[0]
                                .get("identifiers", [{}])[0]
                                .get("identifier")
                            )
                        except (IndexError, AttributeError, KeyError):
                            pass
                        
                        organizations.append({
                            "id": org_id,
                            "name": org_detail.get("localizedName"),
                            "vanityName": org_detail.get("vanityName", ""),
                            "logo_url": logo_url,
                            "role": element.get("role", ""),
                            "is_organization": True
                        })
                    else:
                        logger.warning(f"Could not fetch details for organization {org_id}: HTTP {org_detail_response.status_code}")
                        organizations.append({
                            "id": org_id,
                            "name": f"Organization {org_id}",
                            "role": element.get("role", ""),
                            "is_organization": True
                        })
                except Exception as e:
                    logger.warning(f"Could not fetch details for organization {org_id}: {e}")
                    organizations.append({
                        "id": org_id,
                        "name": f"Organization {org_id}",
                        "role": element.get("role", ""),
                        "is_organization": True
                    })
            
            return access_token, None, token_expires_at, profile_data, [], organizations, None
        
        elif platform == "twitter":
            code_verifier = state_data.get("code_verifier")
            if not code_verifier:
                raise Exception("Code verifier not found in state")
            
            credentials = f"{config.client_id}:{config.client_secret}"
            b64_credentials = base64.b64encode(credentials.encode()).decode()
            
            token_response = await client.post(
                "https://api.twitter.com/2/oauth2/token",
                data={
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                    "code_verifier": code_verifier
                },
                headers={
                    "Authorization": f"Basic {b64_credentials}",
                    "Content-Type": "application/x-www-form-urlencoded"
                }
            )
            token_data = token_response.json()
            
            if "error" in token_data:
                raise Exception(token_data.get("error_description", "Token exchange failed"))
            
            access_token = token_data["access_token"]
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in", 7200)  # Default 2 hours if not provided
            
            # Calculate token expiry
            token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in) if expires_in else None
            
            # Twitter refresh tokens last 6 months (approximately 180 days)
            # Only set refresh_token_expires_at if Twitter provides it in the response
            # Twitter doesn't provide refresh_token_expires_at, so we only set it if it exists in the response
            refresh_token_expires_at = None
            if refresh_token and 'refresh_token_expires_at' in token_data:
                # Twitter provided it - use it (though Twitter typically doesn't provide this)
                try:
                    refresh_token_expires_at = datetime.fromisoformat(token_data['refresh_token_expires_at'].replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    # If parsing fails, don't set it
                    refresh_token_expires_at = None
            
            # Get profile
            profile_response = await client.get(
                "https://api.twitter.com/2/users/me?user.fields=profile_image_url,name,username",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            profile_data = profile_response.json()["data"]
            
            return access_token, refresh_token, token_expires_at, profile_data, [], refresh_token_expires_at
        
        elif platform == "tiktok":
            code_verifier = state_data.get("code_verifier")
            if not code_verifier:
                raise Exception("Code verifier not found in state")
            
            token_response = await client.post(
                "https://open.tiktokapis.com/v2/oauth/token/",
                data={
                    "client_key": config.client_id,
                    "client_secret": config.client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                    "code_verifier": code_verifier
                }
            )
            token_data = token_response.json()
            
            if token_response.status_code != 200 or "error" in token_data:
                raise Exception(token_data.get("error", {}).get("message", "Token exchange failed"))
            
            access_token = token_data["access_token"]
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in", 0)
            token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in) if expires_in else None
            
            # Get profile
            profile_response = await client.get(
                "https://open.tiktokapis.com/v2/user/info/",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"fields": "open_id,union_id,display_name,avatar_url,is_verified,follower_count"}
            )
            profile_data = profile_response.json()["data"]["user"]
            profile_data["open_id"] = token_data["open_id"]
            
            return access_token, refresh_token, token_expires_at, profile_data, [], None
        
        elif platform == "google_ads":
            # Google Ads OAuth token exchange
            # Use the same redirect_uri that was used in the authorization request
            # This should match what's registered in Google OAuth app
            backend_url = settings.BACKEND_URL or 'http://localhost:8000'            
            logger.info(f"Google Ads token exchange - redirect_uri: {redirect_uri}, code present: {bool(code)}")
            
            try:
                logger.info(f"Google Ads token exchange - Request URL: https://oauth2.googleapis.com/token")
                logger.info(f"Google Ads token exchange - Redirect URI: {redirect_uri}")
                logger.info(f"Google Ads token exchange - Client ID: {config.client_id[:20]}...")
                
                token_response = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": redirect_uri,  # Must match exactly what's in Google OAuth app
                        "client_id": config.client_id,
                        "client_secret": config.client_secret,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                
                logger.info(f"Google Ads token response status: {token_response.status_code}")
                
                if token_response.status_code != 200:
                    error_text = token_response.text
                    logger.error(f"Google Ads token exchange failed - Status: {token_response.status_code}, Response: {error_text}")
                    try:
                        error_data = token_response.json()
                        error_msg = error_data.get("error_description", error_data.get("error", f"HTTP {token_response.status_code}"))
                        raise Exception(f"Token exchange failed: {error_msg}")
                    except:
                        raise Exception(f"Token exchange failed: HTTP {token_response.status_code} - {error_text}")
                
                token_data = token_response.json()
                
                if "error" in token_data:
                    error_msg = token_data.get("error_description", token_data.get("error", "Token exchange failed"))
                    logger.error(f"Google Ads token exchange error: {error_msg}, full response: {token_data}")
                    raise Exception(f"Token exchange failed: {error_msg}")
            except httpx.HTTPStatusError as e:
                logger.error(f"Google Ads token exchange HTTP error - Status: {e.response.status_code}, Response: {e.response.text}")
                raise Exception(f"Token exchange failed: HTTP {e.response.status_code}")
            except Exception as e:
                if "Token exchange failed" not in str(e):
                    logger.error(f"Google Ads token exchange error: {str(e)}")
                raise
            
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            
            if not access_token:
                logger.error(f"Google Ads token exchange - no access_token in response: {token_data}")
                raise Exception("No access_token received from Google")
            
            if not refresh_token:
                logger.warning("Google Ads token exchange - no refresh_token in response (may need to re-authenticate)")
            
            expires_in = token_data.get("expires_in", 0)
            token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in) if expires_in else None
            
            logger.info(f"Google Ads token exchange successful - access_token: {access_token[:20] if access_token else None}..., refresh_token: {'present' if refresh_token else 'missing'}")
            
            # Get user profile
            try:
                logger.info("Fetching Google user profile from userinfo API...")
                profile_response = await client.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                logger.info(f"Google userinfo response status: {profile_response.status_code}")
                
                if profile_response.status_code != 200:
                    error_text = profile_response.text
                    logger.error(f"Google userinfo API error - Status: {profile_response.status_code}, Response: {error_text}")
                    raise Exception(f"Failed to fetch user profile: HTTP {profile_response.status_code}")
                
                profile_data = profile_response.json()
                profile_data["platform"] = "google_ads"
                logger.info(f"Google user profile fetched successfully - Email: {profile_data.get('email', 'N/A')}")
            except httpx.HTTPStatusError as e:
                logger.error(f"Google userinfo API HTTP error - Status: {e.response.status_code}, Response: {e.response.text}")
                raise Exception(f"Failed to fetch user profile: HTTP {e.response.status_code}")
            except Exception as e:
                logger.error(f"Google userinfo API error: {str(e)}")
                raise
            
            # Get Google Ads customer IDs (manager accounts)
            organizations = []
            try:
                from app.utils.google_ads import get_customer_ids, get_client_ids
                
                if not refresh_token:
                    logger.error("Google Ads: No refresh_token available, cannot fetch customer IDs")
                    raise Exception("No refresh_token available for Google Ads")
                
                # Get accessible customer IDs - pass both access_token and refresh_token
                logger.info("Google Ads: Fetching customer IDs...")
                customer_ids = await get_customer_ids(refresh_token, access_token)
                
                logger.info(f"Google Ads: get_customer_ids returned {len(customer_ids) if customer_ids else 0} customer IDs")
                
                if customer_ids:
                    logger.info(f"Google Ads: Found {len(customer_ids)} customer IDs")
                    
                    # Process each customer ID
                    for customer_id in customer_ids:
                        # Ensure customer_id is a string and validate it's 10 digits
                        customer_id_str = str(customer_id).strip()
                        if not customer_id_str.isdigit() or len(customer_id_str) != 10:
                            logger.error(f"Invalid customer_id format from Google Ads API: {customer_id} (length: {len(customer_id_str)})")
                            continue
                        
                        customer_info = {
                            "customer_id": customer_id_str,  # Store as string to ensure correct format
                            "type": "manager" if customer_id_str == settings.GOOGLE_ADS_MANAGER_CUSTOMER_ID else "client"
                        }
                        
                        # Try to fetch client IDs for this account to determine if it's a manager account
                        # If it has client accounts, it's a manager account
                        try:
                            client_ids = await get_client_ids(refresh_token, customer_id_str)
                            if client_ids and len(client_ids) > 0:
                                # This account has clients, so it's a manager account
                                customer_info["type"] = "manager"
                                customer_info["client_ids"] = client_ids
                                logger.info(f"Google Ads: Account {customer_id_str} is a manager with {len(client_ids)} client accounts")
                            else:
                                logger.info(f"Google Ads: Account {customer_id_str} has no client accounts")
                        except Exception as e:
                            # If we can't fetch client IDs, it might not be a manager account or there's an error
                            logger.debug(f"Could not fetch client IDs for account {customer_id_str}: {e}")
                            # Keep the type as is (manager if matches configured, otherwise client)
                        
                        organizations.append(customer_info)
                    
                    # No need to send manager link requests - if user is connected to a manager account,
                    # we can already access client accounts under that manager
                
                profile_data["has_google_ads_access"] = True
                profile_data["customer_ids"] = customer_ids
                logger.info(f"Google Ads token exchange successful - found {len(customer_ids)} customer IDs")
            except ImportError:
                logger.warning("Google Ads API library not installed. Customer IDs will not be fetched.")
                profile_data["has_google_ads_access"] = True
                profile_data["note"] = "Install google-ads library to fetch customer IDs"
            except Exception as e:
                logger.warning(f"Could not fetch Google Ads customer IDs: {str(e)}")
                profile_data["has_google_ads_access"] = True
            
            return access_token, refresh_token, token_expires_at, profile_data, [], organizations, None
        
        elif platform == "google_analytics":
            # Google Analytics OAuth token exchange
            # For Google Analytics, we can use the new endpoint or legacy if configured
            backend_url = settings.BACKEND_URL or 'http://localhost:8000'
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": config.client_id,
                    "client_secret": config.client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            token_data = token_response.json()
            
            if "error" in token_data:
                raise Exception(token_data.get("error_description", "Token exchange failed"))
            
            access_token = token_data["access_token"]
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in", 0)
            token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in) if expires_in else None
            
            # Get user profile
            profile_response = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            profile_data = profile_response.json()
            profile_data["platform"] = "google_analytics"
            
            # Get Google Analytics accounts
            organizations = []
            try:
                # Use Google Analytics Management API to get accounts
                accounts_response = await client.get(
                    "https://www.googleapis.com/analytics/v3/management/accounts",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                accounts_data = accounts_response.json()
                
                if "items" in accounts_data:
                    for account in accounts_data["items"]:
                        # Get properties for each account
                        properties_response = await client.get(
                            f"https://www.googleapis.com/analytics/v3/management/accounts/{account['id']}/webproperties",
                            headers={"Authorization": f"Bearer {access_token}"}
                        )
                        properties_data = properties_response.json()
                        
                        account_info = {
                            "id": account.get("id"),
                            "name": account.get("name"),
                            "properties": properties_data.get("items", [])
                        }
                        organizations.append(account_info)
                
                logger.info(f"Google Analytics: Found {len(organizations)} accounts")
            except Exception as e:
                logger.warning(f"Could not fetch Google Analytics accounts: {str(e)}")
            
            return access_token, refresh_token, token_expires_at, profile_data, [], organizations, None
        
        elif platform == "meta_ads":
            # Meta Ads uses Facebook OAuth
            token_response = await client.post(
                "https://graph.facebook.com/v18.0/oauth/access_token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": config.client_id,
                    "client_secret": config.client_secret,
                }
            )
            token_data = token_response.json()
            
            if "error" in token_data:
                raise Exception(token_data.get("error_description", "Token exchange failed"))
            
            access_token = token_data["access_token"]
            expires_in = token_data.get("expires_in", 0)
            token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in) if expires_in else None
            
            # Get profile
            profile_response = await client.get(
                "https://graph.facebook.com/v18.0/me",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"fields": "id,name,email,picture{url}"}
            )
            profile_data = profile_response.json()
            profile_data["platform"] = "meta_ads"
            
            # Get ad accounts (active accounts only)
            ad_accounts_response = await client.get(
                "https://graph.facebook.com/v18.0/me/adaccounts",
                headers={"Authorization": f"Bearer {access_token}"},
                params={
                    "fields": "id,name,account_status,business,currency,timezone_name",
                    "limit": 100
                }
            )
            ad_accounts_data = ad_accounts_response.json().get("data", [])
            
            # Filter active accounts (account_status == 1)
            active_ad_accounts = [
                {
                    "id": account.get("id"),
                    "name": account.get("name", ""),
                    "ad_account_id": account.get("id"),  # Use id as ad_account_id
                    "account_status": account.get("account_status"),
                    "business_id": account.get("business", {}).get("id") if account.get("business") else None,
                    "currency": account.get("currency"),
                    "timezone_name": account.get("timezone_name")
                }
                for account in ad_accounts_data
                if account.get("account_status") == 1  # Active account
            ]
            
            if not active_ad_accounts:
                raise Exception("No active ad accounts found")
            
            # Get pages
            pages_response = await client.get(
                "https://graph.facebook.com/v18.0/me/accounts",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"fields": "id,name", "limit": 100}
            )
            pages_data = pages_response.json().get("data", [])
            pages = [{"id": page.get("id"), "name": page.get("name")} for page in pages_data]
            
            # Store ad accounts in organizations field and pages in pages field
            # Store pages also in profile_data for easy access
            profile_data["ad_accounts"] = active_ad_accounts
            profile_data["pages"] = pages
            
            return access_token, None, token_expires_at, profile_data, pages, active_ad_accounts, None
        
        elif platform == "youtube":
            # YouTube OAuth token exchange (uses Google OAuth)
            backend_url = settings.BACKEND_URL or 'http://localhost:8000'
            google_redirect_uri = f"{backend_url}/api/v1/integrations/oauth/google/callback"
            
            logger.info(f"YouTube token exchange - redirect_uri: {google_redirect_uri}")
            
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": google_redirect_uri,
                    "client_id": config.client_id,
                    "client_secret": config.client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            token_data = token_response.json()
            
            if "error" in token_data:
                error_msg = token_data.get("error_description", token_data.get("error", "Token exchange failed"))
                logger.error(f"YouTube token exchange error: {error_msg}")
                raise Exception(f"Token exchange failed: {error_msg}")
            
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in", 0)
            token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in) if expires_in else None
            
            if not access_token:
                raise Exception("No access_token received from Google")
            
            logger.info(f"YouTube token exchange successful - refresh_token: {'present' if refresh_token else 'missing'}")
            
            # Get user profile
            profile_response = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            profile_data = profile_response.json()
            profile_data["platform"] = "youtube"
            
            # Get YouTube channel info
            organizations = []
            try:
                channel_response = await client.get(
                    "https://www.googleapis.com/youtube/v3/channels",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={
                        "part": "snippet,contentDetails,statistics",
                        "mine": "true"
                    }
                )
                channel_data = channel_response.json()
                
                if "items" in channel_data and len(channel_data["items"]) > 0:
                    channel = channel_data["items"][0]
                    channel_info = {
                        "channel_id": channel.get("id"),
                        "title": channel.get("snippet", {}).get("title"),
                        "description": channel.get("snippet", {}).get("description"),
                        "thumbnail": channel.get("snippet", {}).get("thumbnails", {}).get("default", {}).get("url"),
                        "subscriber_count": channel.get("statistics", {}).get("subscriberCount"),
                        "video_count": channel.get("statistics", {}).get("videoCount"),
                        "view_count": channel.get("statistics", {}).get("viewCount"),
                    }
                    organizations.append(channel_info)
                    profile_data["channel"] = channel_info
                    profile_data["channel_id"] = channel.get("id")
                    logger.info(f"YouTube: Found channel '{channel_info['title']}' (ID: {channel_info['channel_id']})")
                else:
                    logger.warning("YouTube: No channel found for this account")
            except Exception as e:
                logger.warning(f"Could not fetch YouTube channel info: {str(e)}")
            
            return access_token, refresh_token, token_expires_at, profile_data, [], organizations, None
        
        else:
            raise Exception(f"Unsupported platform: {platform}")


# Twitter OAuth 1.0a endpoints for media uploads
@router.get("/oauth/twitter/oauth1/init")
async def init_twitter_oauth1(
    redirect: bool = Query(False, description="If true, redirect directly. If false, return JSON with URL."),
    current_user: User = Depends(get_current_user),
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Initialize Twitter OAuth 1.0a flow to get tokens for media uploads.
    Twitter's media upload endpoints require OAuth 1.0a, not OAuth 2.0.
    User must have completed OAuth 2.0 flow first.
    """
    try:
        try:
            from requests_oauthlib import OAuth1Session
        except ImportError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OAuth 1.0a library not installed. Install requests-oauthlib to enable media uploads."
            )
        
        # Get OAuth 1.0a credentials from settings (separate from OAuth 2.0 credentials)
        # These should be the API Key and API Secret from Twitter Developer Portal
        api_key = settings.TWITTER_API_KEY
        api_secret = settings.TWITTER_API_SECRET
        
        # Fallback to OAuth 2.0 credentials if OAuth 1.0a credentials not set
        if not api_key or not api_secret:
            logger.warning("[Twitter OAuth 1.0a] TWITTER_API_KEY or TWITTER_API_SECRET not set, falling back to OAuth 2.0 credentials")
            service = IntegrationService(db)
            config = await service.get_integration_config("twitter")
            if config:
                api_key = config.client_id
                api_secret = config.client_secret
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Twitter OAuth 1.0a credentials not configured. Please set TWITTER_API_KEY and TWITTER_API_SECRET in .env file."
                )
        
        if not api_key or not api_secret:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Twitter OAuth 1.0a credentials not configured. Please set TWITTER_API_KEY and TWITTER_API_SECRET in .env file."
            )
        
        # Check if user has existing Twitter OAuth 2.0 integration
        from app.models.integration import SocialIntegration
        from sqlalchemy import select
        
        result = await db.execute(
            select(SocialIntegration).where(
                SocialIntegration.tenant_id == current_tenant.id,
                SocialIntegration.platform == "twitter",
                SocialIntegration.is_active == True
            )
        )
        integration = result.scalar_one_or_none()
        
        if not integration:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Twitter account not found. Please connect with OAuth 2.0 first."
            )
        
        # Step 1: Get request token
        backend_url = settings.BACKEND_URL or 'http://localhost:8000'
        oauth_callback = f"{backend_url}/api/v1/integrations/oauth/twitter/oauth1/callback"
        
        # Use OAuth 1.0a credentials (API Key and API Secret)
        oauth1_session = OAuth1Session(
            api_key,  # Consumer Key (API Key)
            client_secret=api_secret  # Consumer Secret (API Secret)
        )
        
        request_token_url = "https://api.twitter.com/oauth/request_token"
        
        # Log callback URL for debugging (don't log full credentials)
        logger.info(f"[Twitter OAuth 1.0a] Using callback URL: {oauth_callback}")
        logger.info(f"[Twitter OAuth 1.0a] Using API Key (first 10 chars): {api_key[:10] if api_key else 'None'}...")
        
        try:
            # Fetch request token with callback
            # IMPORTANT: The callback URL must be registered in Twitter Developer Portal:
            # 1. Go to https://developer.twitter.com/en/portal/dashboard
            # 2. Select your app
            # 3. Go to Settings > User authentication settings
            # 4. Add the callback URL to "Callback URI / Redirect URL"
            # 5. Ensure "App permissions" is set to "Read and write"
            # 6. Save changes
            fetch_response = oauth1_session.fetch_request_token(
                request_token_url,
                data={'oauth_callback': oauth_callback}
            )
            
            oauth_token = fetch_response.get('oauth_token')
            oauth_token_secret = fetch_response.get('oauth_token_secret')
            
            if not oauth_token or not oauth_token_secret:
                logger.error("[Twitter OAuth 1.0a] Failed to get request tokens")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to get OAuth 1.0a request tokens"
                )
            
            # Store request tokens in Redis
            oauth1_state_key = f"twitter_oauth1_{oauth_token}"
            oauth1_cache_data = {
                "user_id": str(current_user.id),
                "tenant_id": str(current_tenant.id),
                "integration_id": str(integration.id),
                "oauth_token_secret": oauth_token_secret,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            redis_client = get_redis_client()
            if redis_client:
                redis_client.setex(
                    oauth1_state_key,
                    600,  # 10 minutes
                    json.dumps(oauth1_cache_data)
                )
            
            # Step 2: Get authorization URL
            authorization_url = oauth1_session.authorization_url("https://api.twitter.com/oauth/authorize")
            
            logger.info(f"[Twitter OAuth 1.0a] Request token obtained, authorization URL: {authorization_url}")
            
            # If redirect parameter is true, redirect directly (for direct browser navigation)
            # Otherwise, return JSON with URL (for API calls)
            if redirect:
                return RedirectResponse(url=authorization_url)
            else:
                return JSONResponse(content={"url": authorization_url})
            
        except HTTPException:
            raise
        except Exception as e:
            error_msg = str(e)
            logger.error(f"[Twitter OAuth 1.0a] Error getting request token: {error_msg}", exc_info=True)
            
            # Check if it's an authentication error (401)
            if "401" in error_msg or "Could not authenticate" in error_msg or "code 32" in error_msg:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Twitter OAuth 1.0a authentication failed. "
                        f"This usually means:\n"
                        f"1. The callback URL '{oauth_callback}' is not registered in your Twitter app settings.\n"
                        f"2. Go to Twitter Developer Portal > Your App > Settings > User authentication settings\n"
                        f"3. Add '{oauth_callback}' to 'Callback URI / Redirect URL'\n"
                        f"4. Ensure 'App permissions' includes 'Read and write' for OAuth 1.0a\n"
                        f"5. Save changes and try again.\n\n"
                        f"Original error: {error_msg}"
                    )
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to initiate OAuth 1.0a flow: {error_msg}"
                )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Twitter OAuth 1.0a] Error in init: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OAuth 1.0a initialization failed: {str(e)}"
        )


@router.get("/oauth/twitter/oauth1/callback")
async def twitter_oauth1_callback(
    oauth_token: Optional[str] = Query(None),
    oauth_verifier: Optional[str] = Query(None),
    denied: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Handle Twitter OAuth 1.0a callback to get access tokens for media uploads.
    """
    frontend_url = settings.FRONTEND_URL or 'http://localhost:3000'
    
    if denied:
        logger.warning("[Twitter OAuth 1.0a] User denied authorization")
        return RedirectResponse(
            url=f"{frontend_url}/dashboard/integrations?success=false&error=OAuth 1.0a authorization denied"
        )
    
    if not oauth_token or not oauth_verifier:
        return RedirectResponse(
            url=f"{frontend_url}/dashboard/integrations?success=false&error=Missing oauth_token or oauth_verifier"
        )
    
    try:
        try:
            from requests_oauthlib import OAuth1Session
        except ImportError:
            return RedirectResponse(
                url=f"{frontend_url}/dashboard/integrations?success=false&error=OAuth 1.0a library not installed"
            )
        
        # Get cached data
        redis_client = get_redis_client()
        oauth1_state_key = f"twitter_oauth1_{oauth_token}"
        
        if not redis_client:
            return RedirectResponse(
                url=f"{frontend_url}/dashboard/integrations?success=false&error=Redis not available"
            )
        
        cached_data_str = redis_client.get(oauth1_state_key)
        if not cached_data_str:
            return RedirectResponse(
                url=f"{frontend_url}/dashboard/integrations?success=false&error=Invalid or expired OAuth 1.0a request"
            )
        
        oauth1_data = json.loads(cached_data_str)
        integration_id = oauth1_data.get('integration_id')
        oauth_token_secret = oauth1_data.get('oauth_token_secret')
        
        # Get integration
        from app.models.integration import SocialIntegration
        from sqlalchemy import select
        from uuid import UUID
        
        result = await db.execute(
            select(SocialIntegration).where(
                SocialIntegration.id == UUID(integration_id) if isinstance(integration_id, str) else integration_id
            )
        )
        integration = result.scalar_one_or_none()
        
        if not integration:
            return RedirectResponse(
                url=f"{frontend_url}/dashboard/integrations?success=false&error=Integration not found"
            )
        
        # Get OAuth 1.0a credentials from settings
        api_key = settings.TWITTER_API_KEY
        api_secret = settings.TWITTER_API_SECRET
        
        # Fallback to OAuth 2.0 credentials if OAuth 1.0a credentials not set
        if not api_key or not api_secret:
            logger.warning("[Twitter OAuth 1.0a] TWITTER_API_KEY or TWITTER_API_SECRET not set, falling back to OAuth 2.0 credentials")
            service = IntegrationService(db)
            config = await service.get_integration_config("twitter")
            if config:
                api_key = config.client_id
                api_secret = config.client_secret
            else:
                return RedirectResponse(
                    url=f"{frontend_url}/dashboard/integrations?success=false&error=Twitter OAuth 1.0a credentials not configured"
                )
        
        if not api_key or not api_secret:
            return RedirectResponse(
                url=f"{frontend_url}/dashboard/integrations?success=false&error=Twitter OAuth 1.0a credentials not configured"
            )
        
        # Step 3: Exchange request token for access token
        oauth1_session = OAuth1Session(
            api_key,
            client_secret=api_secret,
            resource_owner_key=oauth_token,
            resource_owner_secret=oauth_token_secret,
            verifier=oauth_verifier
        )
        
        access_token_url = "https://api.twitter.com/oauth/access_token"
        oauth_tokens = oauth1_session.fetch_access_token(access_token_url)
        
        oauth1_access_token = oauth_tokens.get('oauth_token')
        oauth1_access_token_secret = oauth_tokens.get('oauth_token_secret')
        
        if not oauth1_access_token or not oauth1_access_token_secret:
            logger.error("[Twitter OAuth 1.0a] Failed to get access tokens")
            return RedirectResponse(
                url=f"{frontend_url}/dashboard/integrations?success=false&error=Failed to get OAuth 1.0a access tokens"
            )
        
        # Store OAuth 1.0a tokens in integration meta_data
        meta_data = integration.meta_data or {}
        meta_data.update({
            'oauth1_token': oauth1_access_token,
            'oauth1_token_secret': oauth1_access_token_secret,
            'oauth1_configured': True,
            'oauth1_configured_at': datetime.now(timezone.utc).isoformat()
        })
        
        # Update integration
        from sqlalchemy import update
        update_stmt = (
            update(SocialIntegration)
            .where(SocialIntegration.id == integration.id)
            .values(meta_data=meta_data)
        )
        await db.execute(update_stmt)
        await db.commit()
        
        # Clean up cache
        redis_client.delete(oauth1_state_key)
        
        logger.info(f"[Twitter OAuth 1.0a] Access tokens obtained and stored for integration {integration_id}")
        return RedirectResponse(
            url=f"{frontend_url}/dashboard/integrations?success=true&platform=twitter&oauth1=complete"
        )
        
    except Exception as e:
        logger.error(f"[Twitter OAuth 1.0a] Error in callback: {str(e)}", exc_info=True)
        return RedirectResponse(
            url=f"{frontend_url}/dashboard/integrations?success=false&error=OAuth 1.0a callback failed: {str(e)}"
        )

