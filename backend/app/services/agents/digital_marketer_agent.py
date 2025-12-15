"""
Digital Marketer Agent using LangChain
"""
from typing import Dict, List, Optional, Any, AsyncGenerator
try:
    from langchain.agents import AgentExecutor, create_openai_tools_agent
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
except ImportError:
    # Fallback for different LangChain versions
    from langchain.agents import AgentExecutor
    from langchain.agents.openai_tools import create_openai_tools_agent
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import SystemMessage, HumanMessage
from app.services.agents.langchain_adapter import LangChainLLMAdapter
from app.services.agents.tools import CONTENT_CREATION_TOOLS
from app.utils.logger import logger


class DigitalMarketerAgent:
    """
    Digital Marketer AI Agent using LangChain for orchestration
    """
    
    def __init__(
        self,
        tenant_config: Dict,
        llm_provider: Optional[str] = None,
        temperature: float = 0.7
    ):
        """
        Initialize the Digital Marketer agent
        
        Args:
            tenant_config: Tenant configuration with brand voice, audience, etc.
            llm_provider: LLM provider to use (defaults to config)
            temperature: LLM temperature
        """
        self.tenant_config = tenant_config
        self.llm_provider = llm_provider
        self.temperature = temperature
        
        # Create LangChain-compatible LLM
        self.llm = LangChainLLMAdapter(
            provider=llm_provider,
            temperature=temperature
        )
        
        # Build system prompt
        self.system_prompt = self._build_system_prompt()
        
        # Create agent
        self.agent_executor = self._create_agent()
    
    def _build_system_prompt(self) -> str:
        """Build system prompt from tenant config"""
        brand_voice = self.tenant_config.get("brand_voice", "professional")
        target_audience = self.tenant_config.get("target_audience", "general")
        offerings = self.tenant_config.get("offerings", "")
        
        return f"""You are a Digital Marketing Assistant. Your job is to:
1. Research keywords and trending topics using available tools
2. Create engaging, platform-appropriate social media content
3. Optimize content for engagement and reach

Brand Guidelines:
- Voice & Tone: {brand_voice}
- Target Audience: {target_audience}
- Products/Services: {offerings}

IMPORTANT: When creating content, generate ONE single, final post that is ready to publish immediately. Do NOT provide multiple options, variations, or alternatives. Do NOT include labels like "Option 1", "Option 2", "Headline:", "Body:", "Call to Action:" - just write the complete post content as it should appear when published. Maintain the brand voice, target the specified audience, and make it ready to publish. Do not explain your process - just execute the task and return the final, ready-to-post content."""
    
    def _create_agent(self) -> AgentExecutor:
        """Create LangChain agent with tools"""
        # Create prompt template
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        
        # Create agent
        agent = create_openai_tools_agent(
            llm=self.llm,
            tools=CONTENT_CREATION_TOOLS,
            prompt=prompt
        )
        
        # Create executor
        executor = AgentExecutor(
            agent=agent,
            tools=CONTENT_CREATION_TOOLS,
            verbose=True,
            return_intermediate_steps=True,
            max_iterations=15,
            max_execution_time=300,  # 5 minutes max
        )
        
        return executor
    
    async def execute(
        self,
        request: str,
        chat_history: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        Execute an agent task
        
        Args:
            request: User request/instruction
            chat_history: Previous conversation history
        
        Returns:
            Dictionary with result, steps, and metadata
        """
        try:
            # Format chat history for LangChain
            messages = []
            if chat_history:
                for msg in chat_history:
                    if msg.get("role") == "user":
                        messages.append(HumanMessage(content=msg.get("content", "")))
                    elif msg.get("role") == "assistant":
                        messages.append(HumanMessage(content=msg.get("content", "")))
            
            # Execute agent
            result = await self.agent_executor.ainvoke({
                "input": request,
                "chat_history": messages
            })
            
            # Extract information
            output = result.get("output", "")
            intermediate_steps = result.get("intermediate_steps", [])
            
            # Parse tool calls
            tools_used = []
            steps_executed = []
            
            for step in intermediate_steps:
                action = step[0]
                observation = step[1]
                
                tool_name = action.tool if hasattr(action, 'tool') else "unknown"
                tool_input = action.tool_input if hasattr(action, 'tool_input') else {}
                
                tools_used.append(tool_name)
                steps_executed.append({
                    "tool": tool_name,
                    "input": tool_input,
                    "output": str(observation)[:500]  # Truncate long outputs
                })
            
            return {
                "result": output,
                "tools_used": tools_used,
                "steps_executed": steps_executed,
                "success": True
            }
            
        except Exception as e:
            logger.error(f"Agent execution failed: {str(e)}")
            return {
                "result": None,
                "error": str(e),
                "success": False
            }
    
    def execute_sync(
        self,
        request: str,
        chat_history: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        Execute an agent task synchronously (for Celery workers)
        
        Args:
            request: User request/instruction
            chat_history: Previous conversation history
        
        Returns:
            Dictionary with result, steps, and metadata
        """
        try:
            # Format chat history for LangChain
            messages = []
            if chat_history:
                for msg in chat_history:
                    if msg.get("role") == "user":
                        messages.append(HumanMessage(content=msg.get("content", "")))
                    elif msg.get("role") == "assistant":
                        messages.append(HumanMessage(content=msg.get("content", "")))
            
            # Execute agent synchronously
            result = self.agent_executor.invoke({
                "input": request,
                "chat_history": messages
            })
            
            # Extract information
            output = result.get("output", "")
            intermediate_steps = result.get("intermediate_steps", [])
            
            # Parse tool calls
            tools_used = []
            steps_executed = []
            
            for step in intermediate_steps:
                action = step[0]
                observation = step[1]
                
                tool_name = action.tool if hasattr(action, 'tool') else "unknown"
                tool_input = action.tool_input if hasattr(action, 'tool_input') else {}
                
                tools_used.append(tool_name)
                steps_executed.append({
                    "tool": tool_name,
                    "input": tool_input,
                    "output": str(observation)[:500]  # Truncate long outputs
                })
            
            return {
                "result": output,
                "tools_used": tools_used,
                "steps_executed": steps_executed,
                "success": True
            }
            
        except Exception as e:
            logger.error(f"Agent execution failed: {str(e)}")
            return {
                "result": None,
                "error": str(e),
                "success": False
            }
    
    async def stream_execute(
        self,
        request: str,
        chat_history: Optional[List[Dict]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream agent execution for real-time updates
        
        Args:
            request: User request
            chat_history: Previous conversation
        
        Yields:
            Dictionary updates with execution status
        """
        try:
            messages = []
            if chat_history:
                for msg in chat_history:
                    if msg.get("role") == "user":
                        messages.append(HumanMessage(content=msg.get("content", "")))
                    elif msg.get("role") == "assistant":
                        messages.append(HumanMessage(content=msg.get("content", "")))
            
            # Stream execution
            async for chunk in self.agent_executor.astream({
                "input": request,
                "chat_history": messages
            }):
                yield {
                    "type": "chunk",
                    "data": chunk
                }
            
            yield {
                "type": "complete"
            }
            
        except Exception as e:
            logger.error(f"Stream execution failed: {str(e)}")
            yield {
                "type": "error",
                "error": str(e)
            }

