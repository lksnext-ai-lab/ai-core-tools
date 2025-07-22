#!/usr/bin/env python3
"""
Azure AI Chat Completions Model Invocation Script

This script demonstrates how to use the Azure AI Chat Completions Model
for text generation and conversation.

Requirements:
- langchain-azure-ai
- python-dotenv
- langchain-core

Environment variables needed:
- AZURE_OPENAI_API_KEY: Your Azure OpenAI API key
- AZURE_OPENAI_ENDPOINT: Your Azure OpenAI endpoint URL
- AZURE_OPENAI_API_VERSION: API version (e.g., "2024-02-15-preview")
"""

import os
import logging
from dotenv import load_dotenv
from langchain_azure_ai.chat_models import AzureAIChatCompletionsModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_azure_model(
    model_name="Llama-4-Scout-17B",
    temperature=0,
    api_key="F7C5kZZuTC6CYNdmuK7kymk1BngxlWLe3I9OZymV2arTr8bbgCSAJQQJ99ALAC5RqLJXJ3w3AAAAACOGgbRj",
    endpoint="https://aula-deusto-openai-services.services.ai.azure.com/models",
    api_version="2024-05-01-preview"
):
    """
    Create an Azure AI Chat Completions Model instance
    
    Args:
        model_name (str): The name of the model to use
        temperature (float): Controls randomness in the response (0-1)
        api_key (str): Azure OpenAI API key
        endpoint (str): Azure OpenAI endpoint URL
        api_version (str): API version
    
    Returns:
        AzureAIChatCompletionsModel: Configured model instance
    """
    # Use environment variables if not provided
    api_key = api_key or os.getenv('AZURE_OPENAI_API_KEY')
    endpoint = endpoint or os.getenv('AZURE_OPENAI_ENDPOINT')
    api_version = api_version or os.getenv('AZURE_OPENAI_API_VERSION', '2024-02-15-preview')
    
    if not api_key:
        raise ValueError("Azure OpenAI API key is required. Set AZURE_OPENAI_API_KEY environment variable.")
    if not endpoint:
        raise ValueError("Azure OpenAI endpoint is required. Set AZURE_OPENAI_ENDPOINT environment variable.")
    
    try:
        model = AzureAIChatCompletionsModel(
            model=model_name,
            temperature=temperature,
            credential=api_key,
            endpoint=endpoint,
            api_version=api_version
        )
        logger.info(f"Successfully created Azure AI model: {model_name}")
        return model
    except Exception as e:
        logger.error(f"Error creating Azure AI model: {str(e)}")
        raise

def simple_chat(model, message, system_prompt="You are a helpful AI assistant."):
    """
    Simple chat function using the Azure AI model
    
    Args:
        model: Azure AI model instance
        message (str): User message
        system_prompt (str): System prompt to guide the model
    
    Returns:
        str: Model response
    """
    try:
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{input}")
        ])
        
        chain = prompt | model | StrOutputParser()
        response = chain.invoke({"input": message})
        
        logger.info(f"Response received successfully")
        return response
    except Exception as e:
        logger.error(f"Error in chat: {str(e)}")
        raise

def structured_chat(model, message, output_format="text"):
    """
    Structured chat with specific output format instructions
    
    Args:
        model: Azure AI model instance
        message (str): User message
        output_format (str): Desired output format
    
    Returns:
        str: Model response
    """
    try:
        format_instructions = f"Please respond in {output_format} format."
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a helpful AI assistant that provides structured responses."),
            ("system", f"<output_format_instructions>{format_instructions}</output_format_instructions>"),
            ("human", "{input}")
        ])
        
        chain = prompt | model | StrOutputParser()
        response = chain.invoke({"input": message})
        
        logger.info(f"Structured response received successfully")
        return response
    except Exception as e:
        logger.error(f"Error in structured chat: {str(e)}")
        raise

def main():
    """Main function to demonstrate Azure AI usage"""
    print("Azure AI Chat Completions Model Demo")
    print("=" * 50)
    
    try:
        # Create the Azure AI model
        print("Creating Azure AI model...")
        model = create_azure_model()
        
        # Example 1: Simple chat
        print("\n1. Simple Chat Example:")
        print("-" * 30)
        user_message = "Hello! Can you tell me about artificial intelligence?"
        response = simple_chat(model, user_message)
        print(f"User: {user_message}")
        print(f"AI: {response}")
        
        # Example 2: Structured response
        print("\n2. Structured Response Example:")
        print("-" * 30)
        structured_message = "List three benefits of machine learning in bullet points"
        structured_response = structured_chat(model, structured_message, "bullet points")
        print(f"User: {structured_message}")
        print(f"AI: {structured_response}")
        
        # Example 3: Interactive chat
        print("\n3. Interactive Chat (type 'quit' to exit):")
        print("-" * 30)
        while True:
            user_input = input("\nYou: ")
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("Goodbye!")
                break
            
            try:
                response = simple_chat(model, user_input)
                print(f"AI: {response}")
            except Exception as e:
                print(f"Error: {str(e)}")
    
    except Exception as e:
        logger.error(f"Main execution error: {str(e)}")
        print(f"Error: {str(e)}")
        print("\nPlease check your environment variables:")
        print("- AZURE_OPENAI_API_KEY")
        print("- AZURE_OPENAI_ENDPOINT")
        print("- AZURE_OPENAI_API_VERSION (optional, defaults to 2024-02-15-preview)")

if __name__ == "__main__":
    main() 