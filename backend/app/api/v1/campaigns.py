"""
Campaign Management API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel
from datetime import date, datetime

from app.db.session import get_db
from app.dependencies import get_current_user, get_current_tenant
from app.models.user import User
from app.models.campaign import Campaign, CampaignAsset
from app.models.integration import SocialIntegration
from app.models.tenant import Tenant
from app.services.integrations.ads import GoogleAdsCampaignService, MetaAdsCampaignService
from app.services.campaign_plan_service import generate_campaign_plan, update_plan_step_status
from app.schemas.campaign_schemas import (
    CampaignCreateRequest,
    CampaignPlan,
    CampaignPlanGenerateRequest,
    CampaignStepUpdateRequest,
    CampaignPlanResponse,
    StepExecuteRequest,
    StepExecuteResponse,
    StepResultResponse,
    StepResult
)
from app.utils.logger import logger

router = APIRouter(tags=["campaigns"])


class CampaignResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    campaign_type: Optional[str]
    objective_type: Optional[str]
    start_date: Optional[date]
    end_date: Optional[date]
    channels: List[str]
    total_budget: Optional[float]
    currency: str = "USD"
    budget_allocation: Optional[Dict[str, float]]
    goal_metrics: Optional[Dict[str, Any]]
    status: str
    plan: Optional[Dict[str, Any]]
    product_brief: Optional[str]
    creative_preference: Optional[str]
    target_audience: Optional[Dict[str, Any]]
    metrics: Optional[Dict[str, Any]]
    created_at: str
    execution_id: Optional[str]


class CampaignListResponse(BaseModel):
    campaigns: List[CampaignResponse]


@router.get("/campaigns", response_model=CampaignListResponse)
async def list_campaigns(
    status_filter: Optional[str] = Query(None, description="Filter campaigns by status"),
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """List all campaigns for the current tenant"""
    try:
        query = select(Campaign).where(Campaign.tenant_id == current_tenant.id)
        
        if status_filter:
            query = query.where(Campaign.status == status_filter)
        
        query = query.order_by(Campaign.created_at.desc())
        
        result = await db.execute(query)
        campaigns = result.scalars().all()
        
        return CampaignListResponse(
            campaigns=[
                CampaignResponse(
                    id=str(c.id),
                    name=c.name,
                    description=c.description,
                    campaign_type=c.campaign_type,
                    objective_type=c.objective_type,
                    start_date=c.start_date,
                    end_date=c.end_date,
                    channels=c.channels,
                    total_budget=float(c.total_budget) if c.total_budget else None,
                    currency=c.currency or "USD",
                    budget_allocation={k: float(v) for k, v in c.budget_allocation.items()} if c.budget_allocation else None,
                    goal_metrics=c.goal_metrics,
                    status=c.status,
                    plan=c.plan,
                    product_brief=c.product_brief,
                    creative_preference=c.creative_preference,
                    target_audience=c.target_audience,
                    metrics=c.metrics,
                    created_at=c.created_at.isoformat() if c.created_at else "",
                    execution_id=str(c.execution_id) if c.execution_id else None
                )
                for c in campaigns
            ]
        )
    except Exception as e:
        logger.error(f"Error listing campaigns: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list campaigns: {str(e)}"
        )


@router.get("/campaigns/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: UUID,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific campaign"""
    try:
        result = await db.execute(
            select(Campaign).where(
                Campaign.id == campaign_id,
                Campaign.tenant_id == current_tenant.id
            )
        )
        campaign = result.scalar_one_or_none()
        
        if not campaign:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign not found"
            )
        
        return CampaignResponse(
            id=str(campaign.id),
            name=campaign.name,
            description=campaign.description,
            campaign_type=campaign.campaign_type,
            objective_type=campaign.objective_type,
            start_date=campaign.start_date,
            end_date=campaign.end_date,
            channels=campaign.channels,
            total_budget=float(campaign.total_budget) if campaign.total_budget else None,
            currency=campaign.currency or "USD",
            budget_allocation={k: float(v) for k, v in campaign.budget_allocation.items()} if campaign.budget_allocation else None,
            goal_metrics=campaign.goal_metrics,
            status=campaign.status,
            plan=campaign.plan,
            product_brief=campaign.product_brief,
            creative_preference=campaign.creative_preference,
            target_audience=campaign.target_audience,
            metrics=campaign.metrics,
            created_at=campaign.created_at.isoformat() if campaign.created_at else "",
            execution_id=str(campaign.execution_id) if campaign.execution_id else None
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting campaign: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get campaign: {str(e)}"
        )


