# Azure AI Chat Completions Model Script

This script demonstrates how to use the Azure AI Chat Completions Model for text generation and conversation using LangChain.

## Features

- Simple chat functionality
- Structured responses with format instructions
- Interactive chat mode
- Error handling and logging
- Environment variable configuration

## Prerequisites

1. **Azure OpenAI Service**: You need an Azure OpenAI service deployed in your Azure subscription
2. **API Key**: Your Azure OpenAI API key
3. **Endpoint URL**: Your Azure OpenAI endpoint URL
4. **Model Deployment**: A deployed model (e.g., gpt-35-turbo, gpt-4)

## Installation

1. **Install dependencies**:
   ```bash
   pip install -r azure_ai_requirements.txt
   ```

2. **Set up environment variables**:
   ```bash
   cp azure_ai_env.example .env
   ```
   
   Edit the `.env` file with your actual Azure OpenAI credentials:
   ```env
   AZURE_OPENAI_API_KEY=your_actual_api_key_here
   AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
   AZURE_OPENAI_API_VERSION=2024-02-15-preview
   ```

## Usage

### Basic Usage

Run the script:
```bash
python azure_ai_script.py
```

The script will:
1. Create an Azure AI model instance
2. Demonstrate simple chat functionality
3. Show structured response examples
4. Start an interactive chat session

### Programmatic Usage

You can also use the functions in your own code:

```python
from azure_ai_script import create_azure_model, simple_chat, structured_chat

# Create the model
model = create_azure_model(
    model_name="gpt-35-turbo",
    temperature=0.7
)

# Simple chat
response = simple_chat(model, "Hello! How are you?")
print(response)

# Structured response
response = structured_chat(model, "List three programming languages", "bullet points")
print(response)
```

### Custom Configuration

You can customize the model creation:

```python
model = create_azure_model(
    model_name="gpt-4",  # Different model
    temperature=0.5,     # Higher creativity
    api_key="your_key",  # Direct API key
    endpoint="your_endpoint",  # Direct endpoint
    api_version="2024-02-15-preview"  # Specific API version
)
```

## Configuration Options

### Model Parameters

- **model_name**: The name of your deployed model (e.g., "gpt-35-turbo", "gpt-4")
- **temperature**: Controls randomness (0 = deterministic, 1 = very random)
- **api_key**: Your Azure OpenAI API key
- **endpoint**: Your Azure OpenAI endpoint URL
- **api_version**: API version (defaults to "2024-02-15-preview")

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `AZURE_OPENAI_API_KEY` | Your Azure OpenAI API key | Yes |
| `AZURE_OPENAI_ENDPOINT` | Your Azure OpenAI endpoint URL | Yes |
| `AZURE_OPENAI_API_VERSION` | API version | No (defaults to 2024-02-15-preview) |

## Error Handling

The script includes comprehensive error handling for:
- Missing environment variables
- Invalid API credentials
- Network connectivity issues
- Model deployment issues

## Examples

### Example 1: Simple Chat
```python
response = simple_chat(model, "What is machine learning?")
```

### Example 2: Structured Response
```python
response = structured_chat(model, "Explain Python in 3 points", "numbered list")
```

### Example 3: Custom System Prompt
```python
response = simple_chat(
    model, 
    "Write a short story", 
    system_prompt="You are a creative writer who specializes in science fiction."
)
```

## Troubleshooting

### Common Issues

1. **"Azure OpenAI API key is required"**
   - Check that `AZURE_OPENAI_API_KEY` is set in your `.env` file
   - Verify the API key is correct

2. **"Azure OpenAI endpoint is required"**
   - Check that `AZURE_OPENAI_ENDPOINT` is set in your `.env` file
   - Ensure the endpoint URL is correct and includes the protocol (https://)

3. **"Model not found"**
   - Verify the model name matches your deployed model
   - Check that the model is deployed in your Azure OpenAI service

4. **Authentication errors**
   - Verify your API key is valid
   - Check that your Azure OpenAI service is active
   - Ensure you have the necessary permissions

### Getting Help

If you encounter issues:
1. Check the logs for detailed error messages
2. Verify your Azure OpenAI service configuration
3. Ensure all environment variables are correctly set
4. Test your API key and endpoint with a simple curl request

## License

This script is provided as-is for educational and development purposes. 