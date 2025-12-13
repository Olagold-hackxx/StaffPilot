"""
Campaign Asset Service - Handles generation of creative assets (images, videos)
"""
from typing import List, Dict, Any, Optional
import base64
import asyncio
from datetime import datetime
import uuid
from io import BytesIO

from app.services.llm.factory import create_llm_service
from app.models.campaign import Campaign
from app.schemas.campaign_schemas import GeneratedAsset, AssetType
from app.utils.logger import logger
from app.services.storage import get_storage

class CampaignAssetService:
    """
    Service to generate creative assets for campaigns using AI models (Imagen, Veo).
    """
    
    def __init__(self):
        self.llm_service = create_llm_service()
        self.storage = get_storage()
        
    async def generate_assets_for_campaign(
        self, 
        campaign: Campaign, 
        step_ids: Optional[List[str]] = None
    ) -> List[GeneratedAsset]:
        """
        Generate assets based on the campaign plan.
        
        Args:
            campaign: The campaign object
            step_ids: Optional list of specific step IDs to generate assets for. 
                      If None, finds "Asset Creation" relevant steps.
        
        Returns:
            List of generated assets
        """
        generated_assets = []
        
        # 1. Identify relevant steps
        if not campaign.plan or "steps" not in campaign.plan:
            logger.warning(f"No plan found for campaign {campaign.id}")
            return []
            
        steps_to_process = []
        for step in campaign.plan["steps"]:
            # If specific step_ids requested, check match
            if step_ids and step.get("id") not in step_ids:
                continue
                
            # Otherwise, auto-detect asset creation steps
            # Look for keywords or specific step titles
            if not step_ids and "Asset Creation" not in step.get("title", "") and "Creative" not in step.get("title", ""):
                bool_action_match = any("create" in a.lower() or "generate" in a.lower() for a in step.get("actions", []))
                if not bool_action_match:
                    continue
            
            steps_to_process.append(step)
            
        logger.info(f"Generating assets for {len(steps_to_process)} steps")
        
        # 2. Process each step
        for step in steps_to_process:
            assets = await self._process_step(campaign, step)
            generated_assets.extend(assets)
            
        return generated_assets
    
    async def _process_step(self, campaign: Campaign, step: Dict[str, Any]) -> List[GeneratedAsset]:
        """
        Process a single plan step to generate assets
        """
        assets = []
        
        # Build prompt from campaign context
        base_prompt = f"""
        Professional advertising image for a campaign.
        Product: {campaign.product_brief}
        Audience: {', '.join(campaign.target_audience.get('interests', [])) if campaign.target_audience else 'General'}
        Style: Professional, High Quality, 4k.
        """
        
        # Add specific step context
        specific_prompt = f"{base_prompt}\nContext: {step.get('description')}\n"
        
        # Generate Images based on preferences
        if campaign.creative_preference in ["image", "both"]:
            try:
                # Generate 2 variations
                logger.info(f"Generating images for step {step.get('id')}")
                image_data_list = await self.llm_service.generate_image(
                    prompt=specific_prompt,
                    number_of_images=2,
                    aspect_ratio="1:1"
                )
                
                for i, img_bytes in enumerate(image_data_list):
                    # Upload to storage
                    file_id = str(uuid.uuid4())
                    filename = f"{file_id}.png"
                    storage_key = f"tenants/{campaign.tenant_id}/campaigns/{campaign.id}/assets/{filename}"
                    
                    # Convert bytes to file-like object
                    file_obj = BytesIO(img_bytes)
                    
                    url = await self.storage.upload(
                        key=storage_key,
                        file=file_obj,
                        content_type="image/png"
                    )
                    
                    assets.append(GeneratedAsset(
                        id=f"asset_{step.get('id')}_img_{i}",
                        type=AssetType.IMAGE,
                        content=url,
                        prompt=specific_prompt,
                        aspect_ratio="1:1",
                        created_at=datetime.utcnow().isoformat(),
                        step_id=step.get("id")
                    ))
            except Exception as e:
                logger.error(f"Image generation failed for step {step.get('id')}: {e}")
        
        return assets