@router.post("/campaigns/{campaign_id}/approve", response_model=Dict[str, Any])
async def approve_campaign(
    campaign_id: UUID,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Approve and launch a campaign to platforms (Google Ads, Meta Ads)
    This will create the actual campaigns in the advertising platforms
    """
    try:
        # Get campaign
        result = await db.execute(
            select(Campaign).where(
                Campaign.id == campaign_id,
                Campaign.tenant_id == current_tenant.id
            )
        )
        campaign = result.scalar_one_or_none()
        
        if not campaign:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign not found"
            )
        
        if campaign.status != "draft":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot approve campaign with status: {campaign.status}"
            )
        
        # Get tenant for website URL
        website_url = current_tenant.website_url if current_tenant.website_url else ""
        
        # Get integrations for each channel
        created_assets = []
        errors = []
        
        for channel in campaign.channels:
            try:
                # Get integration for this channel
                integration_result = await db.execute(
                    select(SocialIntegration).where(
                        SocialIntegration.tenant_id == current_tenant.id,
                        SocialIntegration.platform == channel,
                        SocialIntegration.is_active == True
                    )
                )
                integration = integration_result.scalar_one_or_none()
                
                if not integration:
                    errors.append(f"No active integration found for {channel}")
                    continue
                
                # Extract ad copy from plan
                plan = campaign.plan or {}
                ad_copy = plan.get("ad_copy", {}).get(channel, {})
                
                if channel == "google_ads":
                    # Extract login_customer_id (manager account) and client_id from organizations array
                    # Pattern: login_customer_id = manager account (for auth), client_id = target account (for campaigns)
                    login_customer_id = None  # Manager account for authentication
                    client_id = None  # Client account where campaign is created
                    
                    logger.info(f"Google Ads integration - organizations: {integration.organizations}")
                    logger.info(f"Google Ads integration - meta_data: {integration.meta_data}")
                    
                    # Get manager account (login_customer_id) - this is the account used for authentication
                    # Customer IDs should already be 10 digits as fetched from Google Ads API
                    if integration.organizations and isinstance(integration.organizations, list):
                        manager_account = next(
                            (org for org in integration.organizations if org.get("type") == "manager"),
                            None
                        )
                        if manager_account:
                            login_customer_id = manager_account.get("customer_id")
                            logger.info(f"Found manager account with customer_id: {login_customer_id}")
                            
                            # Validate it's a string (should be 10 digits)
                            if login_customer_id:
                                login_customer_id = str(login_customer_id).strip()
                                
                                # Check if user has selected a default client account
                                default_client_id = None
                                if integration.meta_data and integration.meta_data.get("default_page_id"):
                                    default_client_id = str(integration.meta_data.get("default_page_id")).strip()
                                    logger.info(f"Found default client account from default_page_id: {default_client_id}")
                                
                                # Get client_id from default_page_id if set, otherwise from manager's client_ids
                                client_ids = manager_account.get("client_ids", [])
                                if default_client_id and client_ids and isinstance(client_ids, list):
                                    # Validate that the default_client_id is in the manager's client_ids
                                    client_id_strs = [str(cid).strip() for cid in client_ids]
                                    if default_client_id in client_id_strs:
                                        client_id = default_client_id
                                        logger.info(f"Using selected default client_id: {client_id}")
                                    else:
                                        logger.warning(f"Default client_id {default_client_id} not found in manager's client_ids, will use first available")
                                
                                # If no default selected or invalid, use first valid client_id
                                if not client_id and client_ids and isinstance(client_ids, list) and len(client_ids) > 0:
                                    # Validate client_ids are 10 digits
                                    valid_client_ids = [
                                        str(cid).strip() 
                                        for cid in client_ids 
                                        if str(cid).strip().isdigit() and len(str(cid).strip()) == 10
                                    ]
                                    if valid_client_ids:
                                        client_id = valid_client_ids[0]  # Use first valid client account
                                        logger.info(f"Using first client_id from manager's client_ids: {client_id}")
                                    else:
                                        logger.warning(f"Manager account has no valid client_ids, will use manager account itself")
                    
                    # If no manager account with valid client_ids, use the first organization as both login and client
                    # This means we'll create campaigns in the user's own account (not through manager)
                    if not login_customer_id and integration.organizations and isinstance(integration.organizations, list):
                        first_org = integration.organizations[0]
                        login_customer_id = first_org.get("customer_id")
                        if login_customer_id:
                            login_customer_id = str(login_customer_id).strip()
                            # Validate it's 10 digits
                            if login_customer_id.isdigit() and len(login_customer_id) == 10:
                                logger.info(f"Using first organization as login_customer_id (same account for client): {login_customer_id}")
                                # Only use client_ids if they exist and are valid
                                client_ids = first_org.get("client_ids", [])
                                if client_ids and isinstance(client_ids, list) and len(client_ids) > 0:
                                    valid_client_ids = [
                                        str(cid).strip() 
                                        for cid in client_ids 
                                        if str(cid).strip().isdigit() and len(str(cid).strip()) == 10
                                    ]
                                    if valid_client_ids:
                                        client_id = valid_client_ids[0]
                                        logger.info(f"Using client_id from first org's client_ids: {client_id}")
                    
                    # Fallback to meta_data
                    if not login_customer_id and integration.meta_data:
                        login_customer_id = integration.meta_data.get("customer_id")
                        if login_customer_id:
                            login_customer_id = str(login_customer_id).strip()
                            if login_customer_id.isdigit() and len(login_customer_id) == 10:
                                logger.info(f"Using customer_id from meta_data: {login_customer_id}")
                    
                    # If no client_id found, use login_customer_id (same account - create campaigns in user's own account)
                    # This is the safest approach when manager-client relationship isn't established
                    if not client_id and login_customer_id:
                        client_id = login_customer_id
                        logger.info(f"No client_id found, using login_customer_id as client_id (same account): {client_id}")
                        logger.info("This means campaigns will be created in the user's own account, not through a manager account")
                    
                    if not login_customer_id:
                        errors.append("Google Ads: No manager customer_id found in integration. Please reconnect your Google Ads account.")
                        continue
                    
                    logger.info(f"Final Google Ads IDs - login_customer_id: {login_customer_id}, client_id: {client_id}")
                    
                    # Create Google Ads campaign service
                    try:
                        google_service = GoogleAdsCampaignService(
                            refresh_token=integration.refresh_token or integration.access_token,
                            login_customer_id=login_customer_id,  # Manager account for authentication
                            client_id=client_id  # Client account where campaign is created
                        )
                    except ValueError as e:
                        errors.append(f"Google Ads: Invalid customer_id - {str(e)}")
                        continue
                    except Exception as e:
                        errors.append(f"Google Ads: Error initializing service - {str(e)}")
                        logger.error(f"Google Ads service initialization error: {e}", exc_info=True)
                        continue
                    
                    # Create campaign
                    campaign_result = await google_service.create_campaign(
                        name=campaign.name,
                        budget_amount=float(campaign.budget_allocation.get(channel, 0)),
                        start_date=campaign.start_date,
                        end_date=campaign.end_date
                    )
                    
                    if campaign_result.get("success"):
                        google_campaign_id = campaign_result.get("campaign_id")
                        
                        # Create ad group
                        ad_group_result = await google_service.create_ad_group(
                            campaign_id=google_campaign_id,
                            name=f"{campaign.name} Ad Group"
                        )
                        
                        if ad_group_result.get("success"):
                            ad_group_id = ad_group_result.get("ad_group_id")
                            
                            # Create ad
                            headlines = ad_copy.get("headlines", [])
                            descriptions = ad_copy.get("descriptions", [])
                            
                            # Determine final URL - check multiple sources
                            logger.info(f"DEBUG: Resolving URL. ad_copy keys: {ad_copy.keys()}")
                            logger.info(f"DEBUG: ad_copy.final_url: {ad_copy.get('final_url')}")
                            logger.info(f"DEBUG: ad_copy.link_url: {ad_copy.get('link_url')}")
                            logger.info(f"DEBUG: plan.landing_page_url: {plan.get('landing_page_url')}")
                            logger.info(f"DEBUG: plan.website_url: {plan.get('website_url')}")
                            logger.info(f"DEBUG: tenant.website_url: {website_url}")
                            
                            final_url_val = (
                                ad_copy.get("final_url") or 
                                ad_copy.get("link_url") or 
                                plan.get("landing_page_url") or 
                                plan.get("website_url") or
                                website_url
                            )
                            
                            if not final_url_val:
                                errors.append(f"Google Ads: No landing page URL found. Please set a website URL in settings or in the ad plan.")
                                continue
                                
                            ad_result = await google_service.create_ad(
                                ad_group_id=ad_group_id,
                                headlines=headlines[:15] if headlines else ["Discover Our Services", "Best Solutions", "Get Started Today"],
                                descriptions=descriptions[:4] if descriptions else ["Transform your business", "See results today"],
                                final_url=final_url_val
                            )
                            
                            if ad_result.get("success"):
                                # Create campaign asset record
                                asset = CampaignAsset(
                                    campaign_id=campaign.id,
                                    asset_type="ad",
                                    platform="google_ads",
                                    platform_asset_id=ad_result.get("ad_id"),
                                    status="active",
                                    meta_data={
                                        "campaign_id": google_campaign_id,
                                        "ad_group_id": ad_group_id,
                                        "ad_id": ad_result.get("ad_id")
                                    }
                                )
                                db.add(asset)
                                created_assets.append(f"Google Ads: {ad_result.get('ad_id')}")
                
                elif channel == "meta_ads":
                    # Create Meta Ads campaign
                    # Get ad account ID from integration organizations array
                    ad_account_id = None
                    page_id = None
                    
                    # Extract ad account ID from organizations array
                    if integration.organizations and isinstance(integration.organizations, list):
                        # Find the first active ad account
                        for org in integration.organizations:
                            ad_account_id = org.get("ad_account_id") or org.get("id")
                            if ad_account_id:
                                break
                    
                    # Fallback to meta_data
                    if not ad_account_id and integration.meta_data:
                        ad_account_id = integration.meta_data.get("ad_account_id")
                    
                    if not ad_account_id:
                        errors.append("Meta Ads: No ad account ID found. Please reconnect your Meta Ads account.")
                        continue
                    
                    logger.info(f"Meta Ads: Using ad account ID: {ad_account_id}")
                    
                    meta_service = MetaAdsCampaignService(
                        access_token=integration.access_token,
                        ad_account_id=ad_account_id
                    )
                    
                    # Get page ID from integration pages or organizations
                    pages = integration.pages or []
                    if pages and isinstance(pages, list) and len(pages) > 0:
                        page_id = pages[0].get("id") if isinstance(pages[0], dict) else pages[0]
                    
                    # If no page from pages, try to get from organizations
                    if not page_id and integration.organizations:
                        for org in integration.organizations:
                            if org.get("page_id"):
                                page_id = org.get("page_id")
                                break
                    
                    logger.info(f"Meta Ads: Using page ID: {page_id}")
                    
                    # Create campaign
                    campaign_result = await meta_service.create_campaign(
                        name=campaign.name,
                        objective=plan.get("objective", "LINK_CLICKS"),
                        daily_budget=float(campaign.budget_allocation.get(channel, 0)),
                        status="PAUSED"  # Start paused, user can activate later
                    )
                    
                    if campaign_result.get("success"):
                        meta_campaign_id = campaign_result.get("campaign_id")
                        
                        # Create ad set with bid_amount if available
                        bid_amount = plan.get("bid_amount")
                        ad_set_result = await meta_service.create_ad_set(
                            campaign_id=meta_campaign_id,
                            name=f"{campaign.name} Ad Set",
                            optimization_goal=plan.get("optimization_goal", "LINK_CLICKS"),
                            billing_event=plan.get("billing_event", "IMPRESSIONS"),
                            bid_amount=bid_amount,
                            start_time=campaign.start_date,
                            end_time=campaign.end_date,
                            page_id=page_id
                        )
                        
                        if ad_set_result.get("success"):
                            ad_set_id = ad_set_result.get("ad_set_id")
                            
                            # Get image URL from ad_copy if available
                            image_url = ad_copy.get("image_url")
                            
                            # Determine link URL - check multiple sources
                            link_url_val = (
                                ad_copy.get("link_url") or 
                                ad_copy.get("final_url") or 
                                plan.get("landing_page_url") or 
                                plan.get("website_url") or 
                                website_url
                            )
                            
                            if not link_url_val:
                                errors.append("Meta Ads: No landing page URL found. Please set a website URL in settings or in the ad plan.")
                                continue

                            # Create ad creative
                            creative_result = await meta_service.create_ad_creative(
                                name=f"{campaign.name} Creative",
                                page_id=page_id,
                                title=ad_copy.get("headlines", [""])[0] if ad_copy.get("headlines") else campaign.name,
                                body=ad_copy.get("descriptions", [""])[0] if ad_copy.get("descriptions") else "",
                                link_url=link_url_val,
                                image_url=image_url
                            )
                            
                            if creative_result.get("success"):
                                creative_id = creative_result.get("creative_id")
                                
                                # Create ad
                                ad_result = await meta_service.create_ad(
                                    ad_set_id=ad_set_id,
                                    name=f"{campaign.name} Ad",
                                    creative_id=creative_id,
                                    status="PAUSED"
                                )
                                
                                if ad_result.get("success"):
                                    # Create campaign asset record
                                    asset = CampaignAsset(
                                        campaign_id=campaign.id,
                                        asset_type="ad",
                                        platform="meta_ads",
                                        platform_asset_id=ad_result.get("ad_id"),
                                        status="paused",
                                        meta_data={
                                            "campaign_id": meta_campaign_id,
                                            "ad_set_id": ad_set_id,
                                            "creative_id": creative_id,
                                            "ad_id": ad_result.get("ad_id"),
                                            "ad_account_id": ad_account_id
                                        }
                                    )
                                    db.add(asset)
                                    created_assets.append(f"Meta Ads: {ad_result.get('ad_id')}")
                                else:
                                    errors.append(f"Meta Ads: Failed to create ad: {ad_result.get('error')}")
                            else:
                                errors.append(f"Meta Ads: Failed to create creative: {creative_result.get('error')}")
                        else:
                            errors.append(f"Meta Ads: Failed to create ad set: {ad_set_result.get('error')}")
                    else:
                        errors.append(f"Meta Ads: Failed to create campaign: {campaign_result.get('error')}")
            
            except Exception as e:
                logger.error(f"Error creating campaign for {channel}: {str(e)}")
                errors.append(f"{channel}: {str(e)}")
        
        # Update campaign status
        if created_assets:
            campaign.status = "active"
        else:
            campaign.status = "failed"
        
        await db.commit()
        await db.refresh(campaign)
        
        return {
            "success": len(created_assets) > 0,
            "campaign_id": str(campaign.id),
            "status": campaign.status,
            "created_assets": created_assets,
            "errors": errors
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving campaign: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to approve campaign: {str(e)}"
        )


@router.post("/campaigns", response_model=CampaignResponse)
async def create_campaign(
    request: CampaignCreateRequest,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new campaign with AI-generated plan
    
    The campaign plan is automatically generated based on the provided details.
    """
    try:
        # Create campaign record
        campaign = Campaign(
            tenant_id=current_tenant.id,
            name=request.name,
            description=request.description,
            objective_type=request.objective_type.value if request.objective_type else None,
            campaign_type=request.campaign_type,
            start_date=request.start_date,
            end_date=request.end_date,
            channels=request.channels,
            total_budget=request.total_budget,
            currency=request.currency,
            goal_metrics=request.goal_metrics.model_dump() if request.goal_metrics else None,
            product_brief=request.product_brief,
            creative_preference=request.creative_preference.value if request.creative_preference else "both",
            target_audience=request.target_audience.model_dump() if request.target_audience else None,
            status="draft"
        )
        
        db.add(campaign)
        await db.flush()  # Get the ID
        
        # Generate AI plan
        campaign_data = {
            "name": request.name,
            "description": request.description,
            "objective_type": request.objective_type.value if request.objective_type else "conversions",
            "total_budget": request.total_budget,
            "currency": request.currency,
            "start_date": str(request.start_date) if request.start_date else None,
            "end_date": str(request.end_date) if request.end_date else None,
            "channels": request.channels,
            "product_brief": request.product_brief,
            "creative_preference": request.creative_preference.value if request.creative_preference else "both",
            "target_audience": request.target_audience.model_dump() if request.target_audience else None,
            "goal_metrics": request.goal_metrics.model_dump() if request.goal_metrics else None
        }
        
        try:
            plan = await generate_campaign_plan(
                campaign_data,
                db=db,
                tenant_id=current_tenant.id
            )
            campaign.plan = plan.model_dump()
        except Exception as plan_error:
            logger.warning(f"Plan generation failed, using defaults: {str(plan_error)}")
            # Plan generation failed, but continue with campaign creation
            campaign.plan = None
        
        await db.commit()
        await db.refresh(campaign)
        
        logger.info(f"Created campaign {campaign.id} with plan")
        
        return CampaignResponse(
            id=str(campaign.id),
            name=campaign.name,
            description=campaign.description,
            campaign_type=campaign.campaign_type,
            objective_type=campaign.objective_type,
            start_date=campaign.start_date,
            end_date=campaign.end_date,
            channels=campaign.channels,
            total_budget=float(campaign.total_budget) if campaign.total_budget else None,
            currency=campaign.currency or "USD",
            budget_allocation=None,
            goal_metrics=campaign.goal_metrics,
            status=campaign.status,
            plan=campaign.plan,
            product_brief=campaign.product_brief,
            creative_preference=campaign.creative_preference,
            target_audience=campaign.target_audience,
            metrics=campaign.metrics,
            created_at=campaign.created_at.isoformat() if campaign.created_at else "",
            execution_id=None
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating campaign: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create campaign: {str(e)}"
        )


@router.post("/campaigns/{campaign_id}/generate-plan", response_model=CampaignPlanResponse)
async def generate_plan(
    campaign_id: UUID,
    request: CampaignPlanGenerateRequest = CampaignPlanGenerateRequest(),
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate or regenerate the AI campaign plan
    """
    try:
        # Get campaign
        result = await db.execute(
            select(Campaign).where(
                Campaign.id == campaign_id,
                Campaign.tenant_id == current_tenant.id
            )
        )
        campaign = result.scalar_one_or_none()
        
        if not campaign:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign not found"
            )
        
        # Check if plan exists and regeneration not requested
        if campaign.plan and not request.regenerate:
            # Return existing plan
            return CampaignPlanResponse(
                campaign_id=str(campaign.id),
                plan=CampaignPlan(**campaign.plan),
                generated_at=campaign.updated_at.isoformat() if campaign.updated_at else datetime.utcnow().isoformat()
            )
        
        # Build campaign data for plan generation
        campaign_data = {
            "name": campaign.name,
            "description": campaign.description,
            "objective_type": campaign.objective_type or "conversions",
            "total_budget": float(campaign.total_budget) if campaign.total_budget else 0,
            "currency": campaign.currency or "USD",
            "start_date": str(campaign.start_date) if campaign.start_date else None,
            "end_date": str(campaign.end_date) if campaign.end_date else None,
            "channels": campaign.channels,
            "product_brief": campaign.product_brief,
            "creative_preference": campaign.creative_preference or "both",
            "target_audience": campaign.target_audience,
            "goal_metrics": campaign.goal_metrics
        }
        
        # Generate plan with research
        plan = await generate_campaign_plan(
            campaign_data,
            db=db,
            tenant_id=current_tenant.id
        )
        
        # Save plan
        campaign.plan = plan.model_dump()
        await db.commit()
        
        return CampaignPlanResponse(
            campaign_id=str(campaign.id),
            plan=plan,
            generated_at=datetime.utcnow().isoformat()
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating plan: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate plan: {str(e)}"
        )


@router.patch("/campaigns/{campaign_id}/plan/steps/{step_id}")
async def update_step_status(
    campaign_id: UUID,
    step_id: str,
    request: CampaignStepUpdateRequest,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Update the status of a specific plan step
    """
    try:
        # Get campaign
        result = await db.execute(
            select(Campaign).where(
                Campaign.id == campaign_id,
                Campaign.tenant_id == current_tenant.id
            )
        )
        campaign = result.scalar_one_or_none()
        
        if not campaign:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign not found"
            )
        
        if not campaign.plan:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Campaign has no plan"
            )
        
        # Find and update the step
        plan = campaign.plan
        step_found = False
        for step in plan.get("steps", []):
            if step.get("id") == step_id:
                step["status"] = request.status
                step_found = True
                break
        
        if not step_found:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Step {step_id} not found"
            )
        
        # Save updated plan
        campaign.plan = plan
        await db.commit()
        
        return {
            "success": True,
            "campaign_id": str(campaign.id),
            "step_id": step_id,
            "new_status": request.status
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating step status: {str(e)}")
# ... existing code ...

from app.services.campaign_chat_service import CampaignChatService
from app.services.campaign_asset_service import CampaignAssetService
from app.schemas.campaign_schemas import (
    ChatRequest, ChatResponse, 
    AssetGenerationRequest, AssetResponse
)

# Initialize services (could also be done via dependency injection)
chat_service = CampaignChatService()
asset_service = CampaignAssetService()


@router.post("/campaigns/{campaign_id}/chat", response_model=ChatResponse)
async def campaign_chat(
    campaign_id: UUID,
    request: ChatRequest,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Chat with the AI about the campaign
    """
    try:
        # Get campaign
        result = await db.execute(
            select(Campaign).where(
                Campaign.id == campaign_id,
                Campaign.tenant_id == current_tenant.id
            )
        )
        campaign = result.scalar_one_or_none()
        
        if not campaign:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign not found"
            )
            
        # Call chat service
        response = await chat_service.chat(
            campaign=campaign,
            user_message=request.message,
            history=request.history,
            db=db
        )
        
        return ChatResponse(response=response)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in campaign chat: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat failed: {str(e)}"
        )


@router.post("/campaigns/{campaign_id}/assets/generate", response_model=AssetResponse)
async def generate_campaign_assets(
    campaign_id: UUID,
    request: AssetGenerationRequest,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate creative assets for the campaign
    """
    try:
        # Get campaign
        result = await db.execute(
            select(Campaign).where(
                Campaign.id == campaign_id,
                Campaign.tenant_id == current_tenant.id
            )
        )
        campaign = result.scalar_one_or_none()
        
        if not campaign:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign not found"
            )
            
        # Generate assets
        assets = await asset_service.generate_assets_for_campaign(
            campaign=campaign,
            step_ids=request.step_ids
        )
        
        # Save asset metadata to DB (Optional / Future work)
        # For now, we return them directly to the frontend
        
        return AssetResponse(assets=assets)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating assets: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Asset generation failed: {str(e)}"
        )


