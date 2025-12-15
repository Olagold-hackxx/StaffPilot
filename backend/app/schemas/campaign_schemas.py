"""
Campaign-related Pydantic schemas for API requests and responses
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import date
from enum import Enum


class ObjectiveType(str, Enum):
    """Campaign objective types"""
    CONVERSIONS = "conversions"
    TRAFFIC = "traffic"
    AWARENESS = "awareness"
    LEADS = "leads"


class CreativePreference(str, Enum):
    """Creative format preferences"""
    IMAGE = "image"
    VIDEO = "video"
    BOTH = "both"


class StepTaskType(str, Enum):
    """Types of tasks a campaign step can execute"""
    TEXT_GENERATION = "text_generation"      # Strategy, copy, planning content via Gemini
    SEARCH_THINKING = "search_thinking"      # Research, analysis via RAG + SERP
    IMAGE_GENERATION = "image_generation"    # Visual assets via Gemini image model
    VIDEO_GENERATION = "video_generation"    # Video assets via Veo


class StepResult(BaseModel):
    """Result of executing a campaign step"""
    content: Optional[str] = Field(None, description="Generated text content")
    image_urls: List[str] = Field(default_factory=list, description="URLs of generated images")
    video_urls: List[str] = Field(default_factory=list, description="URLs of generated videos")
    research_data: Optional[Dict[str, Any]] = Field(None, description="Research/analysis results")
    executed_at: Optional[str] = Field(None, description="ISO timestamp of execution")
    error: Optional[str] = Field(None, description="Error message if execution failed")


class TargetAudience(BaseModel):
    """Target audience configuration"""
    countries: List[str] = Field(default_factory=list, description="Target country codes")
    age_range: Optional[List[int]] = Field(None, description="[min_age, max_age]")
    interests: List[str] = Field(default_factory=list, description="Interest keywords")
    gender: Optional[str] = Field("all", description="all, male, or female")


class GoalMetrics(BaseModel):
    """Campaign goal metrics"""
    target_cpa: Optional[float] = Field(None, description="Target cost per acquisition")
    target_roas: Optional[float] = Field(None, description="Target return on ad spend")
    conversion_count: Optional[int] = Field(None, description="Target conversion count")


# =====================
# Campaign Create Request
# =====================

class CampaignCreateRequest(BaseModel):
    """Request schema for creating a new campaign with enhanced fields"""
    name: str = Field(..., min_length=1, max_length=255, description="Campaign name")
    description: Optional[str] = Field(None, description="Campaign description/goals")
    objective_type: Optional[ObjectiveType] = Field(None, description="Campaign objective")
    campaign_type: Optional[str] = Field(None, description="Campaign type (legacy)")
    
    # Timeline
    start_date: Optional[date] = Field(None, description="Campaign start date")
    end_date: Optional[date] = Field(None, description="Campaign end date")
    
    # Budget
    total_budget: Optional[float] = Field(None, ge=0, description="Total campaign budget")
    currency: str = Field("USD", description="Currency code")
    goal_metrics: Optional[GoalMetrics] = Field(None, description="Campaign goal metrics")
    
    # Channels
    channels: List[str] = Field(..., min_length=1, description="Marketing channels")
    
    # Product and creative
    product_brief: Optional[str] = Field(None, description="Product/service description")
    creative_preference: CreativePreference = Field(CreativePreference.BOTH, description="Creative format preference")
    
    # Target audience
    target_audience: Optional[TargetAudience] = Field(None, description="Target audience configuration")
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Summer Sale 2026",
                "description": "Drive conversions for our annual summer clearance. 50% off all inventory.",
                "objective_type": "conversions",
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
                "total_budget": 5000,
                "currency": "USD",
                "channels": ["google_ads", "meta_ads"],
                "product_brief": "Fashion retailer summer collection clearance",
                "creative_preference": "both",
                "target_audience": {
                    "countries": ["US", "CA"],
                    "age_range": [25, 45],
                    "interests": ["fashion", "online shopping", "summer style"]
                }
            }
        }


# =====================
# Campaign Plan Schemas
# =====================

class CampaignPlanStep(BaseModel):
    """A single step in the AI-generated campaign plan"""
    id: str = Field(..., description="Unique step identifier (e.g., 'step_1')")
    title: str = Field(..., description="Step title")
    description: str = Field(..., description="What this step accomplishes")
    actions: List[str] = Field(default_factory=list, description="Specific actions to take")
    time_estimate: Optional[str] = Field(None, description="Estimated time (e.g., '2 hours')")
    status: str = Field("pending", description="pending, in_progress, completed, failed")
    task_type: Optional[str] = Field(None, description="Task type: text_generation, search_thinking, image_generation, video_generation")
    result: Optional[StepResult] = Field(None, description="Execution result with generated content/media")
    execution_id: Optional[str] = Field(None, description="Celery task ID for tracking execution")


class CampaignPlanAdSet(BaseModel):
    """Recommended ad set configuration"""
    name: str = Field(..., description="Ad set name")
    audience_type: str = Field(..., description="lookalike, interest, or retargeting")
    description: str = Field(..., description="Who this targets")
    budget_percentage: int = Field(..., ge=0, le=100, description="Percentage of total budget")


class CampaignPlan(BaseModel):
    """Full AI-generated campaign plan structure"""
    overview: str = Field(..., description="2-3 sentence strategic summary")
    steps: List[CampaignPlanStep] = Field(..., description="Step-by-step execution plan")
    recommended_ad_sets: List[CampaignPlanAdSet] = Field(default_factory=list, description="Recommended ad sets")
    priority_metrics: List[str] = Field(default_factory=list, description="Priority metrics to track")
    research_insights: List[str] = Field(default_factory=list, description="Key insights from RAG/SERP research")
    
    class Config:
        json_schema_extra = {
            "example": {
                "overview": "A conversion-focused campaign targeting fashion enthusiasts with compelling summer sale messaging across Google and Meta platforms.",
                "steps": [
                    {
                        "id": "step_1",
                        "title": "Audience Research",
                        "description": "Define and segment target audiences based on demographics and interests",
                        "actions": ["Analyze existing customer data", "Define lookalike audiences", "Identify interest targets"],
                        "time_estimate": "2 hours",
                        "status": "pending"
                    },
                    {
                        "id": "step_2", 
                        "title": "Creative Strategy",
                        "description": "Develop messaging angles and creative concepts",
                        "actions": ["Draft 5-10 headline variations", "Define visual style", "Plan video storyboard"],
                        "time_estimate": "4 hours",
                        "status": "pending"
                    }
                ],
                "recommended_ad_sets": [
                    {
                        "name": "Lookalike - Purchasers",
                        "audience_type": "lookalike",
                        "description": "Users similar to existing customers who made purchases",
                        "budget_percentage": 50
                    },
                    {
                        "name": "Interest - Fashion Enthusiasts",
                        "audience_type": "interest",
                        "description": "Users interested in fashion, shopping, summer style",
                        "budget_percentage": 30
                    },
                    {
                        "name": "Retargeting - Website Visitors",
                        "audience_type": "retargeting",
                        "description": "Users who visited the website in the last 30 days",
                        "budget_percentage": 20
                    }
                ],
                "priority_metrics": ["CPA", "ROAS", "CTR"]
            }
        }


# =====================
# API Response Schemas
# =====================

class CampaignResponse(BaseModel):
    """Response schema for a single campaign"""
    id: str
    name: str
    description: Optional[str] = None
    objective_type: Optional[str] = None
    campaign_type: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    channels: List[str]
    total_budget: Optional[float] = None
    currency: str = "USD"
    budget_allocation: Optional[Dict[str, float]] = None
    goal_metrics: Optional[Dict[str, Any]] = None
    status: str
    plan: Optional[CampaignPlan] = None
    product_brief: Optional[str] = None
    creative_preference: Optional[str] = None
    target_audience: Optional[Dict[str, Any]] = None
    metrics: Optional[Dict[str, Any]] = None
    # Performance Max fields
    final_url: Optional[str] = None
    business_name: Optional[str] = None
    call_to_action: Optional[str] = None
    headlines: Optional[List[Dict[str, Any]]] = None
    descriptions: Optional[List[Dict[str, Any]]] = None
    ad_strength: Optional[str] = None
    created_at: str
    execution_id: Optional[str] = None


class CampaignListResponse(BaseModel):
    """Response schema for listing campaigns"""
    campaigns: List[CampaignResponse]


class CampaignPlanGenerateRequest(BaseModel):
    """Request to generate/regenerate campaign plan"""
    regenerate: bool = Field(False, description="Force regeneration of existing plan")


class CampaignStepUpdateRequest(BaseModel):
    """Request to update a plan step's status"""
    status: str = Field(..., description="New status: pending, in_progress, completed")


