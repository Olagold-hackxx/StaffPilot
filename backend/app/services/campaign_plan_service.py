"""
Campaign Plan Generation Service - AI-powered campaign plan creation
"""
import json
from typing import Optional, Dict, Any
from datetime import datetime

from app.services.llm.factory import create_llm_service
from app.schemas.campaign_schemas import (
    CampaignPlan, 
    CampaignPlanStep, 
    CampaignPlanAdSet,
    CampaignCreateRequest
)
from app.utils.logger import logger


PLAN_GENERATION_SYSTEM_PROMPT = """You are a growth marketing strategist. Given campaign details, create a comprehensive execution plan.

Output must be valid JSON with this exact structure:
{
  "overview": "2-3 sentence strategic summary",
  "steps": [
    {
      "id": "step_1",
      "title": "Step title",
      "description": "What this step accomplishes",
      "actions": ["Specific action 1", "Specific action 2"],
      "time_estimate": "X hours/days",
      "status": "pending"
    }
  ],
  "recommended_ad_sets": [
    {
      "name": "Adset name",
      "audience_type": "lookalike|interest|retargeting",
      "description": "Who this targets",
      "budget_percentage": 50
    }
  ],
  "priority_metrics": ["metric1", "metric2", "metric3"]
}

Requirements:
- Create 4-6 actionable steps covering: audience research, creative strategy, asset creation, campaign structure, review & launch
- Steps should be specific to the campaign objective and channels
- Time estimates should be realistic
- Ad set budget percentages must sum to 100
- Priority metrics should align with the campaign objective
- All steps should start with status "pending"
"""


def build_plan_generation_prompt(campaign_data: Dict[str, Any]) -> str:
    """Build the user prompt for plan generation from campaign data"""
    
    # Extract and format campaign data
    name = campaign_data.get("name", "Unnamed Campaign")
    description = campaign_data.get("description", "No description provided")
    objective_type = campaign_data.get("objective_type", "conversions")
    budget = campaign_data.get("total_budget", 0)
    currency = campaign_data.get("currency", "USD")
    start_date = campaign_data.get("start_date", "Not specified")
    end_date = campaign_data.get("end_date", "Not specified")
    channels = campaign_data.get("channels", [])
    product_brief = campaign_data.get("product_brief", "")
    creative_preference = campaign_data.get("creative_preference", "both")
    
    # Target audience
    target_audience = campaign_data.get("target_audience", {})
    countries = target_audience.get("countries", []) if target_audience else []
    age_range = target_audience.get("age_range", []) if target_audience else []
    interests = target_audience.get("interests", []) if target_audience else []
    
    # Goal metrics
    goal_metrics = campaign_data.get("goal_metrics", {})
    
    prompt = f"""Campaign: {name}
Description: {description}
Objective: {objective_type}
Budget: {budget} {currency}
Timeline: {start_date} to {end_date}
Channels: {', '.join(channels) if channels else 'Not specified'}
Creative preference: {creative_preference}

Product/Service Brief:
{product_brief if product_brief else 'Not provided'}

Target Audience:
- Countries: {', '.join(countries) if countries else 'Global'}
- Age range: {f'{age_range[0]}-{age_range[1]}' if age_range and len(age_range) >= 2 else 'Not specified'}
- Interests: {', '.join(interests) if interests else 'Not specified'}

Goal Metrics:
{json.dumps(goal_metrics, indent=2) if goal_metrics else 'Not specified'}

Generate a comprehensive campaign execution plan in JSON format."""

    return prompt


