"""
Campaign Creation Worker - Celery tasks for campaign creation
"""
import asyncio
import uuid
from typing import Dict, Any
from uuid import UUID
from datetime import datetime, timedelta
from decimal import Decimal

from app.workers import celery_app
from app.utils.logger import logger


@celery_app.task(name="campaign.create_execution", bind=True, max_retries=1)
def execute_campaign_creation(
    self,
    execution_id: str,
    tenant_id: str,
    assistant_id: str,
    request_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Main Celery task for campaign creation execution
    
    This orchestrates the entire workflow:
    1. RAG retrieval for context
    2. Campaign plan generation using AI agent
    3. Ad copy generation
    4. Campaign structure creation (draft status)
    5. User review and approval
    6. Campaign launch to platforms
    
    Args:
        execution_id: Execution UUID string
        tenant_id: Tenant UUID string
        assistant_id: Assistant UUID string
        request_data: Request data with campaign objective, budget, channels, etc.
    
    Returns:
        Execution result with campaign draft
    """
    try:
        def _execute():
            from app.db.session import create_worker_session_factory
            from app.services.rag_service import RAGService
            from app.services.agents.digital_marketer_agent import DigitalMarketerAgent
            from app.models.campaign import Campaign
            from app.models.tenant import Tenant
            from app.models.agent_execution import AgentExecution
            from sqlalchemy import select
            from datetime import datetime, timezone
            import json
            
            # Create a new session factory for this worker task
            SessionFactory = create_worker_session_factory()
            db = SessionFactory()
            try:
                # Update status to running (sync)
                result = db.execute(
                    select(AgentExecution).where(AgentExecution.id == UUID(execution_id))
                )
                execution = result.scalar_one_or_none()
                if execution:
                    execution.status = "running"
                    if not execution.started_at:
                        execution.started_at = datetime.now(timezone.utc)
                    db.commit()
                    db.refresh(execution)
                
                # Task tracking
                tasks = []
                
                logger.info("=" * 80)
                logger.info("CAMPAIGN CREATION EXECUTION STARTED")
                logger.info(f"Execution ID: {execution_id}")
                logger.info(f"Tenant ID: {tenant_id}")
                logger.info(f"Assistant ID: {assistant_id}")
                logger.info("=" * 80)
                
                # Get tenant and website URL (sync)
                tenant_result = db.execute(
                    select(Tenant).where(Tenant.id == UUID(tenant_id))
                )
                tenant = tenant_result.scalar_one_or_none()
                website_url = tenant.website_url if tenant and tenant.website_url else ""
                
                # Step 1: RAG retrieval (sync)
                logger.info("[TASK 1/5] Starting RAG retrieval...")
                try:
                    rag_service = RAGService(db, UUID(tenant_id))
                    user_request = request_data.get("objective", "") + " " + request_data.get("description", "")
                    context = rag_service.retrieve_relevant_context(
                        query=user_request,
                        assistant_id=UUID(assistant_id),
                        limit=10
                    )
                    tasks.append({"task": "RAG Retrieval", "status": "PASSED"})
                    logger.info(f"[TASK 1/5] ✓ PASSED - Retrieved {len(context)} relevant chunks")
                except Exception as e:
                    logger.error(f"[TASK 1/5] ✗ FAILED - RAG retrieval failed: {str(e)}")
                    tasks.append({"task": "RAG Retrieval", "status": "FAILED", "error": str(e)})
                    context = ""
                
                # Step 2: Get tenant config
                tenant_config = tenant.custom_config if tenant and tenant.custom_config else {}
                
                # Step 3: Initialize agent
                logger.info("[TASK 2/5] Initializing AI agent...")
                try:
                    agent = DigitalMarketerAgent(tenant_config=tenant_config)
                    tasks.append({"task": "Agent Initialization", "status": "PASSED"})
                    logger.info("[TASK 2/5] ✓ PASSED - Agent initialized")
                except Exception as e:
                    logger.error(f"[TASK 2/5] ✗ FAILED - Agent initialization failed: {str(e)}")
                    tasks.append({"task": "Agent Initialization", "status": "FAILED", "error": str(e)})
                    raise
                
                # Step 4: Generate campaign plan using agent
                logger.info("[TASK 3/5] Generating campaign plan...")
                try:
                    # Extract all campaign fields
                    campaign_name = request_data.get("name", request_data.get("objective", "Campaign"))
                    campaign_objective = request_data.get("objective", "")
                    description = request_data.get("description", "")
                    budget = request_data.get("budget", 0)
                    start_date_str = request_data.get("start_date")
                    end_date_str = request_data.get("end_date")
                    channels = request_data.get("channels", ["google_ads", "meta_ads"])
                    product_brief = request_data.get("product_brief", "")
                    creative_preference = request_data.get("creative_preference", "both")
                    
                    # Target audience
                    target_audience_data = request_data.get("target_audience", {})
                    target_audience_text = tenant.target_audience if tenant else ""
                    if target_audience_data:
                        countries = target_audience_data.get("countries", [])
                        age_range = target_audience_data.get("age_range")
                        interests_list = target_audience_data.get("interests", [])
                        
                        audience_parts = []
                        if countries:
                            audience_parts.append(f"Countries: {', '.join(countries)}")
                        if age_range and len(age_range) == 2:
                            audience_parts.append(f"Age: {age_range[0]}-{age_range[1]}")
                        if interests_list:
                            audience_parts.append(f"Interests: {', '.join(interests_list)}")
                        
                        if audience_parts:
                            target_audience_text = "; ".join(audience_parts)
                        elif not target_audience_text:
                            target_audience_text = "General audience"
                    
                    # Calculate duration if dates provided
                    duration_days = 30  # default
                    if start_date_str and end_date_str:
                        try:
                            start_dt = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
                            end_dt = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
                            duration_days = (end_dt - start_dt).days
                        except Exception:
                            pass
                    
                    # Build enhanced request with structured JSON output requirement
                    enhanced_request = f"""You are a growth marketing strategist. Create a comprehensive campaign execution plan.

CAMPAIGN DETAILS:
- Campaign Name: {campaign_name}
- Objective: {campaign_objective}
- Description: {description if description else 'Not provided'}
- Target Audience: {target_audience_text}
- Budget: ${budget}
- Duration: {duration_days} days
- Channels: {', '.join(channels)}
- Product/Service: {product_brief if product_brief else 'Not provided'}
- Creative Preference: {creative_preference}
- Website URL: {website_url}

CONTEXT FROM KNOWLEDGE BASE:
{context}

REQUIRED OUTPUT FORMAT - You MUST return valid JSON only with this exact structure:

{{
  "overview": "2-3 sentence strategic summary of the recommended approach",
  "steps": [
    {{
      "id": "step_1",
      "title": "Step title (e.g., Audience Research)",
      "description": "What this step accomplishes",
      "actions": ["Specific action 1", "Specific action 2"],
      "time_estimate": "X hours or X days"
    }},
    {{
      "id": "step_2",
      "title": "Creative Strategy",
      "description": "Define messaging angles and formats",
      "actions": ["Action 1", "Action 2"],
      "time_estimate": "X hours"
    }},
    {{
      "id": "step_3",
      "title": "Asset Creation",
      "description": "Generate creatives",
      "actions": ["Action 1", "Action 2"],
      "time_estimate": "X days"
    }},
    {{
      "id": "step_4",
      "title": "Campaign Structure",
      "description": "Set up adsets and targeting",
      "actions": ["Action 1", "Action 2"],
      "time_estimate": "X hours"
    }},
    {{
      "id": "step_5",
      "title": "Review & Launch",
      "description": "Final review and deployment",
      "actions": ["Action 1", "Action 2"],
      "time_estimate": "X hours"
    }}
  ],
  "recommended_ad_sets": [
    {{
      "name": "Lookalike - Purchasers",
      "audience_type": "lookalike",
      "description": "Who this targets",
      "budget_percentage": 50,
      "platforms": ["meta_ads"]
    }},
    {{
      "name": "Interest Targeting",
      "audience_type": "interest",
      "description": "Who this targets",
      "budget_percentage": 30,
      "platforms": ["meta_ads", "google_ads"]
    }},
    {{
      "name": "Retargeting",
      "audience_type": "retargeting",
      "description": "Who this targets",
      "budget_percentage": 20,
      "platforms": ["meta_ads", "google_ads"]
    }}
  ],
  "priority_metrics": ["CPA", "ROAS", "CTR"],
  "ad_copy": {{
    "meta_ads": {{
      "headlines": ["Headline 1", "Headline 2", "Headline 3"],
      "descriptions": ["Description 1", "Description 2"]
    }},
    "google_ads": {{
      "headlines": ["Headline 1", "Headline 2", "Headline 3"],
      "descriptions": ["Description 1", "Description 2"]
    }}
  }},
  "budget_allocation": {{
    "meta_ads": 50,
    "google_ads": 50
  }}
}}

IMPORTANT: 
- Return ONLY valid JSON, no additional text before or after
- Budget percentages must sum to 100
- Include the website URL ({website_url}) in all ad copy where links are needed
- Make recommendations specific to the channels: {', '.join(channels)}
- Ensure steps are actionable and time estimates are realistic
"""
                    
                    # Agent.execute is async, so we need to handle it
                    try:
                        agent_loop = asyncio.get_event_loop()
                    except RuntimeError:
                        agent_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(agent_loop)
                    agent_result = agent_loop.run_until_complete(agent.execute(enhanced_request))
                    
                    if not agent_result.get("success"):
                        raise Exception(agent_result.get("error", "Campaign plan generation failed"))
                    
                    # Parse agent result to extract structured campaign plan
                    generated_output = agent_result.get("result", "")
                    
                    # Try to parse JSON from response (might be embedded in text)
                    import json
                    import re
                    campaign_plan_json = None
                    
                    # Try to find JSON in the response
                    json_match = re.search(r'\{.*\}', generated_output, re.DOTALL)
                    if json_match:
                        try:
                            campaign_plan_json = json.loads(json_match.group())
                        except json.JSONDecodeError:
                            logger.warning("Found JSON-like structure but failed to parse, using fallback")
                    
                    # If parsing failed, try parsing the entire output
                    if not campaign_plan_json:
                        try:
                            campaign_plan_json = json.loads(generated_output.strip())
                        except json.JSONDecodeError:
                            logger.warning("Failed to parse JSON from agent response, creating fallback plan")
                    
                    # Build structured campaign plan
                    if campaign_plan_json:
                        # Use parsed JSON structure
                        campaign_plan = {
                            "overview": campaign_plan_json.get("overview", ""),
                            "steps": campaign_plan_json.get("steps", []),
                            "recommended_ad_sets": campaign_plan_json.get("recommended_ad_sets", []),
                            "priority_metrics": campaign_plan_json.get("priority_metrics", ["CPA", "ROAS", "CTR"]),
                            "ad_copy": campaign_plan_json.get("ad_copy", {}),
                            "budget_allocation": campaign_plan_json.get("budget_allocation", {}),
                            # Preserve original fields
                            "objective": campaign_objective,
                            "target_audience": target_audience_text,
                            "budget": budget,
                            "duration_days": duration_days,
                            "channels": channels,
                            "product_brief": product_brief,
                            "creative_preference": creative_preference
                        }
                    else:
                        # Fallback: create basic structure from text output
                        logger.warning("Using fallback plan structure - agent did not return valid JSON")
                        budget_per_channel = 100 / len(channels) if channels else 100
                        campaign_plan = {
                            "overview": generated_output[:500] if generated_output else "Campaign plan generated",
                            "steps": [
                                {
                                    "id": "step_1",
                                    "title": "Audience Research",
                                    "description": "Define target audience segments",
                                    "actions": ["Research audience insights", "Define personas"],
                                    "time_estimate": "2-4 hours"
                                },
                                {
                                    "id": "step_2",
                                    "title": "Creative Strategy",
                                    "description": "Develop messaging and creative concepts",
                                    "actions": ["Create ad copy", "Design creatives"],
                                    "time_estimate": "1-2 days"
                                },
                                {
                                    "id": "step_3",
                                    "title": "Campaign Setup",
                                    "description": "Configure campaigns and targeting",
                                    "actions": ["Set up adsets", "Configure targeting"],
                                    "time_estimate": "4-6 hours"
                                },
                                {
                                    "id": "step_4",
                                    "title": "Review & Launch",
                                    "description": "Final review and deployment",
                                    "actions": ["Review all assets", "Launch campaigns"],
                                    "time_estimate": "2-3 hours"
                                }
                            ],
                            "recommended_ad_sets": [
                                {
                                    "name": f"{campaign_objective} - Primary",
                                    "audience_type": "interest",
                                    "description": "Primary target audience",
                                    "budget_percentage": 60,
                                    "platforms": channels
                                },
                                {
                                    "name": f"{campaign_objective} - Retargeting",
                                    "audience_type": "retargeting",
                                    "description": "Retargeting audience",
                                    "budget_percentage": 40,
                                    "platforms": channels
                                }
                            ],
                            "priority_metrics": ["CPA", "ROAS", "CTR"],
                            "ad_copy": {},
                            "budget_allocation": {channel: budget_per_channel for channel in channels} if channels else {},
                            "objective": campaign_objective,
                            "target_audience": target_audience_text,
                            "budget": budget,
                            "duration_days": duration_days,
                            "channels": channels,
                            "product_brief": product_brief,
                            "creative_preference": creative_preference,
                            "raw_output": generated_output  # Store raw output for debugging
                        }
                    
                    tasks.append({"task": "Campaign Plan Generation", "status": "PASSED"})
                    logger.info("[TASK 3/5] ✓ PASSED - Campaign plan generated")
                    
                except Exception as e:
                    logger.error(f"[TASK 3/5] ✗ FAILED - Campaign plan generation failed: {str(e)}")
                    tasks.append({"task": "Campaign Plan Generation", "status": "FAILED", "error": str(e)})
                    raise
                
                # Step 5: Create campaign draft in database
                logger.info("[TASK 4/5] Creating campaign draft...")
                try:
                    # Calculate dates
                    if start_date_str:
                        try:
                            start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00')).date()
                        except Exception:
                            start_date = datetime.now().date()
                    else:
                        start_date = datetime.now().date()
                    
                    if end_date_str:
                        try:
                            end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00')).date()
                        except Exception:
                            end_date = start_date + timedelta(days=duration_days)
                    else:
                        end_date = start_date + timedelta(days=duration_days)
                    
                    # Budget allocation - use from plan if available, otherwise equal split
                    if campaign_plan.get("budget_allocation"):
                        # Convert percentages to actual dollar amounts
                        plan_allocation = campaign_plan.get("budget_allocation", {})
                        budget_allocation = {}
                        for channel in channels:
                            percentage = plan_allocation.get(channel, 100 / len(channels))
                            budget_allocation[channel] = (budget * percentage / 100) if budget > 0 else 0
                    else:
                        # Equal split fallback
                        budget_per_channel = budget / len(channels) if channels else budget
                        budget_allocation = {channel: budget_per_channel for channel in channels}
                    
                    # Create campaign record
                    campaign = Campaign(
                        id=uuid.uuid4(),
                        tenant_id=UUID(tenant_id),
                        execution_id=UUID(execution_id),
                        name=campaign_name,
                        description=description,
                        campaign_type=request_data.get("campaign_type", "brand_awareness"),
                        start_date=start_date,
                        end_date=end_date,
                        channels=channels,
                        total_budget=Decimal(str(budget)),
                        budget_allocation=budget_allocation,
                        status="draft",  # Draft status - waiting for user approval
                        plan=campaign_plan,
                        metrics={}
                    )
                    
                    db.add(campaign)
                    db.commit()
                    db.refresh(campaign)
                    
                    tasks.append({"task": "Campaign Draft Creation", "status": "PASSED"})
                    logger.info(f"[TASK 4/5] ✓ PASSED - Campaign draft created: {campaign.id}")
                    
                except Exception as e:
                    logger.error(f"[TASK 4/5] ✗ FAILED - Campaign draft creation failed: {str(e)}")
                    tasks.append({"task": "Campaign Draft Creation", "status": "FAILED", "error": str(e)})
                    db.rollback()
                    raise
                
                # Step 6: Update execution with result (sync)
                logger.info("[TASK 5/5] Finalizing execution...")
                try:
                    result = db.execute(
                        select(AgentExecution).where(AgentExecution.id == UUID(execution_id))
                    )
                    execution = result.scalar_one_or_none()
                    if execution:
                        execution.status = "completed"
                        execution.completed_at = datetime.now(timezone.utc)
                        if execution.started_at:
                            delta = execution.completed_at - execution.started_at
                            execution.execution_time_ms = int(delta.total_seconds() * 1000)
                        execution.result = {
                            "campaign_id": str(campaign.id),
                            "campaign_name": campaign.name,
                            "status": campaign.status,
                            "plan": campaign_plan,
                            "tasks": tasks
                        }
                        execution.steps_executed = tasks
                        db.commit()
                        db.refresh(execution)
                    
                    tasks.append({"task": "Execution Finalization", "status": "PASSED"})
                    logger.info("[TASK 5/5] ✓ PASSED - Execution finalized")
                    
                except Exception as e:
                    logger.error(f"[TASK 5/5] ✗ FAILED - Execution finalization failed: {str(e)}")
                    tasks.append({"task": "Execution Finalization", "status": "FAILED", "error": str(e)})
                
                # Summary
                passed_tasks = sum(1 for t in tasks if t.get("status") == "PASSED")
                failed_tasks = sum(1 for t in tasks if t.get("status") == "FAILED")
                
                logger.info("=" * 80)
                logger.info("CAMPAIGN CREATION EXECUTION COMPLETED")
                logger.info(f"Tasks Passed: {passed_tasks}/{len(tasks)}")
                logger.info(f"Tasks Failed: {failed_tasks}/{len(tasks)}")
                logger.info(f"Campaign ID: {campaign.id}")
                logger.info(f"Campaign Status: {campaign.status}")
                logger.info("=" * 80)
                
                return {
                    "success": True,
                    "campaign_id": str(campaign.id),
                    "status": campaign.status,
                    "tasks": tasks
                }
                
            finally:
                db.close()
        
        result = _execute()
        return result
        
    except Exception as e:
        logger.error(f"Campaign creation execution failed: {str(e)}", exc_info=True)
        
        # Update execution status to failed (sync)
        try:
            from app.db.session import create_worker_session_factory
            from app.models.agent_execution import AgentExecution
            from sqlalchemy import select
            
            SessionFactory = create_worker_session_factory()
            db = SessionFactory()
            try:
                result = db.execute(
                    select(AgentExecution).where(AgentExecution.id == UUID(execution_id))
                )
                execution = result.scalar_one_or_none()
                if execution:
                    execution.status = "failed"
                    execution.error_message = str(e)
                    execution.completed_at = datetime.now(timezone.utc)
                    if execution.started_at:
                        delta = execution.completed_at - execution.started_at
                        execution.execution_time_ms = int(delta.total_seconds() * 1000)
                    db.commit()
            finally:
                db.close()
        except Exception as update_error:
            logger.error(f"Failed to update execution status: {str(update_error)}")
        
        raise self.retry(exc=e, countdown=120)


@celery_app.task(name="campaign.execute_step", bind=True, max_retries=2)
def execute_campaign_step(
    self,
    campaign_id: str,
    step_id: str,
    tenant_id: str,
    task_type: str,
    step_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Execute a single campaign plan step based on its task type.
    
    Task types:
    - text_generation: Strategy, copy, planning content via Gemini
    - search_thinking: Research, analysis via RAG + SERP
    - image_generation: Visual assets via Gemini image model
    - video_generation: Video assets via Veo
    
    Args:
        campaign_id: Campaign UUID string
        step_id: Step ID within the campaign plan
        tenant_id: Tenant UUID string
        task_type: One of text_generation, search_thinking, image_generation, video_generation
        step_data: Step data including title, description, actions, campaign context
    
    Returns:
        Execution result with generated content/media
    """
    try:
        logger.info(f"=== STEP EXECUTION STARTED ===")
        logger.info(f"Campaign: {campaign_id}, Step: {step_id}, Type: {task_type}")
        
        def _execute_step():
            from app.db.session import create_worker_session_factory
            from app.models.campaign import Campaign
            from app.services.llm.factory import create_llm_service
            from sqlalchemy import select
            from datetime import datetime, timezone
            import uuid as uuid_lib
            
            SessionFactory = create_worker_session_factory()
            db = SessionFactory()
            
            try:
                # Get campaign
                result = db.execute(
                    select(Campaign).where(Campaign.id == UUID(campaign_id))
                )
                campaign = result.scalar_one_or_none()
                
                if not campaign:
                    raise Exception(f"Campaign {campaign_id} not found")
                
                step_title = step_data.get("title", "")
                step_description = step_data.get("description", "")
                step_actions = step_data.get("actions", [])
                campaign_name = step_data.get("campaign_name", campaign.name)
                product_brief = step_data.get("product_brief", campaign.product_brief or "")
                target_audience = step_data.get("target_audience", campaign.target_audience or {})
                creative_preference = step_data.get("creative_preference", campaign.creative_preference or "both")
                
                step_result = {
                    "content": None,
                    "image_urls": [],
                    "video_urls": [],
                    "research_data": None,
                    "executed_at": datetime.now(timezone.utc).isoformat(),
                    "error": None
                }
                
                try:
                    if task_type == "text_generation":
                        # Use Gemini for text generation
                        step_result = _execute_text_generation(
                            step_title, step_description, step_actions,
                            campaign_name, product_brief, target_audience
                        )
                    
                    elif task_type == "search_thinking":
                        # Use RAG + SERP for research
                        step_result = _execute_search_thinking(
                            step_title, step_description, step_actions,
                            campaign_name, product_brief, tenant_id, db
                        )
                    
                    elif task_type == "image_generation":
                        # Use Gemini image model
                        step_result = _execute_image_generation(
                            step_title, step_description,
                            campaign_name, product_brief, tenant_id, campaign_id
                        )
                    
                    elif task_type == "video_generation":
                        # Use Veo for video
                        step_result = _execute_video_generation(
                            step_title, step_description,
                            campaign_name, product_brief, tenant_id, campaign_id
                        )
                    
                    else:
                        step_result["error"] = f"Unknown task type: {task_type}"
                    
                    # Mark step as completed
                    step_status = "completed" if not step_result.get("error") else "failed"
                    
                except Exception as e:
                    logger.error(f"Step execution failed: {str(e)}", exc_info=True)
                    step_result["error"] = str(e)
                    step_status = "failed"
                
                # Update campaign plan with result
                # Use deepcopy to ensure SQLAlchemy detects the change
                import copy
                from sqlalchemy.orm.attributes import flag_modified
                
                plan = copy.deepcopy(campaign.plan)
                for i, step in enumerate(plan.get("steps", [])):
                    if step.get("id") == step_id:
                        plan["steps"][i]["status"] = step_status
                        plan["steps"][i]["result"] = step_result
                        logger.info(f"Updated step {step_id} with status={step_status}")
                        break
                
                campaign.plan = plan
                flag_modified(campaign, "plan")  # Force SQLAlchemy to detect the change
                db.commit()
                logger.info(f"Saved step result to database for step {step_id}")
                
                logger.info(f"=== STEP EXECUTION {step_status.upper()} ===")
                
                return {
                    "success": step_status == "completed",
                    "campaign_id": campaign_id,
                    "step_id": step_id,
                    "task_type": task_type,
                    "status": step_status,
                    "result": step_result
                }
                
            finally:
                db.close()
        
        result = _execute_step()
        return result
        
    except Exception as e:
        logger.error(f"Step execution task failed: {str(e)}", exc_info=True)
        
        # Update step status to failed
        try:
            from app.db.session import create_worker_session_factory
            from app.models.campaign import Campaign
            from sqlalchemy import select
            from datetime import datetime, timezone
            
            SessionFactory = create_worker_session_factory()
            db = SessionFactory()
            try:
                result = db.execute(
                    select(Campaign).where(Campaign.id == UUID(campaign_id))
                )
                campaign = result.scalar_one_or_none()
                if campaign and campaign.plan:
                    plan = campaign.plan
                    for i, step in enumerate(plan.get("steps", [])):
                        if step.get("id") == step_id:
                            plan["steps"][i]["status"] = "failed"
                            plan["steps"][i]["result"] = {
                                "error": str(e),
                                "executed_at": datetime.now(timezone.utc).isoformat()
                            }
                            break
                    campaign.plan = plan
                    db.commit()
            finally:
                db.close()
        except Exception as update_error:
            logger.error(f"Failed to update step status: {str(update_error)}")
        
        raise self.retry(exc=e, countdown=60)


def _execute_text_generation(
    step_title: str,
    step_description: str,
    step_actions: list,
    campaign_name: str,
    product_brief: str,
    target_audience: dict
) -> Dict[str, Any]:
    """Execute text generation using Gemini"""
    from app.services.llm.factory import create_llm_service
    from datetime import datetime, timezone
    
    logger.info(f"Executing text generation for: {step_title}")
    
    # Build prompt
    actions_text = "\n".join(f"- {action}" for action in step_actions) if step_actions else ""
    
    prompt = f"""You are a marketing strategist working on the campaign "{campaign_name}".

Step: {step_title}
Description: {step_description}

Actions to complete:
{actions_text}

Product/Service: {product_brief if product_brief else 'Not specified'}
Target Audience: {target_audience if target_audience else 'General audience'}

Please provide detailed, actionable output for this step. Be specific and practical.
Include recommendations, best practices, and concrete examples where applicable.
"""
    
    system_instruction = """You are an expert digital marketing strategist. 
Provide detailed, practical, and actionable marketing recommendations.
Format your response with clear sections and bullet points for easy reading."""
    
    # Call LLM
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    llm_service = create_llm_service()
    content = loop.run_until_complete(
        llm_service.generate_content(
            prompt=prompt,
            system_instruction=system_instruction,
            temperature=0.7
        )
    )
    
    return {
        "content": content,
        "image_urls": [],
        "video_urls": [],
        "research_data": None,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "error": None
    }


def _execute_search_thinking(
    step_title: str,
    step_description: str,
    step_actions: list,
    campaign_name: str,
    product_brief: str,
    tenant_id: str,
    db
) -> Dict[str, Any]:
    """Execute research using Gemini Search Grounding + RAG (fully synchronous)"""
    from datetime import datetime, timezone
    
    logger.info(f"Executing search/thinking for: {step_title}")
    
    research_results = {
        "rag_context": [],
        "web_search_results": "",
        "grounding_sources": [],
        "insights": []
    }
    
    # RAG retrieval from knowledge base (synchronous)
    try:
        from app.services.rag_service import RAGService
        rag_service = RAGService(db, UUID(tenant_id))
        query = f"{step_title} {step_description} {product_brief}"
        # The RAGService retrieve_relevant_context should be sync
        context_chunks = rag_service.retrieve_relevant_context_sync(query, limit=5) if hasattr(rag_service, 'retrieve_relevant_context_sync') else []
        if not context_chunks:
            # Fallback to regular method if sync version doesn't exist
            try:
                context_chunks = rag_service.retrieve_relevant_context(query, limit=5)
            except Exception:
                context_chunks = []
        research_results["rag_context"] = context_chunks
        logger.info(f"Retrieved {len(context_chunks)} RAG chunks")
    except Exception as e:
        logger.warning(f"RAG retrieval failed: {e}")
    
    # Gemini Search Grounding - synchronous call
    try:
        from google import genai
        from google.genai import types
        
        from app.config import settings
        
        api_key = settings.GOOGLE_API_KEY
        if not api_key:
            raise ValueError("No Gemini API key found in settings.GOOGLE_API_KEY")
        
        client = genai.Client(api_key=api_key)
        
        # Build the search prompt
        search_prompt = f"""You are a marketing research analyst. Research the following topic using web search:

Campaign: {campaign_name}
Research Topic: {step_title}
Description: {step_description}
Product/Service: {product_brief if product_brief else 'Not specified'}

Please search and provide:
1. Current market trends and insights
2. Competitor analysis if relevant
3. Best practices and strategies
4. Statistics and data points
5. Actionable recommendations

Be specific and cite your sources."""

        # Synchronous Gemini call with google_search tool
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=search_prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.4
            )
        )
        
        # Extract the content
        search_content = ""
        if hasattr(response, 'text') and response.text:
            search_content = response.text
        elif hasattr(response, 'parts') and response.parts:
            search_content = " ".join([p.text for p in response.parts if hasattr(p, 'text')])
        
        # Extract grounding metadata/citations if available
        if hasattr(response, 'candidates') and response.candidates:
            for candidate in response.candidates:
                if hasattr(candidate, 'grounding_metadata') and candidate.grounding_metadata:
                    metadata = candidate.grounding_metadata
                    if hasattr(metadata, 'grounding_chunks') and metadata.grounding_chunks:
                        for chunk in metadata.grounding_chunks:
                            if hasattr(chunk, 'web') and chunk.web:
                                research_results["grounding_sources"].append({
                                    "title": getattr(chunk.web, 'title', ''),
                                    "uri": getattr(chunk.web, 'uri', '')
                                })
        
        research_results["web_search_results"] = search_content
        logger.info(f"Gemini search completed with {len(research_results['grounding_sources'])} sources")
        
    except Exception as e:
        logger.warning(f"Gemini search grounding failed: {e}")
        research_results["web_search_results"] = f"Search failed: {str(e)}"
    
    # Combine RAG context with web search for final insights
    context_text = "\n".join([str(c) for c in research_results["rag_context"][:3]]) if research_results["rag_context"] else ""
    
    # Build final summary combining all research - synchronous call
    summary_prompt = f"""Based on the following research, provide a comprehensive analysis for "{step_title}":

WEB SEARCH FINDINGS:
{research_results.get("web_search_results", "No web results")}

INTERNAL KNOWLEDGE BASE:
{context_text if context_text else "No internal context available"}

Campaign: {campaign_name}
Product: {product_brief}

Synthesize all findings into 5-7 key actionable insights. Include specific recommendations and any relevant statistics or trends discovered."""

    try:
        from google import genai
        from app.config import settings
        
        api_key = settings.GOOGLE_API_KEY
        client = genai.Client(api_key=api_key)
        
        # Synchronous content generation
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=summary_prompt
        )
        
        insights_content = ""
        if hasattr(response, 'text') and response.text:
            insights_content = response.text
        elif hasattr(response, 'parts') and response.parts:
            insights_content = " ".join([p.text for p in response.parts if hasattr(p, 'text')])
            
    except Exception as e:
        logger.error(f"Failed to generate insights: {e}")
        insights_content = f"Analysis generation failed: {str(e)}"
    
    return {
        "content": insights_content,
        "image_urls": [],
        "video_urls": [],
        "research_data": research_results,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "error": None
    }


