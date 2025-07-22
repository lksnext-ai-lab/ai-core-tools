#!/usr/bin/env python3
"""
Test script to verify Mistral AI agent creation with tools
"""

import asyncio
import os
import sys

# Add the app directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from dotenv import load_dotenv
from extensions import db
from model.agent import Agent
from model.ai_service import AIService, ProviderEnum
from tools.agentTools import create_agent
from langchain_core.messages import HumanMessage

load_dotenv()

async def test_mistral_agent():
    """Test creating a Mistral AI agent with tools"""
    
    # Create a mock AI service for Mistral
    ai_service = AIService(
        service_id=1,
        name="mistral-medium-2505",
        provider=ProviderEnum.MistralAI.value,
        api_key=os.getenv("MISTRAL_API_KEY"),
        endpoint=None,
        api_version=None
    )
    
    # Create a mock agent
    agent = Agent(
        agent_id=1,
        name="Test Mistral Agent",
        description="A test agent for Mistral AI",
        system_prompt="You are a helpful assistant that can use tools to answer questions.",
        prompt_template="Question: {question}\n\nPlease answer the question using available tools if needed.",
        type="agent",
        status="active",
        has_memory=False,
        output_parser_id=None,
        ai_service=ai_service,
        silo_id=None,
        app_id=1
    )
    
    try:
        print("Creating Mistral AI agent...")
        agent_chain = await create_agent(agent)
        print("✅ Agent created successfully!")
        
        # Test the agent with a simple question
        print("\nTesting agent with a simple question...")
        result = await agent_chain.ainvoke({
            "messages": [HumanMessage(content="Hello, how are you?")]
        })
        
        print("✅ Agent response received!")
        print(f"Response: {result}")
        
    except Exception as e:
        print(f"❌ Error creating or testing agent: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_mistral_agent()) 