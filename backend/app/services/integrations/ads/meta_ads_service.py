"""
Meta Ads Campaign Service
"""
import json
from typing import Dict, Any, Optional, List
from datetime import datetime, date
import httpx
from app.utils.logger import logger


META_API_BASE = "https://graph.facebook.com/v23.0"


class MetaAdsCampaignService:
    """Service for creating and managing Meta Ads campaigns"""
    
    def __init__(self, access_token: str, ad_account_id: str):
        self.access_token = access_token
        # Ensure ad_account_id always has act_ prefix
        if ad_account_id and not ad_account_id.startswith("act_"):
            ad_account_id = f"act_{ad_account_id}"
        self.ad_account_id = ad_account_id
        logger.info(f"MetaAdsCampaignService initialized with ad_account_id: {self.ad_account_id}")
    
    async def _make_api_request(
        self,
        endpoint: str,
        method: str = 'GET',
        data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make a request to Meta Graph API"""
        url = f"{META_API_BASE}/{endpoint}"
        
        if params is None:
            params = {}
        params['access_token'] = self.access_token
        
        # Log request details (without full token)
        logger.info(f"Meta API {method} -> {endpoint}")
        if data:
            logger.info(f"Meta API Payload: {json.dumps(data, indent=2)}")
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if method == 'GET':
                    response = await client.get(url, params=params)
                elif method == 'POST':
                    response = await client.post(url, data=data, params=params)
                elif method == 'PUT':
                    response = await client.put(url, data=data, params=params)
                elif method == 'DELETE':
                    response = await client.delete(url, params=params)
                else:
                    return {"success": False, "error": "Invalid HTTP method"}
                
                # Log response status
                logger.info(f"Meta API Response Status: {response.status_code}")
                
                response.raise_for_status()
                response_data = response.json()
                logger.info(f"Meta API Response: {json.dumps(response_data, indent=2)}")
                return {"success": True, "data": response_data}
                
        except httpx.HTTPStatusError as e:
            try:
                error_data = e.response.json()
                error_message = error_data.get('error', {}).get('error_user_msg') or error_data.get('error', {}).get('message', str(e))
                error_code = error_data.get('error', {}).get('code', '')
                error_type = error_data.get('error', {}).get('type', '')
                error_subcode = error_data.get('error', {}).get('error_subcode', '')
                
                logger.error(f"Meta API FAILED - Status: {e.response.status_code}")
                logger.error(f"Meta API FAILED - Type: {error_type}, Code: {error_code}, Subcode: {error_subcode}")
                logger.error(f"Meta API FAILED - Message: {error_message}")
                logger.error(f"Meta API FAILED - Full Response: {json.dumps(error_data, indent=2)}")
            except Exception as parse_error:
                logger.error(f"Meta API FAILED - Could not parse error: {parse_error}")
                logger.error(f"Meta API FAILED - Raw response: {e.response.text}")
                error_message = str(e)
            return {"success": False, "error": error_message}
        except Exception as e:
            logger.error(f"Meta API request error: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def create_campaign(
        self,
        name: str,
        objective: str,
        daily_budget: Optional[float] = None,
        lifetime_budget: Optional[float] = None,
        status: str = "PAUSED",
        special_ad_categories: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        Create a Meta Ads campaign
        
        Args:
            name: Campaign name
            objective: Campaign objective (e.g., "LINK_CLICKS", "CONVERSIONS", "REACH")
            daily_budget: Daily budget in dollars
            lifetime_budget: Lifetime budget in dollars
            status: Campaign status (PAUSED, ACTIVE)
            special_ad_categories: Special ad categories if needed
        
        Returns:
            Dictionary with campaign_id and success status
        """
        endpoint = f"{self.ad_account_id}/campaigns"
        
        campaign_data = {
            'name': name,
            'objective': objective,
            'status': status,
            'buying_type': 'AUCTION',
        }
        
        if daily_budget:
            campaign_data['daily_budget'] = str(int(daily_budget * 100))  # Convert to cents
        
        if lifetime_budget:
            campaign_data['lifetime_budget'] = str(int(lifetime_budget * 100))  # Convert to cents
        
        if special_ad_categories:
            campaign_data['special_ad_categories'] = special_ad_categories
        
        logger.info(f"Creating Meta campaign: {name} (objective={objective}, budget={daily_budget or lifetime_budget})")
        result = await self._make_api_request(endpoint, 'POST', data=campaign_data)
        
        if result['success']:
            campaign_id = result['data']['id']
            logger.info(f"✅ Meta campaign created: {campaign_id}")
            return {"success": True, "campaign_id": campaign_id}
        else:
            logger.error(f"❌ Meta campaign creation failed: {result['error']}")
            return {"success": False, "error": result['error']}
    
    async def create_ad_set(
        self,
        campaign_id: str,
        name: str,
        optimization_goal: str,
        billing_event: str,
        bid_amount: Optional[float] = None,
        daily_budget: Optional[float] = None,
        lifetime_budget: Optional[float] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        targeting: Optional[Dict] = None,
        page_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create an ad set"""
        endpoint = f"{self.ad_account_id}/adsets"
        
        if not targeting:
            targeting = {
                'geo_locations': {'countries': ['US']},
                'age_min': 18,
                'age_max': 65
            }
        
        promoted_obj = {"page_id": page_id} if page_id else {}

        ad_set_data = {
            'name': name,
            'campaign_id': campaign_id,
            'optimization_goal': optimization_goal,
            'billing_event': billing_event,
            'status': 'PAUSED',
            'targeting': json.dumps(targeting),
            'promoted_object': json.dumps(promoted_obj),
        }
        
        if bid_amount:
            ad_set_data["bid_amount"] = str(int(bid_amount * 100))
        
        # Always include start_time and end_time if provided
        if start_time:
            ad_set_data['start_time'] = start_time.isoformat()
        
        if end_time:
            ad_set_data['end_time'] = end_time.isoformat()
        
        logger.info(f"Creating Meta ad set: {name} (campaign={campaign_id})")
        result = await self._make_api_request(endpoint, 'POST', data=ad_set_data)
        
        if result['success']:
            ad_set_id = result['data']['id']
            logger.info(f"✅ Meta ad set created: {ad_set_id}")
            return {"success": True, "ad_set_id": ad_set_id}
        else:
            logger.error(f"❌ Meta ad set creation failed: {result['error']}")
            return {"success": False, "error": result['error']}
    
    async def create_ad_creative(
        self,
        name: str,
        page_id: Optional[str],
        title: str,
        body: str,
        link_url: str,
        image_url: Optional[str] = None,
        call_to_action_type: str = "LEARN_MORE"
    ) -> Dict[str, Any]:
        """Create an ad creative"""
        endpoint = f"{self.ad_account_id}/adcreatives"
        
        # Build object_story_spec for page post
        if page_id:
            # For page posts, use link_data
            link_data = {
                "link": link_url,
                "message": body,
                "name": title,
                "call_to_action": {
                    "type": call_to_action_type
                }
            }
            
            # Add image URL if available
            if image_url:
                link_data["image_url"] = image_url
            
            object_story_spec = {
                "page_id": page_id,
                "link_data": link_data
            }
        else:
            # Create creative without page_id (for app ads or other types)
            link_data = {
                "link": link_url,
                "message": body,
                "name": title,
                "call_to_action": {
                    "type": call_to_action_type
                }
            }
            
            if image_url:
                link_data["image_url"] = image_url
            
            object_story_spec = {
                "link_data": link_data
            }
        
        creative_data = {
            "name": name,
            "object_story_spec": json.dumps(object_story_spec),
        }
        
        logger.info(f"Creating Meta creative: {name} (page={page_id})")
        logger.info(f"Creative object_story_spec: {json.dumps(object_story_spec, indent=2)}")
        result = await self._make_api_request(endpoint, 'POST', data=creative_data)
        
        if result['success']:
            creative_id = result['data']['id']
            logger.info(f"✅ Meta creative created: {creative_id}")
            return {"success": True, "creative_id": creative_id}
        else:
            logger.error(f"❌ Meta creative creation failed: {result['error']}")
            return {"success": False, "error": result['error']}
    
    async def create_ad(
        self,
        ad_set_id: str,
        name: str,
        creative_id: str,
        status: str = "PAUSED"
    ) -> Dict[str, Any]:
        """Create an ad"""
        endpoint = f"{self.ad_account_id}/ads"
        
        ad_data = {
            'name': name,
            'adset_id': ad_set_id,
            'creative': json.dumps({"creative_id": creative_id}),
            'status': status,
        }
        
        logger.info(f"Creating Meta ad: {name} (ad_set={ad_set_id}, creative={creative_id})")
        result = await self._make_api_request(endpoint, 'POST', data=ad_data)
        
        if result['success']:
            ad_id = result['data']['id']
            logger.info(f"✅ Meta ad created: {ad_id}")
            return {"success": True, "ad_id": ad_id}
        else:
            logger.error(f"❌ Meta ad creation failed: {result['error']}")
            return {"success": False, "error": result['error']}