def _execute_image_generation(
    step_title: str,
    step_description: str,
    campaign_name: str,
    product_brief: str,
    tenant_id: str,
    campaign_id: str
) -> Dict[str, Any]:
    """Execute image generation using Gemini"""
    from app.services.llm.factory import create_llm_service
    from app.services.storage import get_storage
    from io import BytesIO
    from datetime import datetime, timezone
    import uuid as uuid_lib
    
    logger.info(f"Executing image generation for: {step_title}")
    
    # Build image prompt
    image_prompt = f"""Create a professional marketing image for the campaign "{campaign_name}".

Context: {step_description}
Product/Service: {product_brief if product_brief else 'General marketing'}

Create a visually appealing, high-quality marketing image that:
- Looks professional and polished
- Conveys the brand message clearly
- Is suitable for digital advertising
- Has clean, modern design aesthetics
"""
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    llm_service = create_llm_service()
    
    # Generate image
    images = loop.run_until_complete(
        llm_service.generate_image(
            prompt=image_prompt,
            aspect_ratio="1:1",
            number_of_images=1
        )
    )
    
    # Upload to storage
    image_urls = []
    if images:
        storage = get_storage()
        for i, image_data in enumerate(images):
            try:
                img_bytes = BytesIO()
                if isinstance(image_data, bytes):
                    img_bytes.write(image_data)
                elif hasattr(image_data, 'save'):
                    image_data.save(img_bytes, format="PNG")
                else:
                    img_bytes.write(bytes(image_data))
                
                img_bytes.seek(0)
                storage_key = f"tenants/{tenant_id}/campaigns/{campaign_id}/images/{uuid_lib.uuid4()}.png"
                
                url = loop.run_until_complete(
                    storage.upload(
                        key=storage_key,
                        file=img_bytes,
                        content_type="image/png"
                    )
                )
                image_urls.append(url)
                logger.info(f"Uploaded image to: {url}")
            except Exception as e:
                logger.error(f"Failed to upload image: {e}")
    
    return {
        "content": f"Generated {len(image_urls)} image(s) for {step_title}",
        "image_urls": image_urls,
        "video_urls": [],
        "research_data": None,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "error": None if image_urls else "No images generated"
    }


