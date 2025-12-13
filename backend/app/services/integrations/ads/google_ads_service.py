"""
Google Ads Campaign Service
"""
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from app.config import settings
from app.utils.logger import logger
from app.utils.google_ads import get_customer_ids


GOOGLE_ADS_LIBRARY_ERROR = "google-ads library not installed. Install with: pip install google-ads"


class GoogleAdsCampaignService:
    """Service for creating and managing Google Ads campaigns"""
    
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
        # Validate and format login_customer_id (manager account) - must be exactly 10 digits
        self.login_customer_id = self._validate_customer_id(login_customer_id, "login_customer_id")
        # Validate and format client_id (target account) - must be exactly 10 digits
        # If not provided, use login_customer_id
        self.client_id = self._validate_customer_id(client_id or login_customer_id, "client_id")
    
    def _validate_customer_id(self, customer_id: Optional[str], field_name: str = "customer_id") -> str:
        """
        Validate that customer_id is exactly 10 digits as a string.
        Customer IDs should already be in the correct format as fetched from Google Ads API.
        
        Args:
            customer_id: Customer ID from integration (should be 10 digits)
            field_name: Name of the field for error messages
        
        Returns:
            Validated 10-digit customer ID as string
        
        Raises:
            ValueError: If customer_id cannot be validated
        """
        if not customer_id:
            raise ValueError(f"Google Ads {field_name} is required but not provided")
        
        # Convert to string and strip whitespace
        customer_id_str = str(customer_id).strip()
        
        # If it's a resource name like "customers/1234567890", extract the ID
        if "/" in customer_id_str:
            customer_id_str = customer_id_str.split("/")[-1]
        
        # Check if it's exactly 10 digits (allowing only digits)
        if customer_id_str.isdigit() and len(customer_id_str) == 10:
            return customer_id_str
        
        # If not valid, provide clear error message
        digits_only = ''.join(filter(str.isdigit, customer_id_str))
        raise ValueError(
            f"Google Ads {field_name} must be exactly 10 digits. "
            f"Got: {customer_id} ({len(digits_only)} digits: {digits_only}). "
            f"Please reconnect your Google Ads account to ensure customer IDs are stored correctly."
        )
    
    def _get_client(self):
        """Get Google Ads client using login_customer_id for authentication"""
        try:
            from google.ads.googleads.client import GoogleAdsClient
            
            # Debug logging
            developer_token = settings.GOOGLE_ADS_DEVELOPER_TOKEN
            logger.info(f"Google Ads client config - login_customer_id: {self.login_customer_id}, client_id: {self.client_id}")
            logger.info(f"Developer token length: {len(developer_token) if developer_token else 0}")
            logger.info(f"Developer token set: {bool(developer_token)}")
            
            # login_customer_id must be exactly 10 digits as a string (manager account)
            client_config = {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "developer_token": developer_token,
                "refresh_token": self.refresh_token,
                "login_customer_id": str(self.login_customer_id),  # Manager account for authentication
                "use_proto_plus": True,
            }
            
            logger.info(f"Client config keys: {list(client_config.keys())}")
            logger.info(f"Developer token in config: {bool(client_config.get('developer_token'))}")
            
            client = GoogleAdsClient.load_from_dict(client_config)
            
            # Log API version if available
            if hasattr(client, 'get_api_version'):
                logger.info(f"Google Ads API version: {client.get_api_version()}")
            
            return client
        except ImportError:
            logger.error(GOOGLE_ADS_LIBRARY_ERROR)
            raise ImportError(GOOGLE_ADS_LIBRARY_ERROR)
        except Exception as e:
            logger.error(f"Error creating Google Ads client: {e}")
            raise
    
    async def create_campaign(
        self,
        name: str,
        budget_amount: float,
        start_date: date,
        end_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Create a Google Ads campaign
        
        Args:
            name: Campaign name
            budget_amount: Daily budget in dollars
            start_date: Campaign start date
            end_date: Campaign end date (optional)
        
        Returns:
            Dictionary with campaign_id and success status
        """
        try:
            def _create_campaign_sync():
                logger.info(f"Creating campaign: name={name}, budget={budget_amount}, start_date={start_date}, end_date={end_date}")
                logger.info(f"Login customer_id (manager): {self.login_customer_id}, Client ID: {self.client_id}")
                
                client = self._get_client()
                budget_service = client.get_service("CampaignBudgetService")
                campaign_service = client.get_service("CampaignService")
                
                # Create Budget
                budget_operation = client.get_type("CampaignBudgetOperation")
                budget = budget_operation.create
                budget.name = f"{name} Budget {datetime.now().timestamp()}"
                
                # Safely coerce budget to micros
                try:
                    budget_decimal = Decimal(str(budget_amount))
                    budget_micros = int(budget_decimal * Decimal(1_000_000))
                except (InvalidOperation, ValueError, TypeError):
                    logger.error("Invalid budget amount")
                    return {"success": False, "error": "Invalid budget amount"}
                
                budget.amount_micros = budget_micros
                budget.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD
                
                logger.info(f"Creating budget with customer_id={self.client_id}")
                budget_response = budget_service.mutate_campaign_budgets(
                    customer_id=str(self.client_id), operations=[budget_operation]  # Use client_id for campaign creation
                )
                logger.info(f"Budget created successfully: {budget_response.results[0].resource_name}")
                budget_resource_name = budget_response.results[0].resource_name
                
                # Create Campaign
                campaign_operation = client.get_type("CampaignOperation")
                campaign = campaign_operation.create
                
                # Set all required and optional fields
                campaign.name = name
                campaign.status = client.enums.CampaignStatusEnum.PAUSED
                campaign.advertising_channel_type = client.enums.AdvertisingChannelTypeEnum.SEARCH
                campaign.campaign_budget = budget_resource_name
                
                # Set dates
                campaign.start_date = start_date.strftime("%Y%m%d")
                if end_date:
                    campaign.end_date = end_date.strftime("%Y%m%d")
                
                # Set bidding strategy - with proto-plus, direct assignment works
                campaign.manual_cpc = client.get_type("ManualCpc")
                
                # Set network settings (optional but recommended)
                campaign.network_settings.target_google_search = True
                campaign.network_settings.target_search_network = True
                campaign.network_settings.target_partner_search_network = False
                campaign.network_settings.target_content_network = True
                
                # CRITICAL: Required field - must use ENUM value, not boolean!
                campaign.contains_eu_political_advertising = (
                    client.enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
                )
                
                logger.info(f"Campaign fields set - attempting mutation with customer_id={self.client_id}")
                
                campaign_response = campaign_service.mutate_campaigns(
                    customer_id=str(self.client_id), operations=[campaign_operation]  # Use client_id for campaign creation
                )
                logger.info(f"Campaign created successfully: {campaign_response.results[0].resource_name}")
                resource_name = campaign_response.results[0].resource_name
                campaign_id = resource_name.split("/")[-1]
                
                return {"success": True, "campaign_id": campaign_id, "budget_id": budget_resource_name.split("/")[-1]}
            
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _create_campaign_sync)
            return result
            
        except Exception as e:
            logger.error(f"Error creating Google Ads campaign: {e}")
            return {"success": False, "error": str(e)}
    
    async def create_ad_group(
        self,
        campaign_id: str,
        name: str
    ) -> Dict[str, Any]:
        """Create an ad group"""
        try:
            def _create_ad_group_sync():
                client = self._get_client()
                service = client.get_service("AdGroupService")
                operation = client.get_type("AdGroupOperation")
                ad_group = operation.create
                ad_group.name = name
                ad_group.campaign = f"customers/{self.client_id}/campaigns/{campaign_id}"  # Use client_id for campaign creation
                ad_group.status = client.enums.AdGroupStatusEnum.ENABLED
                ad_group.type_ = client.enums.AdGroupTypeEnum.SEARCH_STANDARD
                
                response = service.mutate_ad_groups(customer_id=str(self.client_id), operations=[operation])  # Use client_id for campaign creation
                ad_group_id = response.results[0].resource_name.split("/")[-1]
                return {"success": True, "ad_group_id": ad_group_id}
            
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _create_ad_group_sync)
            return result
            
        except Exception as e:
            logger.error(f"Error creating ad group: {e}")
            return {"success": False, "error": str(e)}
    
    async def create_ad(
        self,
        ad_group_id: str,
        headlines: List[str],
        descriptions: List[str],
        final_url: str
    ) -> Dict[str, Any]:
        """Create a responsive search ad"""
        try:
            def _create_ad_sync():
                client = self._get_client()
                service = client.get_service("AdGroupAdService")
                operation = client.get_type("AdGroupAdOperation")
                ad_group_ad = operation.create
                ad_group_ad.ad_group = f"customers/{self.client_id}/adGroups/{ad_group_id}"  # Use client_id for campaign creation
                ad_group_ad.status = client.enums.AdGroupAdStatusEnum.ENABLED
                
                ad = ad_group_ad.ad
                ad.final_urls.append(final_url)
                
                rsa = ad.responsive_search_ad
                
                # Add headlines (need at least 3, max 15) - Google Ads limit: 30 chars
                for headline_text in headlines[:15]:
                    headline_asset = client.get_type("AdTextAsset")
                    headline_asset.text = headline_text[:30]  # Max 30 chars for headlines
                    rsa.headlines.append(headline_asset)
                
                # Add descriptions (need at least 2, max 4)
                for desc_text in descriptions[:4]:
                    description_asset = client.get_type("AdTextAsset")
                    description_asset.text = desc_text[:90]  # Max 90 chars
                    rsa.descriptions.append(description_asset)
                
                response = service.mutate_ad_group_ads(
                    customer_id=str(self.client_id),  # Use client_id for campaign creation
                    operations=[operation]
                )
                
                ad_id = response.results[0].resource_name.split("/")[-1]
                return {"success": True, "ad_id": ad_id}
            
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _create_ad_sync)
            return result
            
        except Exception as e:
            logger.error(f"Error creating ad: {e}")
            return {"success": False, "error": str(e)}