def infer_step_task_type(step_title: str, step_description: str, creative_preference: str = "both") -> str:
    """
    Infer the task type for a step based on its title and description.
    
    Returns one of: text_generation, search_thinking, image_generation, video_generation
    """
    title_lower = step_title.lower()
    desc_lower = step_description.lower()
    combined = f"{title_lower} {desc_lower}"
    
    # Image generation keywords
    image_keywords = ["image", "visual", "creative asset", "design", "graphic", "banner", "ad creative"]
    if any(kw in combined for kw in image_keywords):
        if creative_preference == "video":
            return "video_generation"
        return "image_generation"
    
    # Video generation keywords
    video_keywords = ["video", "film", "motion", "animation", "clip"]
    if any(kw in combined for kw in video_keywords):
        return "video_generation"
    
    # Asset creation - depends on creative preference
    if "asset" in combined and "creation" in combined:
        if creative_preference == "video":
            return "video_generation"
        elif creative_preference == "image":
            return "image_generation"
        else:
            return "image_generation"  # Default to image for "both"
    
    # Search/research/analysis keywords
    research_keywords = ["research", "analysis", "analyze", "study", "market", "competitor", "audience", "insight"]
    if any(kw in combined for kw in research_keywords):
        return "search_thinking"
    
    # Default to text generation (strategy, copy, planning, etc.)
    return "text_generation"