def _execute_video_generation(
    step_title: str,
    step_description: str,
    campaign_name: str,
    product_brief: str,
    tenant_id: str,
    campaign_id: str
) -> Dict[str, Any]:
    """Execute video generation using Veo"""
    from app.services.llm.factory import create_llm_service
    from app.services.storage import get_storage
    from io import BytesIO
    from datetime import datetime, timezone
    import uuid as uuid_lib
    
    logger.info(f"Executing video generation for: {step_title}")
    
    # Build video prompt
    video_prompt = f"""Create a short, cinematic marketing video for the campaign "{campaign_name}".

Context: {step_description}
Product/Service: {product_brief if product_brief else 'General marketing'}

Create a compelling video ad that:
- Opens with a strong hook
- Builds intrigue and engagement
- Has professional production quality
- Conveys the brand message effectively
- Ends with a clear call to action
"""
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    llm_service = create_llm_service()
    
    # Generate video (this can take several minutes)
    logger.info("Starting video generation - this may take 2-10 minutes...")
    video_data = loop.run_until_complete(
        llm_service.generate_video(
            prompt=video_prompt,
            duration_seconds=8,
            aspect_ratio="16:9"
        )
    )
    
    # Upload to storage
    video_urls = []
    if video_data:
        storage = get_storage()
        try:
            video_bytes = BytesIO()
            if isinstance(video_data, bytes):
                video_bytes.write(video_data)
            else:
                video_bytes.write(bytes(video_data))
            
            video_bytes.seek(0)
            storage_key = f"tenants/{tenant_id}/campaigns/{campaign_id}/videos/{uuid_lib.uuid4()}.mp4"
            
            url = loop.run_until_complete(
                storage.upload(
                    key=storage_key,
                    file=video_bytes,
                    content_type="video/mp4"
                )
            )
            video_urls.append(url)
            logger.info(f"Uploaded video to: {url}")
        except Exception as e:
            logger.error(f"Failed to upload video: {e}")
    
    return {
        "content": f"Generated {len(video_urls)} video(s) for {step_title}",
        "image_urls": [],
        "video_urls": video_urls,
        "research_data": None,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "error": None if video_urls else "No video generated"
    }