class CampaignPlanResponse(BaseModel):
    """Response containing generated campaign plan"""
    campaign_id: str
    plan: CampaignPlan
    generated_at: str


# =====================
# Chat & Asset Schemas
# =====================

class ChatRequest(BaseModel):
    """Request for AI chat message"""
    message: str = Field(..., description="User message")
    history: Optional[List[Dict[str, Any]]] = Field(None, description="Conversation history")


class ChatResponse(BaseModel):
    """Response from AI chat"""
    response: str
    

class AssetGenerationRequest(BaseModel):
    """Request to generate assets from plan"""
    step_ids: Optional[List[str]] = Field(None, description="Specific steps to generate assets for (optional)")
    force_regenerate: bool = Field(False, description="Regenerate existing assets")


class AssetType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"


class GeneratedAsset(BaseModel):
    """A single generated asset"""
    id: str
    type: AssetType
    content: str = Field(..., description="Base64 content or URL")
    prompt: str
    aspect_ratio: str
    created_at: str
    step_id: Optional[str] = None


class AssetResponse(BaseModel):
    """Response containing generated assets"""
    assets: List[GeneratedAsset]
    status: str = Field("completed", description="pending, in_progress, completed")


# =====================
# Step Execution Schemas
# =====================

class StepExecuteRequest(BaseModel):
    """Request to execute a campaign plan step"""
    force_task_type: Optional[str] = Field(None, description="Override inferred task type")


class StepExecuteResponse(BaseModel):
    """Response from step execution request"""
    campaign_id: str
    step_id: str
    execution_id: str
    task_type: str
    status: str = Field("in_progress", description="pending, in_progress, completed, failed")
    message: str = Field("Step execution started")


class StepResultResponse(BaseModel):
    """Response containing step execution result"""
    campaign_id: str
    step_id: str
    status: str
    result: Optional[StepResult] = None
    error: Optional[str] = None
