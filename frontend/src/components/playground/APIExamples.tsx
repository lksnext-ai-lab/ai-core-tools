import React, { useState } from 'react';

interface APIExamplesProps {
  appId: number;
  agentId: number;
  agentName: string;
  agentType?: string;
  hasSilo?: boolean;
  siloName?: string;
}

interface CodeExample {
  id: string;
  title: string;
  language: string;
  code: string;
}

function APIExamples({ appId, agentId, agentName, agentType = 'agent', hasSilo = false, siloName }: APIExamplesProps) {
  const [copied, setCopied] = useState<string | null>(null);
  const [selectedExample, setSelectedExample] = useState('curl');

  const baseUrl = window.location.origin; // Use current domain
  const endpoint = `${baseUrl}/public/v1/app/${appId}/call/${agentId}`;

  // Generate request body based on agent capabilities
  const getRequestBodyExample = () => {
    const baseBody = {
      message: "Your question here",
      conversation_id: "optional-conversation-id"
    };

    if (agentType === 'ocr_agent') {
      return {
        ...baseBody,
        attachments: [
          {
            file_reference: "uploaded-file-reference",
            filename: "document.pdf"
          }
        ]
      };
    }

    if (hasSilo) {
      return {
        ...baseBody,
        search_params: {
          metadata_filter: {
            category: "documents",
            department: "engineering"
          }
        }
      };
    }

    return baseBody;
  };

  const requestBody = getRequestBodyExample();
  const requestBodyJson = JSON.stringify(requestBody, null, 2);

  // Generate capability-specific comments
  const getCapabilityComments = () => {
    const comments = [];
    
    if (agentType === 'ocr_agent') {
      comments.push('# OCR Agent - supports file attachments');
      comments.push('# Upload files first using the attach-file endpoint');
    }
    
    if (hasSilo) {
      comments.push(`# RAG-enabled agent with silo: ${siloName || 'Unknown'}`);
      comments.push('# Supports metadata filtering for enhanced search');
    }
    
    if (!hasSilo && agentType === 'agent') {
      comments.push('# Standard conversational agent');
    }
    
    return comments.join('\n');
  };

  const capabilityComments = getCapabilityComments();

  const examples: CodeExample[] = [
    {
      id: 'curl',
      title: 'cURL',
      language: 'bash',
      code: `${capabilityComments}
curl -X POST "${endpoint}" \\
  -H "X-API-KEY: your-api-key" \\
  -H "Content-Type: application/json" \\
  -d '${requestBodyJson}'

# Reset conversation
curl -X POST "${baseUrl}/public/v1/app/${appId}/reset/${agentId}" \\
  -H "X-API-KEY: your-api-key"`
    },
    {
      id: 'python',
      title: 'Python',
      language: 'python',
      code: `import requests
import json

# Configuration
API_KEY = "your-api-key"
BASE_URL = "${baseUrl}"
APP_ID = ${appId}
AGENT_ID = ${agentId}

def call_agent(message, conversation_id=None${hasSilo ? ', search_params=None' : ''}${agentType === 'ocr_agent' ? ', attachments=None' : ''}):
    """Call ${agentName}${agentType === 'ocr_agent' ? ' (OCR Agent)' : hasSilo ? ' (RAG-enabled)' : ''}"""
    url = f"{BASE_URL}/public/v1/app/{APP_ID}/call/{AGENT_ID}"
    
    headers = {
        "X-API-KEY": API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {"message": message}
    if conversation_id:
        payload["conversation_id"] = conversation_id
${hasSilo ? `    if search_params:
        payload["search_params"] = search_params` : ''}${agentType === 'ocr_agent' ? `    if attachments:
        payload["attachments"] = attachments` : ''}
    
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()

def reset_conversation():
    """Reset conversation for ${agentName}"""
    url = f"{BASE_URL}/public/v1/app/{APP_ID}/reset/{AGENT_ID}"
    headers = {"X-API-KEY": API_KEY}
    
    response = requests.post(url, headers=headers)
    response.raise_for_status()
    return response.json()

# Example usage
try:${hasSilo ? `
    # Example with metadata filtering
    search_params = {
        "metadata_filter": {
            "category": "documents",
            "department": "engineering"
        }
    }
    result = call_agent("Your question here", search_params=search_params)` : agentType === 'ocr_agent' ? `
    # Example with file attachment
    attachments = [
        {
            "file_reference": "uploaded-file-reference",
            "filename": "document.pdf"
        }
    ]
    result = call_agent("Analyze this document", attachments=attachments)` : `
    result = call_agent("Your question here")`}
    print("Agent response:", result["response"])
    print("Conversation ID:", result["conversation_id"])
except requests.exceptions.RequestException as e:
    print(f"Error calling agent: {e}")`
    },
    {
      id: 'javascript',
      title: 'JavaScript',
      language: 'javascript',
      code: `// Configuration
const API_KEY = 'your-api-key';
const BASE_URL = '${baseUrl}';
const APP_ID = ${appId};
const AGENT_ID = ${agentId};

/**
 * Call ${agentName}${agentType === 'ocr_agent' ? ' (OCR Agent)' : hasSilo ? ' (RAG-enabled)' : ''}
 */
async function callAgent(message, options = {}) {
  const url = \`\${BASE_URL}/public/v1/app/\${APP_ID}/call/\${AGENT_ID}\`;
  
  const payload = { message };
  
  if (options.conversationId) {
    payload.conversation_id = options.conversationId;
  }${hasSilo ? `
  
  if (options.searchParams) {
    payload.search_params = options.searchParams;
  }` : ''}${agentType === 'ocr_agent' ? `
  
  if (options.attachments) {
    payload.attachments = options.attachments;
  }` : ''}
  
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'X-API-KEY': API_KEY,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    });
    
    if (!response.ok) {
      throw new Error(\`HTTP error! status: \${response.status}\`);
    }
    
    return await response.json();
  } catch (error) {
    console.error('Error calling agent:', error);
    throw error;
  }
}

/**
 * Reset conversation for ${agentName}
 */
async function resetConversation() {
  const url = \`\${BASE_URL}/public/v1/app/\${APP_ID}/reset/\${AGENT_ID}\`;
  
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'X-API-KEY': API_KEY
      }
    });
    
    if (!response.ok) {
      throw new Error(\`HTTP error! status: \${response.status}\`);
    }
    
    return await response.json();
  } catch (error) {
    console.error('Error resetting conversation:', error);
    throw error;
  }
}

// Example usage
(async () => {
  try {${hasSilo ? `
    // Example with metadata filtering
    const result = await callAgent('Your question here', {
      searchParams: {
        metadata_filter: {
          category: 'documents',
          department: 'engineering'
        }
      }
    });` : agentType === 'ocr_agent' ? `
    // Example with file attachment
    const result = await callAgent('Analyze this document', {
      attachments: [
        {
          file_reference: 'uploaded-file-reference',
          filename: 'document.pdf'
        }
      ]
    });` : `
    const result = await callAgent('Your question here');`}
    console.log('Agent response:', result.response);
    console.log('Conversation ID:', result.conversation_id);
  } catch (error) {
    console.error('Failed to call agent:', error);
  }
})();`
    },
    {
      id: 'nodejs',
      title: 'Node.js',
      language: 'javascript',
      code: `const axios = require('axios');

// Configuration
const API_KEY = 'your-api-key';
const BASE_URL = '${baseUrl}';
const APP_ID = ${appId};
const AGENT_ID = ${agentId};

/**
 * Call ${agentName}${agentType === 'ocr_agent' ? ' (OCR Agent)' : hasSilo ? ' (RAG-enabled)' : ''}
 */
async function callAgent(message, options = {}) {
  const url = \`\${BASE_URL}/public/v1/app/\${APP_ID}/call/\${AGENT_ID}\`;
  
  const payload = { message };
  
  if (options.conversationId) {
    payload.conversation_id = options.conversationId;
  }${hasSilo ? `
  
  if (options.searchParams) {
    payload.search_params = options.searchParams;
  }` : ''}${agentType === 'ocr_agent' ? `
  
  if (options.attachments) {
    payload.attachments = options.attachments;
  }` : ''}
  
  try {
    const response = await axios.post(url, payload, {
      headers: {
        'X-API-KEY': API_KEY,
        'Content-Type': 'application/json'
      }
    });
    
    return response.data;
  } catch (error) {
    console.error('Error calling agent:', error.response?.data || error.message);
    throw error;
  }
}

/**
 * Reset conversation for ${agentName}
 */
async function resetConversation() {
  const url = \`\${BASE_URL}/public/v1/app/\${APP_ID}/reset/\${AGENT_ID}\`;
  
  try {
    const response = await axios.post(url, {}, {
      headers: {
        'X-API-KEY': API_KEY
      }
    });
    
    return response.data;
  } catch (error) {
    console.error('Error resetting conversation:', error.response?.data || error.message);
    throw error;
  }
}

// Example usage
(async () => {
  try {${hasSilo ? `
    // Example with metadata filtering
    const result = await callAgent('Your question here', {
      searchParams: {
        metadata_filter: {
          category: 'documents',
          department: 'engineering'
        }
      }
    });` : agentType === 'ocr_agent' ? `
    // Example with file attachment
    const result = await callAgent('Analyze this document', {
      attachments: [
        {
          file_reference: 'uploaded-file-reference',
          filename: 'document.pdf'
        }
      ]
    });` : `
    const result = await callAgent('Your question here');`}
    console.log('Agent response:', result.response);
    console.log('Conversation ID:', result.conversation_id);
  } catch (error) {
    console.error('Failed to call agent:', error);
  }
})();`
    }
  ];

  const copyToClipboard = async (text: string, exampleId: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(exampleId);
      setTimeout(() => setCopied(null), 2000);
    } catch (err) {
      console.error('Failed to copy text: ', err);
    }
  };

  const selectedExampleData = examples.find(ex => ex.id === selectedExample);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div className="flex items-center">
          <span className="text-blue-500 text-xl mr-3">🔗</span>
          <div>
            <h3 className="text-lg font-semibold text-blue-900">API Integration Examples</h3>
            <p className="text-blue-700 text-sm mt-1">
              Use these examples to integrate <strong>{agentName}</strong> into your applications
            </p>
          </div>
        </div>
      </div>

      {/* Agent Capabilities Info */}
      <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
        <h4 className="font-medium text-gray-900 mb-3">🤖 Agent Capabilities</h4>
        <div className="space-y-2 text-sm">
          <div className="flex items-center">
            <span className="w-20 text-gray-600">Type:</span>
            <span className="font-medium">{agentType === 'ocr_agent' ? 'OCR Agent' : 'AI Agent'}</span>
          </div>
          {hasSilo && (
            <div className="flex items-center">
              <span className="w-20 text-gray-600">RAG:</span>
              <span className="font-medium text-green-600">✓ Enabled ({siloName})</span>
            </div>
          )}
          {agentType === 'ocr_agent' && (
            <div className="flex items-center">
              <span className="w-20 text-gray-600">Files:</span>
              <span className="font-medium text-green-600">✓ Supports attachments</span>
            </div>
          )}
        </div>
      </div>

      {/* API Info */}
      <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
        <h4 className="font-medium text-gray-900 mb-3">🔑 API Information</h4>
        <div className="space-y-2 text-sm">
          <div className="flex items-center justify-between">
            <span className="text-gray-600">Endpoint:</span>
            <code className="bg-white px-2 py-1 rounded border text-xs">{endpoint}</code>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-gray-600">Authentication:</span>
            <code className="bg-white px-2 py-1 rounded border text-xs">X-API-KEY header</code>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-gray-600">Method:</span>
            <code className="bg-white px-2 py-1 rounded border text-xs">POST</code>
          </div>
        </div>
        <div className="mt-3 p-3 bg-yellow-50 border border-yellow-200 rounded text-sm text-yellow-800">
          <span className="mr-2">💡</span>
          Get your API key from the <strong>Settings → API Keys</strong> page
        </div>
      </div>

      {/* Request Body Schema */}
      <div className="bg-indigo-50 border border-indigo-200 rounded-lg p-4">
        <h4 className="font-medium text-indigo-900 mb-3">📋 Request Body for {agentName}</h4>
        <pre className="bg-white p-3 rounded border text-sm overflow-x-auto">
          <code>{requestBodyJson}</code>
        </pre>
      </div>

      {/* Language Selector */}
      <div className="flex space-x-1 bg-gray-100 p-1 rounded-lg">
        {examples.map((example) => (
          <button
            key={example.id}
            onClick={() => setSelectedExample(example.id)}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              selectedExample === example.id
                ? 'bg-white text-blue-600 shadow-sm'
                : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            {example.title}
          </button>
        ))}
      </div>

      {/* Code Example */}
      {selectedExampleData && (
        <div className="relative">
          <div className="flex items-center justify-between mb-2">
            <h4 className="font-medium text-gray-900">{selectedExampleData.title} Example</h4>
            <button
              onClick={() => copyToClipboard(selectedExampleData.code, selectedExampleData.id)}
              className={`px-3 py-1 text-sm rounded-md transition-colors ${
                copied === selectedExampleData.id
                  ? 'bg-green-100 text-green-700'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              {copied === selectedExampleData.id ? '✓ Copied!' : '📋 Copy'}
            </button>
          </div>
          <div className="relative">
            <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg overflow-x-auto text-sm">
              <code>{selectedExampleData.code}</code>
            </pre>
          </div>
        </div>
      )}

      {/* Response Format Info */}
      <div className="bg-green-50 border border-green-200 rounded-lg p-4">
        <h4 className="font-medium text-green-900 mb-3">📄 Expected Response Format</h4>
        <pre className="bg-white p-3 rounded border text-sm overflow-x-auto">
          <code>{`{
  "response": "Agent's response text",
  "conversation_id": "unique-conversation-identifier", 
  "usage": {
    "agent_name": "${agentName}",
    "agent_type": "${agentType}",
    "files_processed": ${agentType === 'ocr_agent' ? '1' : '0'},
    "has_memory": false
  }
}`}</code>
        </pre>
      </div>

      {/* Error Handling Info */}
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <h4 className="font-medium text-red-900 mb-3">⚠️ Error Handling</h4>
        <div className="space-y-2 text-sm text-red-800">
          <div><strong>401 Unauthorized:</strong> Invalid or missing API key</div>
          <div><strong>404 Not Found:</strong> Agent not found or no access</div>
          <div><strong>500 Internal Server Error:</strong> Agent execution failed</div>
        </div>
      </div>
    </div>
  );
}

export default APIExamples; 