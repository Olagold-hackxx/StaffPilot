"""
Campaign Chat Service - Handles AI conversation with campaign context
"""
from typing import List, Dict, Any, Optional
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from app.services.agents.langchain_adapter import LangChainLLMAdapter
from app.models.campaign import Campaign
from app.utils.logger import logger

import json

class CampaignChatService:
    """
    Service to handle chat interactions specifically for campaigns,
    maintaining context of the current campaign plan and status.
    """
    
    def __init__(self):
        # Initialize the adapter with Gemini (or default provider)
        self.llm = LangChainLLMAdapter(temperature=0.7)
        
    async def chat(
        self, 
        campaign: Campaign, 
        user_message: str, 
        history: List[Dict[str, str]] = None,
        db: Any = None
    ) -> str:
        """
        Process a user message in the context of a campaign
        
        Args:
            campaign: The campaign object containing plan and details
            user_message: The user's question or instruction
            history: Optional conversation history [{"role": "user", "content": "..."}, ...]
            db: Database session for RAG retrieval
            
        Returns:
            AI response string
        """
        try:
            # 1. Retrieve RAG Context if DB is available
            rag_context = ""
            if db:
                try:
                    from app.services.rag_service import RAGService
                    rag_service = RAGService(db, campaign.tenant_id)
                    chunks = rag_service.retrieve_relevant_context(user_message, limit=3)
                    if chunks:
                        rag_context = "\nRELEVANT KNOWLEDGE BASE CONTEXT:\n"
                        for chunk in chunks:
                            rag_context += f"- {chunk['content'][:500]}...\n"
                except Exception as e:
                    logger.warning(f"Chat RAG retrieval failed: {e}")

            # 2. Build System Context
            system_prompt = self._build_system_context(campaign, rag_context)
            
            # 3. Prepare Messages
            messages = [SystemMessage(content=system_prompt)]
            
            # Add history if available
            if history:
                for msg in history:
                    if msg.get("role") == "user":
                        messages.append(HumanMessage(content=msg.get("content", "")))
                    elif msg.get("role") == "assistant":
                        messages.append(AIMessage(content=msg.get("content", "")))
            
            # Add current user message
            messages.append(HumanMessage(content=user_message))
            
            # 4. Generate Response using LangChain Adapter
            response = await self.llm.ainvoke(messages)
            
            return response.content
            
        except Exception as e:
            logger.error(f"Campaign chat failed: {str(e)}")
            return "I apologize, but I'm having trouble processing your request right now. Please try again."

    def _build_system_context(self, campaign: Campaign, rag_context: str = "") -> str:
        """
        Constructs the system prompt with campaign details and RAG context
        """
        # Format basics
        context = f"""You are the AI Creative Director and Campaign Manager for the campaign "{campaign.name}".
Your goal is to assist the user in refining their campaign strategy, creative plan, and execution details.

CAMPAIGN DETAILS:
- Name: {campaign.name}
- Objective: {campaign.objective_type}
- Budget: {campaign.total_budget} {campaign.currency}
- Status: {campaign.status}
- Start Date: {campaign.start_date}
- End Date: {campaign.end_date}
- Key Metrics: {json.dumps(campaign.goal_metrics, default=str) if campaign.goal_metrics else 'Not defined'}
- Product Brief: {campaign.product_brief or 'Not provided'}
- Target Audience: {json.dumps(campaign.target_audience, default=str) if campaign.target_audience else 'Not defined'}

CURRENT PLAN:
"""
        # Format Plan Steps
        if campaign.plan and "steps" in campaign.plan:
            context += "Steps:\n"
            for step in campaign.plan["steps"]:
                status_icon = "[x]" if step.get("status") == "completed" else "[ ]"
                context += f"{status_icon} {step.get('title')}: {step.get('description')}\n"
        else:
            context += "No detailed plan generated yet.\n"
            
        # Add RAG Context
        if rag_context:
            context += f"\n{rag_context}\n"

        context += """
INSTRUCTIONS:
- Be helpful, professional, and creative.
- If the user asks for creative ideas (headlines, ad copy), generate them based on compliance with ad platform policies (Google/Meta).
- Keep responses concise and focused on moving the campaign forward.
- You have access to the campaign plan and knowledge base context above; reference it when answering questions.
- Use Markdown formatting for your responses (e.g., **bold**, *italics*, lists) to make them readable.
"""
        return context