async def generate_campaign_plan(
    campaign_data: Dict[str, Any],
    provider: Optional[str] = None,
    db: Optional[Any] = None,
    tenant_id: Optional[Any] = None
) -> CampaignPlan:
    """
    Generate an AI-powered campaign plan with Research (RAG + SERP)
    
    Args:
        campaign_data: Dictionary with campaign details
        provider: LLM provider to use (optional, uses default)
        db: Database session (optional, for RAG)
        tenant_id: Tenant ID (optional, for RAG)
        
    Returns:
        CampaignPlan object with structured plan
    """
    try:
        # 1. Research Phase
        research_context = ""
        keywords_found = []
        
        # RAG Retrieval
        if db and tenant_id:
            try:
                from app.services.rag_service import RAGService
                rag_service = RAGService(db, tenant_id)
                query = f"{campaign_data.get('objective_type', '')} {campaign_data.get('product_brief', '')} {campaign_data.get('description', '')}"
                context_chunks = rag_service.retrieve_relevant_context(query, limit=5)
                if context_chunks:
                    research_context += "\nKNOWLEDGE BASE CONTEXT:\n"
                    for chunk in context_chunks:
                        research_context += f"- {chunk['content'][:300]}...\n"
            except Exception as e:
                logger.warning(f"RAG retrieval failed during plan generation: {e}")

        # SERP Keyword Research
        try:
            from app.services.integrations.seo.serpapi_service import SerpAPIService
            serp_service = SerpAPIService()
            # Research topic based on product/service
            topic = campaign_data.get('product_brief') or campaign_data.get('name')
            if topic:
                research_result = await serp_service.keyword_research(topic[:100], limit=10)
                if research_result and "keywords" in research_result:
                    keywords_found = [k['keyword'] for k in research_result['keywords'] if isinstance(k, dict) and 'keyword' in k]
                    if keywords_found:
                        research_context += f"\nTOP SEARCH KEYWORDS FOR '{topic}':\n" + ", ".join(keywords_found)
        except Exception as e:
            logger.warning(f"SERP research failed during plan generation: {e}")

        # Create LLM service
        llm_service = create_llm_service(provider=provider)
        
        # Build prompt with added research
        prompt = build_plan_generation_prompt(campaign_data)
        if research_context:
            prompt += f"\n\nRESEARCH INSIGHTS:\n{research_context}"
        
        logger.info(f"Generating campaign plan for: {campaign_data.get('name', 'Unknown')}")
        
        # Generate JSON response
        plan_json = await llm_service.generate_json(
            prompt=prompt,
            system_instruction=PLAN_GENERATION_SYSTEM_PROMPT,
            temperature=0.5
        )
        
        # Parse and validate the response
        plan = parse_plan_response(plan_json)
        
        # Add research insights
        insights = []
        if keywords_found:
            insights.append(f"Top Keywords identified: {', '.join(keywords_found[:5])}")
        if research_context and "KNOWLEDGE BASE CONTEXT" in research_context:
            insights.append("Incorporated insights from company knowledge base documents.")
            
        plan.research_insights = insights
        
        # Add research step explicitly if not present
        if keywords_found and plan.steps:
            # Ensure the first step mentions the research done
            plan.steps[0].description += f" (Preliminary analysis identified keywords: {', '.join(keywords_found[:3])}...)"
        
        logger.info(f"Generated plan with {len(plan.steps)} steps")
        
        return plan
        
    except Exception as e:
        logger.error(f"Failed to generate campaign plan: {str(e)}")
        # Return a default plan on error
        return create_default_plan(campaign_data)


def parse_plan_response(plan_json: Dict[str, Any]) -> CampaignPlan:
    """
    Parse and validate the LLM response into a CampaignPlan
    
    Args:
        plan_json: Raw JSON from LLM
        
    Returns:
        Validated CampaignPlan object
    """
    try:
        # Extract steps
        steps = []
        for i, step_data in enumerate(plan_json.get("steps", [])):
            step = CampaignPlanStep(
                id=step_data.get("id", f"step_{i+1}"),
                title=step_data.get("title", f"Step {i+1}"),
                description=step_data.get("description", ""),
                actions=step_data.get("actions", []),
                time_estimate=step_data.get("time_estimate"),
                status=step_data.get("status", "pending")
            )
            steps.append(step)
        
        # Extract ad sets
        ad_sets = []
        for adset_data in plan_json.get("recommended_ad_sets", []):
            ad_set = CampaignPlanAdSet(
                name=adset_data.get("name", "Ad Set"),
                audience_type=adset_data.get("audience_type", "interest"),
                description=adset_data.get("description", ""),
                budget_percentage=adset_data.get("budget_percentage", 0)
            )
            ad_sets.append(ad_set)
        
        # Create plan
        return CampaignPlan(
            overview=plan_json.get("overview", "Campaign plan generated."),
            steps=steps,
            recommended_ad_sets=ad_sets,
            priority_metrics=plan_json.get("priority_metrics", ["CPA", "ROAS", "CTR"])
        )
        
    except Exception as e:
        logger.error(f"Failed to parse plan response: {str(e)}")
        raise ValueError(f"Invalid plan structure: {str(e)}")