@router.post("/campaigns/{campaign_id}/steps/{step_id}/execute", response_model=StepExecuteResponse)
async def execute_campaign_step(
    campaign_id: UUID,
    step_id: str,
    request: StepExecuteRequest = StepExecuteRequest(),
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Execute a campaign plan step using the appropriate Celery task.
    
    The system will infer the task type from the step title/description:
    - text_generation: Strategy, copy, planning content via Gemini
    - search_thinking: Research, analysis via RAG + SERP
    - image_generation: Visual assets via Gemini image model
    - video_generation: Video assets via Veo
    
    Returns an execution ID that can be used to poll for results.
    """
    try:
        # Get campaign
        result = await db.execute(
            select(Campaign).where(
                Campaign.id == campaign_id,
                Campaign.tenant_id == current_tenant.id
            )
        )
        campaign = result.scalar_one_or_none()
        
        if not campaign:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign not found"
            )
        
        if not campaign.plan:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Campaign has no plan"
            )
        
        # Find the step
        plan = campaign.plan
        step_found = None
        step_index = None
        for i, step in enumerate(plan.get("steps", [])):
            if step.get("id") == step_id:
                step_found = step
                step_index = i
                break
        
        if not step_found:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Step {step_id} not found"
            )
        
        # Check if already executing
        if step_found.get("status") == "in_progress":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Step is already executing"
            )
        
        # Infer or use provided task type
        task_type = request.force_task_type
        if not task_type:
            task_type = step_found.get("task_type")
        if not task_type:
            task_type = infer_step_task_type(
                step_found.get("title", ""),
                step_found.get("description", ""),
                campaign.creative_preference or "both"
            )
        
        # Update step status to in_progress
        plan["steps"][step_index]["status"] = "in_progress"
        plan["steps"][step_index]["task_type"] = task_type
        campaign.plan = plan
        await db.commit()
        
        # Import and trigger Celery task
        from app.workers.campaign_creation import execute_campaign_step as celery_execute_step
        
        # Prepare step data for the celery task
        step_data = {
            "id": step_id,
            "title": step_found.get("title", ""),
            "description": step_found.get("description", ""),
            "actions": step_found.get("actions", []),
            "campaign_name": campaign.name,
            "campaign_objective": campaign.objective_type,
            "product_brief": campaign.product_brief,
            "target_audience": campaign.target_audience,
            "creative_preference": campaign.creative_preference
        }
        
        # Send to Celery
        celery_result = celery_execute_step.delay(
            campaign_id=str(campaign_id),
            step_id=step_id,
            tenant_id=str(current_tenant.id),
            task_type=task_type,
            step_data=step_data
        )
        
        # Store execution ID in the step
        plan["steps"][step_index]["execution_id"] = celery_result.id
        campaign.plan = plan
        await db.commit()
        
        logger.info(f"Started execution for step {step_id} with task {celery_result.id}, type: {task_type}")
        
        return StepExecuteResponse(
            campaign_id=str(campaign_id),
            step_id=step_id,
            execution_id=celery_result.id,
            task_type=task_type,
            status="in_progress",
            message=f"Step execution started with task type: {task_type}"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing step: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute step: {str(e)}"
        )


@router.get("/campaigns/{campaign_id}/steps/{step_id}/result", response_model=StepResultResponse)
async def get_step_result(
    campaign_id: UUID,
    step_id: str,
    current_tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Get the execution result for a campaign plan step.
    """
    try:
        # Get campaign
        result = await db.execute(
            select(Campaign).where(
                Campaign.id == campaign_id,
                Campaign.tenant_id == current_tenant.id
            )
        )
        campaign = result.scalar_one_or_none()
        
        if not campaign:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign not found"
            )
        
        if not campaign.plan:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Campaign has no plan"
            )
        
        # Find the step
        step_found = None
        for step in campaign.plan.get("steps", []):
            if step.get("id") == step_id:
                step_found = step
                break
        
        if not step_found:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Step {step_id} not found"
            )
        
        # Return current status and result
        step_result = None
        if step_found.get("result"):
            step_result = StepResult(**step_found["result"])
        
        return StepResultResponse(
            campaign_id=str(campaign_id),
            step_id=step_id,
            status=step_found.get("status", "pending"),
            result=step_result,
            error=step_found.get("result", {}).get("error") if step_found.get("result") else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting step result: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get step result: {str(e)}"
        )
