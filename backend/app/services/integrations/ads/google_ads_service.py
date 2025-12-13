"""
Google Ads Campaign Service - Performance Max Campaigns
"""
import asyncio
import base64
import requests
from typing import Dict, Any, Optional, List
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from app.config import settings
from app.utils.logger import logger


GOOGLE_ADS_LIBRARY_ERROR = "google-ads library not installed. Install with: pip install google-ads"


class GoogleAdsCampaignService:
    """Service for creating and managing Google Ads Performance Max campaigns"""
    
    def __init__(self, refresh_token: str, login_customer_id: str, client_id: Optional[str] = None):
        """
        Initialize Google Ads Campaign Service
        
        Args:
            refresh_token: OAuth refresh token
            login_customer_id: Manager account customer ID (10 digits) - used for authentication
            client_id: Client account customer ID (10 digits) - where campaigns are created. 
                      If None, uses login_customer_id
        """
        self.refresh_token = refresh_token
        self.login_customer_id = self._validate_customer_id(login_customer_id, "login_customer_id")
        self.client_id = self._validate_customer_id(client_id or login_customer_id, "client_id")
    
    def _validate_customer_id(self, customer_id: Optional[str], field_name: str = "customer_id") -> str:
        """Validate that customer_id is exactly 10 digits as a string."""
        if not customer_id:
            raise ValueError(f"Google Ads {field_name} is required but not provided")
        
        customer_id_str = str(customer_id).strip()
        
        if "/" in customer_id_str:
            customer_id_str = customer_id_str.split("/")[-1]
        
        if customer_id_str.isdigit() and len(customer_id_str) == 10:
            return customer_id_str
        
        digits_only = ''.join(filter(str.isdigit, customer_id_str))
        raise ValueError(
            f"Google Ads {field_name} must be exactly 10 digits. "
            f"Got: {customer_id} ({len(digits_only)} digits: {digits_only}). "
            f"Please reconnect your Google Ads account."
        )
    
    def _get_client(self):
        """Get Google Ads client"""
        try:
            from google.ads.googleads.client import GoogleAdsClient
            
            developer_token = settings.GOOGLE_ADS_DEVELOPER_TOKEN
            logger.info(f"Google Ads client config - login_customer_id: {self.login_customer_id}, client_id: {self.client_id}")
            logger.info(f"Developer token in config: {bool(developer_token)}")
            
            client_config = {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "developer_token": developer_token,
                "refresh_token": self.refresh_token,
                "login_customer_id": str(self.login_customer_id),
                "use_proto_plus": True,
            }
            
            return GoogleAdsClient.load_from_dict(client_config)
        except ImportError:
            logger.error(GOOGLE_ADS_LIBRARY_ERROR)
            raise ImportError(GOOGLE_ADS_LIBRARY_ERROR)
        except Exception as e:
            logger.error(f"Error creating Google Ads client: {e}")
            raise
    
    async def create_performance_max_campaign(
        self,
        name: str,
        budget_amount: float,
        start_date: date,
        end_date: Optional[date] = None,
        final_url: str = "",
        headlines: List[str] = None,
        descriptions: List[str] = None,
        image_urls: List[str] = None,
        video_urls: List[str] = None
    ) -> Dict[str, Any]:
        """
        Create a Performance Max campaign with assets.
        
        Performance Max campaigns use Google's AI to automatically combine
        text, images, and videos into optimized ads across all Google properties.
        """
        try:
            def _create_pmax_sync():
                logger.info(f"Creating Performance Max campaign: {name}")
                logger.info(f"Assets - Headlines: {len(headlines or [])}, Descriptions: {len(descriptions or [])}, Images: {len(image_urls or [])}, Videos: {len(video_urls or [])}")
                
                client = self._get_client()
                
                # Generate temporary IDs for resources
                temp_id_counter = -1
                
                def get_next_temp_id():
                    nonlocal temp_id_counter
                    temp_id_counter -= 1
                    return temp_id_counter + 1
                
                budget_temp_id = get_next_temp_id()
                campaign_temp_id = get_next_temp_id()
                asset_group_temp_id = get_next_temp_id()
                
                operations = []
                
                # === 1. CREATE BUDGET ===
                budget_operation = client.get_type("MutateOperation")
                budget = budget_operation.campaign_budget_operation.create
                budget.resource_name = client.get_service("CampaignBudgetService").campaign_budget_path(
                    self.client_id, budget_temp_id
                )
                budget.name = f"{name} Budget {datetime.now().timestamp()}"
                
                try:
                    budget_decimal = Decimal(str(budget_amount))
                    budget.amount_micros = int(budget_decimal * Decimal(1_000_000))
                except (InvalidOperation, ValueError, TypeError):
                    return {"success": False, "error": "Invalid budget amount"}
                
                budget.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD
                budget.explicitly_shared = False
                operations.append(budget_operation)
                
                # === 2. CREATE PERFORMANCE MAX CAMPAIGN ===
                campaign_operation = client.get_type("MutateOperation")
                campaign = campaign_operation.campaign_operation.create
                campaign.resource_name = client.get_service("CampaignService").campaign_path(
                    self.client_id, campaign_temp_id
                )
                campaign.name = name
                campaign.status = client.enums.CampaignStatusEnum.PAUSED
                campaign.advertising_channel_type = client.enums.AdvertisingChannelTypeEnum.PERFORMANCE_MAX
                campaign.campaign_budget = client.get_service("CampaignBudgetService").campaign_budget_path(
                    self.client_id, budget_temp_id
                )
                
                # Performance Max uses maximize conversions by default
                campaign.maximize_conversions = client.get_type("MaximizeConversions")
                
                campaign.start_date = start_date.strftime("%Y%m%d")
                if end_date:
                    campaign.end_date = end_date.strftime("%Y%m%d")
                
                # URL expansion for Performance Max
                campaign.url_expansion_opt_out = False
                
                operations.append(campaign_operation)
                
                # === 3. CREATE ASSET GROUP ===
                asset_group_operation = client.get_type("MutateOperation")
                asset_group = asset_group_operation.asset_group_operation.create
                asset_group.resource_name = client.get_service("AssetGroupService").asset_group_path(
                    self.client_id, asset_group_temp_id
                )
                asset_group.campaign = client.get_service("CampaignService").campaign_path(
                    self.client_id, campaign_temp_id
                )
                asset_group.name = f"{name} Asset Group"
                asset_group.status = client.enums.AssetGroupStatusEnum.PAUSED
                
                # Set final URL for the asset group
                if final_url:
                    asset_group.final_urls.append(final_url)
                
                operations.append(asset_group_operation)
                
                # === 4. CREATE TEXT ASSETS AND LINK TO ASSET GROUP ===
                asset_temp_ids = {}
                
                # Headlines (need at least 3, max 15 for PMax)
                headlines_list = (headlines or [])[:15]
                if len(headlines_list) < 3:
                    headlines_list.extend(["Discover More", "Get Started", "Learn More"][:3 - len(headlines_list)])
                
                for i, headline_text in enumerate(headlines_list):
                    asset_temp_id = get_next_temp_id()
                    asset_temp_ids[f"headline_{i}"] = asset_temp_id
                    
                    # Create the asset
                    asset_op = client.get_type("MutateOperation")
                    asset = asset_op.asset_operation.create
                    asset.resource_name = client.get_service("AssetService").asset_path(
                        self.client_id, asset_temp_id
                    )
                    asset.text_asset.text = headline_text[:30]  # Max 30 chars
                    operations.append(asset_op)
                    
                    # Link asset to asset group
                    link_op = client.get_type("MutateOperation")
                    link = link_op.asset_group_asset_operation.create
                    link.asset = client.get_service("AssetService").asset_path(
                        self.client_id, asset_temp_id
                    )
                    link.asset_group = client.get_service("AssetGroupService").asset_group_path(
                        self.client_id, asset_group_temp_id
                    )
                    link.field_type = client.enums.AssetFieldTypeEnum.HEADLINE
                    operations.append(link_op)
                
                # Long Headlines (at least 1 required for PMax)
                long_headline_text = (headlines_list[0] if headlines_list else "Discover Our Services")[:90]
                long_headline_temp_id = get_next_temp_id()
                
                lh_asset_op = client.get_type("MutateOperation")
                lh_asset = lh_asset_op.asset_operation.create
                lh_asset.resource_name = client.get_service("AssetService").asset_path(
                    self.client_id, long_headline_temp_id
                )
                lh_asset.text_asset.text = long_headline_text
                operations.append(lh_asset_op)
                
                lh_link_op = client.get_type("MutateOperation")
                lh_link = lh_link_op.asset_group_asset_operation.create
                lh_link.asset = client.get_service("AssetService").asset_path(
                    self.client_id, long_headline_temp_id
                )
                lh_link.asset_group = client.get_service("AssetGroupService").asset_group_path(
                    self.client_id, asset_group_temp_id
                )
                lh_link.field_type = client.enums.AssetFieldTypeEnum.LONG_HEADLINE
                operations.append(lh_link_op)
                
                # Descriptions (need at least 2, max 4)
                descriptions_list = (descriptions or [])[:4]
                if len(descriptions_list) < 2:
                    descriptions_list.extend(["Transform your business today.", "See results that matter."][:2 - len(descriptions_list)])
                
                for i, desc_text in enumerate(descriptions_list):
                    asset_temp_id = get_next_temp_id()
                    
                    asset_op = client.get_type("MutateOperation")
                    asset = asset_op.asset_operation.create
                    asset.resource_name = client.get_service("AssetService").asset_path(
                        self.client_id, asset_temp_id
                    )
                    asset.text_asset.text = desc_text[:90]  # Max 90 chars
                    operations.append(asset_op)
                    
                    link_op = client.get_type("MutateOperation")
                    link = link_op.asset_group_asset_operation.create
                    link.asset = client.get_service("AssetService").asset_path(
                        self.client_id, asset_temp_id
                    )
                    link.asset_group = client.get_service("AssetGroupService").asset_group_path(
                        self.client_id, asset_group_temp_id
                    )
                    link.field_type = client.enums.AssetFieldTypeEnum.DESCRIPTION
                    operations.append(link_op)
                
                # Business Name (required for PMax)
                business_name_temp_id = get_next_temp_id()
                bn_asset_op = client.get_type("MutateOperation")
                bn_asset = bn_asset_op.asset_operation.create
                bn_asset.resource_name = client.get_service("AssetService").asset_path(
                    self.client_id, business_name_temp_id
                )
                bn_asset.text_asset.text = name[:25]  # Use campaign name as business name
                operations.append(bn_asset_op)
                
                bn_link_op = client.get_type("MutateOperation")
                bn_link = bn_link_op.asset_group_asset_operation.create
                bn_link.asset = client.get_service("AssetService").asset_path(
                    self.client_id, business_name_temp_id
                )
                bn_link.asset_group = client.get_service("AssetGroupService").asset_group_path(
                    self.client_id, asset_group_temp_id
                )
                bn_link.field_type = client.enums.AssetFieldTypeEnum.BUSINESS_NAME
                operations.append(bn_link_op)
                
                # === 5. CREATE IMAGE ASSETS ===
                if image_urls:
                    for i, img_url in enumerate(image_urls[:20]):  # Max 20 images
                        try:
                            # Download and encode image
                            response = requests.get(img_url, timeout=30)
                            if response.status_code == 200:
                                image_data = response.content
                                
                                asset_temp_id = get_next_temp_id()
                                
                                asset_op = client.get_type("MutateOperation")
                                asset = asset_op.asset_operation.create
                                asset.resource_name = client.get_service("AssetService").asset_path(
                                    self.client_id, asset_temp_id
                                )
                                asset.image_asset.data = image_data
                                asset.name = f"{name} Image {i+1}"
                                operations.append(asset_op)
                                
                                # Link as MARKETING_IMAGE (landscape)
                                link_op = client.get_type("MutateOperation")
                                link = link_op.asset_group_asset_operation.create
                                link.asset = client.get_service("AssetService").asset_path(
                                    self.client_id, asset_temp_id
                                )
                                link.asset_group = client.get_service("AssetGroupService").asset_group_path(
                                    self.client_id, asset_group_temp_id
                                )
                                link.field_type = client.enums.AssetFieldTypeEnum.MARKETING_IMAGE
                                operations.append(link_op)
                                
                                logger.info(f"Added image asset {i+1}/{len(image_urls)}")
                        except Exception as img_err:
                            logger.warning(f"Failed to add image {img_url}: {img_err}")
                            continue
                
                # === 6. CREATE VIDEO ASSETS ===
                # Note: YouTube video IDs are used for Performance Max
                if video_urls:
                    for i, video_url in enumerate(video_urls[:5]):  # Max 5 videos
                        try:
                            # Extract YouTube video ID if it's a YouTube URL
                            youtube_id = None
                            if "youtube.com" in video_url or "youtu.be" in video_url:
                                if "v=" in video_url:
                                    youtube_id = video_url.split("v=")[1].split("&")[0]
                                elif "youtu.be/" in video_url:
                                    youtube_id = video_url.split("youtu.be/")[1].split("?")[0]
                            
                            if youtube_id:
                                asset_temp_id = get_next_temp_id()
                                
                                asset_op = client.get_type("MutateOperation")
                                asset = asset_op.asset_operation.create
                                asset.resource_name = client.get_service("AssetService").asset_path(
                                    self.client_id, asset_temp_id
                                )
                                asset.youtube_video_asset.youtube_video_id = youtube_id
                                asset.name = f"{name} Video {i+1}"
                                operations.append(asset_op)
                                
                                link_op = client.get_type("MutateOperation")
                                link = link_op.asset_group_asset_operation.create
                                link.asset = client.get_service("AssetService").asset_path(
                                    self.client_id, asset_temp_id
                                )
                                link.asset_group = client.get_service("AssetGroupService").asset_group_path(
                                    self.client_id, asset_group_temp_id
                                )
                                link.field_type = client.enums.AssetFieldTypeEnum.YOUTUBE_VIDEO
                                operations.append(link_op)
                                
                                logger.info(f"Added YouTube video asset: {youtube_id}")
                            else:
                                logger.warning(f"Skipping non-YouTube video: {video_url}")
                        except Exception as vid_err:
                            logger.warning(f"Failed to add video {video_url}: {vid_err}")
                            continue
                
                # === EXECUTE ALL OPERATIONS ===
                logger.info(f"Executing {len(operations)} operations for Performance Max campaign")
                
                googleads_service = client.get_service("GoogleAdsService")
                response = googleads_service.mutate(
                    customer_id=str(self.client_id),
                    mutate_operations=operations
                )
                
                # Extract campaign ID from response
                campaign_id = None
                for result in response.mutate_operation_responses:
                    if result.campaign_result.resource_name:
                        campaign_id = result.campaign_result.resource_name.split("/")[-1]
                        break
                
                logger.info(f"Performance Max campaign created successfully: {campaign_id}")
                
                return {
                    "success": True,
                    "campaign_id": campaign_id,
                    "campaign_type": "PERFORMANCE_MAX",
                    "assets_created": {
                        "headlines": len(headlines_list),
                        "descriptions": len(descriptions_list),
                        "images": len(image_urls or []),
                        "videos": len(video_urls or [])
                    }
                }
            
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _create_pmax_sync)
            return result
            
        except Exception as e:
            logger.error(f"Error creating Performance Max campaign: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    # Keep legacy methods for backward compatibility
    async def create_campaign(
        self,
        name: str,
        budget_amount: float,
        start_date: date,
        end_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """Legacy method - redirects to Performance Max"""
        return await self.create_performance_max_campaign(
            name=name,
            budget_amount=budget_amount,
            start_date=start_date,
            end_date=end_date
        )
    
    async def create_ad_group(
        self,
        campaign_id: str,
        name: str
    ) -> Dict[str, Any]:
        """Performance Max doesn't use ad groups - return success for compatibility"""
        logger.info(f"Performance Max campaigns don't use ad groups - skipping")
        return {"success": True, "ad_group_id": "pmax_asset_group", "skipped": True}
    
    async def create_ad(
        self,
        ad_group_id: str,
        headlines: List[str],
        descriptions: List[str],
        final_url: str
    ) -> Dict[str, Any]:
        """Performance Max doesn't create individual ads - return success for compatibility"""
        logger.info(f"Performance Max campaigns don't create individual ads - assets are in asset groups")
        return {"success": True, "ad_id": "pmax_auto_generated", "skipped": True}

