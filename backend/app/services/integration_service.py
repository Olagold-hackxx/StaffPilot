"""
Integration service - handles social media platform connections
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional, Dict
from uuid import UUID
from datetime import datetime, timedelta, timezone
from app.models.integration import SocialIntegration, IntegrationConfig
from app.models.capability import Capability
from app.utils.errors import AssistantNotFoundError
from app.utils.logger import logger


class IntegrationService:
    """Service for managing social media integrations"""
    
    SUPPORTED_PLATFORMS = [
        "facebook",
        "instagram", 
        "linkedin",
        "twitter",
        "tiktok",
        "google_ads",
        "google_analytics",
        "youtube",
        "meta_ads"
    ]
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_integration_config(self, platform: str) -> Optional[IntegrationConfig]:
        """
        Get OAuth configuration for a platform
        First checks environment variables, then falls back to database
        """
        from app.config import settings
        
        # Map platform names to config keys
        platform_config_map = {
            "facebook": ("FACEBOOK_APP_ID", "FACEBOOK_APP_SECRET"),
            "instagram": ("INSTAGRAM_APP_ID", "INSTAGRAM_APP_SECRET"),
            "linkedin": ("LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET"),
            "tiktok": ("TIKTOK_CLIENT_ID", "TIKTOK_CLIENT_SECRET"),
            "twitter": ("TWITTER_CLIENT_ID", "TWITTER_CLIENT_SECRET"),
            "google_ads": ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"),
            "google_analytics": ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"),
            "youtube": ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"),
            "meta_ads": ("META_ADS_APP_ID", "META_ADS_APP_SECRET"),
        }
        
        # Check environment variables first
        if platform in platform_config_map:
            client_id_key, client_secret_key = platform_config_map[platform]
            client_id = getattr(settings, client_id_key, None)
            client_secret = getattr(settings, client_secret_key, None)
            
            if client_id and client_secret:
                # Create a config object from env vars
                config = IntegrationConfig(
                    platform=platform,
                    client_id=client_id,
                    client_secret=client_secret,
                    is_enabled=True
                )
                # Set default URLs based on platform
                if platform in ["facebook", "instagram"]:
                    config.authorization_url = "https://www.facebook.com/v18.0/dialog/oauth"
                    config.token_url = "https://graph.facebook.com/v18.0/oauth/access_token"
                    config.api_base_url = "https://graph.facebook.com/v18.0"
                elif platform == "linkedin":
                    config.authorization_url = "https://www.linkedin.com/oauth/v2/authorization"
                    config.token_url = "https://www.linkedin.com/oauth/v2/accessToken"
                    config.api_base_url = "https://api.linkedin.com/v2"
                elif platform == "twitter":
                    config.authorization_url = "https://twitter.com/i/oauth2/authorize"
                    config.token_url = "https://api.twitter.com/2/oauth2/token"
                    config.api_base_url = "https://api.twitter.com/2"
                elif platform == "tiktok":
                    config.authorization_url = "https://www.tiktok.com/v2/auth/authorize/"
                    config.token_url = "https://open.tiktokapis.com/v2/oauth/token/"
                    config.api_base_url = "https://open.tiktokapis.com/v2"
                elif platform in ["google_ads", "google_analytics", "youtube"]:
                    config.authorization_url = "https://accounts.google.com/o/oauth2/v2/auth"
                    config.token_url = "https://oauth2.googleapis.com/token"
                    if platform == "google_ads":
                        config.api_base_url = "https://googleads.googleapis.com/v16"
                    elif platform == "google_analytics":
                        config.api_base_url = "https://analyticsreporting.googleapis.com/v4"
                    else:  # youtube
                        config.api_base_url = "https://www.googleapis.com/youtube/v3"
                elif platform == "meta_ads":
                    config.authorization_url = "https://www.facebook.com/v18.0/dialog/oauth"
                    config.token_url = "https://graph.facebook.com/v18.0/oauth/access_token"
                    config.api_base_url = "https://graph.facebook.com/v18.0"
                
                return config
        
        # Fall back to database
        result = await self.db.execute(
            select(IntegrationConfig).where(
                IntegrationConfig.platform == platform,
                IntegrationConfig.is_enabled == True
            )
        )
        return result.scalar_one_or_none()
    
    async def get_integration(
        self,
        tenant_id: UUID,
        integration_id: UUID
    ) -> SocialIntegration:
        """Get integration by ID"""
        result = await self.db.execute(
            select(SocialIntegration).where(
                SocialIntegration.id == integration_id,
                SocialIntegration.tenant_id == tenant_id
            )
        )
        integration = result.scalar_one_or_none()
        
        if not integration:
            raise ValueError(f"Integration {integration_id} not found")
        
        return integration
    
    async def list_integrations(
        self,
        tenant_id: UUID,
        assistant_id: Optional[UUID] = None,
        platform: Optional[str] = None
    ) -> List[SocialIntegration]:
        """List integrations for a tenant"""
        query = select(SocialIntegration).where(
            SocialIntegration.tenant_id == tenant_id
        )
        
        if assistant_id:
            query = query.where(SocialIntegration.assistant_id == assistant_id)
        
        if platform:
            query = query.where(SocialIntegration.platform == platform)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_platform_status(
        self,
        tenant_id: UUID,
        assistant_id: Optional[UUID] = None
    ) -> Dict[str, Dict]:
        """Get connection status for all platforms"""
        integrations = await self.list_integrations(
            tenant_id=tenant_id,
            assistant_id=assistant_id
        )
        
        # Create a map of platform -> integration
        platform_map = {
            integration.platform: integration
            for integration in integrations
            if integration.is_active
        }
        
        # Build status for each supported platform
        status = {}
        for platform in self.SUPPORTED_PLATFORMS:
            integration = platform_map.get(platform)
            status[platform] = {
                "is_connected": integration is not None,
                "integration_id": integration.id if integration else None,
                "platform_username": integration.platform_username if integration else None,
                "platform_name": integration.platform_name if integration else None,
                "connected_at": integration.created_at if integration else None,
                "is_active": integration.is_active if integration else False
            }
        
        return status
    
    async def create_or_update_integration(
        self,
        tenant_id: UUID,
        platform: str,
        platform_user_id: str,
        access_token: str,
        profile_data: Dict,
        assistant_id: Optional[UUID] = None,
        connected_by: Optional[UUID] = None,
        refresh_token: Optional[str] = None,
        token_expires_at: Optional[datetime] = None,
        refresh_token_expires_at: Optional[datetime] = None,
        pages: Optional[List[Dict]] = None,
        organizations: Optional[List[Dict]] = None
    ) -> SocialIntegration:
        """Create or update a social media integration"""
        # Check if integration already exists
        result = await self.db.execute(
            select(SocialIntegration).where(
                SocialIntegration.tenant_id == tenant_id,
                SocialIntegration.platform == platform,
                SocialIntegration.platform_user_id == platform_user_id
            )
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            # Update existing
            existing.access_token = access_token
            existing.refresh_token = refresh_token
            existing.profile_data = profile_data
            existing.token_expires_at = token_expires_at
            if refresh_token_expires_at:
                existing.refresh_token_expires_at = refresh_token_expires_at
            existing.pages = pages or []
            existing.organizations = organizations or []
            existing.platform_username = profile_data.get("username") or profile_data.get("vanityName") or profile_data.get("name")
            existing.platform_name = profile_data.get("display_name") or profile_data.get("name") or profile_data.get("firstName") or ""
            existing.is_active = True
            existing.last_used_at = datetime.now(timezone.utc)
            # Update assistant_id if provided (allows reassigning integrations)
            if assistant_id:
                existing.assistant_id = assistant_id
            
            await self.db.commit()
            await self.db.refresh(existing)
            
            # Update capabilities that require this platform
            await self._update_capability_integrations(tenant_id, assistant_id, platform)
            
            logger.info(f"Updated integration {existing.id} for platform {platform}")
            return existing
        
        # Create new
        integration = SocialIntegration(
            tenant_id=tenant_id,
            assistant_id=assistant_id,
            platform=platform,
            platform_user_id=platform_user_id,
            platform_username=profile_data.get("username") or profile_data.get("vanityName") or profile_data.get("name") or None,
            platform_name=profile_data.get("display_name") or profile_data.get("name") or profile_data.get("firstName") or None,
            profile_data=profile_data,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expires_at=token_expires_at,
            refresh_token_expires_at=refresh_token_expires_at,
            pages=pages or [],
            organizations=organizations or [],
            connected_by=connected_by,
            is_active=True
        )
        
        self.db.add(integration)
        await self.db.commit()
        await self.db.refresh(integration)
        
        # Update capabilities that require this platform
        await self._update_capability_integrations(tenant_id, assistant_id, platform)
        
        logger.info(f"Created integration {integration.id} for platform {platform}")
        return integration
    
    async def disconnect_integration(
        self,
        tenant_id: UUID,
        integration_id: UUID
    ) -> bool:
        """Disconnect (deactivate) an integration"""
        integration = await self.get_integration(tenant_id, integration_id)
        integration.is_active = False
        await self.db.commit()
        
        logger.info(f"Disconnected integration {integration_id}")
        
        # Update capabilities after disconnection
        if integration.assistant_id:
            await self._update_capability_integrations(
                tenant_id, 
                integration.assistant_id, 
                integration.platform
            )
        
        return True
    
    async def delete_integration(
        self,
        tenant_id: UUID,
        integration_id: UUID
    ) -> bool:
        """Permanently delete an integration"""
        integration = await self.get_integration(tenant_id, integration_id)
        await self.db.delete(integration)
        await self.db.commit()
        
        logger.info(f"Deleted integration {integration_id}")
        
        # Update capabilities after disconnection
        if integration.assistant_id:
            await self._update_capability_integrations(
                tenant_id, 
                integration.assistant_id, 
                integration.platform
            )
        
        return True
    
    async def set_default_page(
        self,
        tenant_id: UUID,
        integration_id: UUID,
        page_id: str
    ) -> SocialIntegration:
        """
        Set the default page/organization for an integration
        
        Args:
            tenant_id: Tenant UUID
            integration_id: Integration UUID
            page_id: Page/Organization ID to set as default
        
        Returns:
            Updated integration
        """
        integration = await self.get_integration(tenant_id, integration_id)
        
        # Validate that the page_id exists in pages or organizations
        platform = integration.platform
        page_found = False
        
        if platform in ["facebook", "instagram"]:
            # Check in pages array
            if integration.pages:
                for page in integration.pages if isinstance(integration.pages, list) else []:
                    if str(page.get("id")) == str(page_id) or str(page.get("page_id")) == str(page_id):
                        page_found = True
                        break
        elif platform in ["linkedin", "google_ads", "google_analytics", "meta_ads"]:
            # Check in organizations array
            if integration.organizations:
                for org in integration.organizations if isinstance(integration.organizations, list) else []:
                    # LinkedIn uses: id, entity_id, organization_id
                    # Google Ads uses: customer_id
                    # Google Analytics uses: account_id
                    # Meta Ads uses: ad_account_id
                    if (str(org.get("id")) == str(page_id) or 
                        str(org.get("entity_id")) == str(page_id) or 
                        str(org.get("organization_id")) == str(page_id) or
                        str(org.get("customer_id")) == str(page_id) or
                        str(org.get("account_id")) == str(page_id) or
                        str(org.get("ad_account_id")) == str(page_id)):
                        page_found = True
                        break
                    
                    # For Google Ads: Also check if page_id is a client_id in manager account's client_ids
                    if platform == "google_ads" and org.get("type") == "manager":
                        client_ids = org.get("client_ids", [])
                        if isinstance(client_ids, list):
                            client_id_strs = [str(cid).strip() for cid in client_ids]
                            if str(page_id).strip() in client_id_strs:
                                page_found = True
                                break
        
        if not page_found:
            raise ValueError(f"Page/Organization with ID {page_id} not found in integration")
        
        # Store default page in meta_data
        if not integration.meta_data:
            integration.meta_data = {}
        
        integration.meta_data["default_page_id"] = str(page_id)
        await self.db.commit()
        await self.db.refresh(integration)
        
        logger.info(f"Set default page {page_id} for integration {integration_id}")
        return integration
    
    async def get_default_page(
        self,
        integration: SocialIntegration
    ) -> Optional[Dict]:
        """
        Get the default page/organization for an integration
        
        Args:
            integration: Integration object
        
        Returns:
            Default page/organization dict or None
        """
        if not integration.meta_data or "default_page_id" not in integration.meta_data:
            return None
        
        default_page_id = integration.meta_data.get("default_page_id")
        platform = integration.platform
        
        if platform in ["facebook", "instagram"]:
            # Find in pages array
            if integration.pages:
                for page in integration.pages if isinstance(integration.pages, list) else []:
                    if str(page.get("id")) == str(default_page_id) or str(page.get("page_id")) == str(default_page_id):
                        return page
        elif platform == "linkedin":
            # Find in organizations array
            if integration.organizations:
                for org in integration.organizations if isinstance(integration.organizations, list) else []:
                    if str(org.get("id")) == str(default_page_id) or str(org.get("entity_id")) == str(default_page_id) or str(org.get("organization_id")) == str(default_page_id):
                        return org
        
        return None
    
    async def _update_capability_integrations(
        self,
        tenant_id: UUID,
        assistant_id: Optional[UUID],
        platform: str
    ):
        """Update capability integration counts when integrations are added/removed"""
        if not assistant_id:
            return
        
        try:
            from app.services.capability_service import CapabilityService
            capability_service = CapabilityService(self.db)
            
            # Get all capabilities for this assistant
            capabilities = await capability_service.get_capabilities_for_assistant(assistant_id)
            
            for capability in capabilities:
                required_platforms = capability.integrations_required or []
                
                # Check if this capability requires this platform
                if platform not in required_platforms:
                    continue
                
                # Count connected integrations for required platforms
                connected_count = 0
                for req_platform in required_platforms:
                    result = await self.db.execute(
                        select(SocialIntegration).where(
                            SocialIntegration.tenant_id == tenant_id,
                            SocialIntegration.assistant_id == assistant_id,
                            SocialIntegration.platform == req_platform,
                            SocialIntegration.is_active == True
                        )
                    )
                    integrations = result.scalars().all()
                    if integrations:
                        connected_count += 1
                
                # Update capability
                # At least one required integration must be connected
                new_status = "active" if connected_count > 0 else "configuring"
                if connected_count >= len(required_platforms):
                    # All required integrations connected
                    new_status = "active"
                
                await capability_service.update_capability_status(
                    capability_id=capability.id,
                    status=new_status,
                    integrations_connected=connected_count
                )
                
                logger.info(
                    f"Updated capability {capability.id}: "
                    f"{connected_count}/{len(required_platforms)} integrations connected"
                )
        except Exception as e:
            logger.error(f"Error updating capability integrations: {str(e)}")