def create_default_plan(campaign_data: Dict[str, Any]) -> CampaignPlan:
    """Create a default plan when AI generation fails"""
    
    objective = campaign_data.get("objective_type", "conversions")
    channels = campaign_data.get("channels", [])
    creative_pref = campaign_data.get("creative_preference", "both")
    
    # Default steps based on objective
    steps = [
        CampaignPlanStep(
            id="step_1",
            title="Audience Research",
            description="Define and segment target audiences based on demographics, interests, and behaviors",
            actions=[
                "Review existing customer data",
                "Define lookalike audiences",
                "Identify interest-based targets",
                "Set geographic and demographic targeting"
            ],
            time_estimate="2-4 hours",
            status="pending"
        ),
        CampaignPlanStep(
            id="step_2",
            title="Creative Strategy",
            description="Develop messaging angles and creative concepts aligned with campaign objectives",
            actions=[
                "Draft 5-10 headline variations",
                "Write compelling ad descriptions",
                "Define visual style and mood",
                "Plan creative formats for each platform"
            ],
            time_estimate="4-6 hours",
            status="pending"
        ),
        CampaignPlanStep(
            id="step_3",
            title="Asset Creation",
            description=f"Create {'images and videos' if creative_pref == 'both' else creative_pref + 's'} for all placements",
            actions=[
                "Generate ad creatives using AI",
                "Review and refine generated assets",
                "Ensure brand consistency",
                "Optimize for each platform's specifications"
            ],
            time_estimate="4-8 hours",
            status="pending"
        ),
        CampaignPlanStep(
            id="step_4",
            title="Campaign Structure",
            description="Configure campaigns, ad sets, and targeting in ad platforms",
            actions=[
                f"Set up campaigns in {', '.join(channels) if channels else 'selected platforms'}",
                "Configure ad set budget allocation",
                "Set bidding strategies based on objectives",
                "Enable tracking and conversion setup"
            ],
            time_estimate="2-3 hours",
            status="pending"
        ),
        CampaignPlanStep(
            id="step_5",
            title="Review & Launch",
            description="Final review of all components before launching the campaign",
            actions=[
                "Review all ad creatives",
                "Verify targeting settings",
                "Confirm budget and schedule",
                "Launch campaign and monitor initial performance"
            ],
            time_estimate="1-2 hours",
            status="pending"
        )
    ]
    
    # Default ad sets
    ad_sets = [
        CampaignPlanAdSet(
            name="Lookalike - High Value",
            audience_type="lookalike",
            description="Users similar to existing high-value customers",
            budget_percentage=50
        ),
        CampaignPlanAdSet(
            name="Interest - Core Audience",
            audience_type="interest",
            description="Users matching interest and demographic targeting",
            budget_percentage=30
        ),
        CampaignPlanAdSet(
            name="Retargeting - Website Visitors",
            audience_type="retargeting",
            description="Users who visited the website recently",
            budget_percentage=20
        )
    ]
    
    # Priority metrics based on objective
    metrics_by_objective = {
        "conversions": ["CPA", "ROAS", "Conversion Rate"],
        "traffic": ["CTR", "CPC", "Clicks"],
        "awareness": ["Impressions", "Reach", "CPM"],
        "leads": ["CPL", "Lead Volume", "Conversion Rate"]
    }
    
    return CampaignPlan(
        overview=f"A {objective}-focused campaign targeting your defined audience across {', '.join(channels) if channels else 'multiple platforms'}. This plan provides a structured approach from audience research through launch.",
        steps=steps,
        recommended_ad_sets=ad_sets,
        priority_metrics=metrics_by_objective.get(objective, ["CPA", "ROAS", "CTR"])
    )


async def update_plan_step_status(
    plan: CampaignPlan,
    step_id: str,
    new_status: str
) -> CampaignPlan:
    """
    Update a step's status in the plan
    
    Args:
        plan: Current campaign plan
        step_id: ID of the step to update
        new_status: New status (pending, in_progress, completed)
        
    Returns:
        Updated CampaignPlan
    """
    # Convert to dict, update, and convert back
    plan_dict = plan.model_dump()
    
    for step in plan_dict["steps"]:
        if step["id"] == step_id:
            step["status"] = new_status
            break
    
    return CampaignPlan(**plan_dict)
