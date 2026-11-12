import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { KeyRound, ClipboardList, AlertTriangle, Check, CheckCircle2 } from 'lucide-react';
import Alert from '../ui/Alert';
import { Badge } from '../ui/Badge';
import CardApp from '../ui/CardApp';
import ButtonApp from '../ui/ButtonApp';
import SegmentedTabs from '../ui/SegmentedTabs';

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

function buildRequestBody(agentType: string, hasSilo: boolean) {
  const baseBody = {
    message: 'Your question here',
    conversation_id: 'optional-conversation-id',
  };

  if (agentType === 'ocr_agent') {
    return {
      ...baseBody,
      attachments: [{ file_reference: 'uploaded-file-reference', filename: 'document.pdf' }],
    };
  }

  if (hasSilo) {
    return {
      ...baseBody,
      search_params: { metadata_filter: { category: 'documents', department: 'engineering' } },
    };
  }

  return baseBody;
}

function buildCapabilityComments(agentType: string, hasSilo: boolean, siloName?: string): string {
  const comments: string[] = [];

  if (agentType === 'ocr_agent') {
    comments.push(
      '# OCR Agent - supports file attachments',
      '# Upload files first using the attach-file endpoint',
    );
  }

  if (hasSilo) {
    comments.push(
      `# RAG-enabled agent with silo: ${siloName ?? 'Unknown'}`,
      '# Supports metadata filtering for enhanced search',
    );
  }

  if (!hasSilo && agentType === 'agent') {
    comments.push('# Standard conversational agent');
  }

  return comments.join('\n');
}

interface AgentSnippetVars {
  agentLabel: string;
  pythonExtraParams: string;
  pythonPayloadBlock: string;
  pythonExampleUsage: string;
  jsSearchParamsBlock: string;
  jsAttachmentsBlock: string;
  jsExampleUsage: string;
}

function buildAgentSnippetVars(agentType: string, hasSilo: boolean): AgentSnippetVars {
  let agentLabel = '';
  if (agentType === 'ocr_agent') {
    agentLabel = ' (OCR Agent)';
  } else if (hasSilo) {
    agentLabel = ' (RAG-enabled)';
  }

  const pythonExtraParams = `${hasSilo ? ', search_params=None' : ''}${agentType === 'ocr_agent' ? ', attachments=None' : ''}`;

  let pythonPayloadBlock = '';
  if (hasSilo) {
    pythonPayloadBlock = `    if search_params:\n        payload["search_params"] = search_params`;
  } else if (agentType === 'ocr_agent') {
    pythonPayloadBlock = `    if attachments:\n        payload["attachments"] = attachments`;
  }

  let pythonExampleUsage = `\n    result = call_agent("Your question here")`;
  if (hasSilo) {
    pythonExampleUsage = `\n    # Example with metadata filtering\n    search_params = {\n        "metadata_filter": {\n            "category": "documents",\n            "department": "engineering"\n        }\n    }\n    result = call_agent("Your question here", search_params=search_params)`;
  } else if (agentType === 'ocr_agent') {
    pythonExampleUsage = `\n    # Example with file attachment\n    attachments = [\n        {\n            "file_reference": "uploaded-file-reference",\n            "filename": "document.pdf"\n        }\n    ]\n    result = call_agent("Analyze this document", attachments=attachments)`;
  }

  const jsSearchParamsBlock = hasSilo
    ? `\n  \n  if (options.searchParams) {\n    payload.search_params = options.searchParams;\n  }`
    : '';
  const jsAttachmentsBlock = agentType === 'ocr_agent'
    ? `\n  \n  if (options.attachments) {\n    payload.attachments = options.attachments;\n  }`
    : '';

  let jsExampleUsage = `\n    const result = await callAgent('Your question here');`;
  if (hasSilo) {
    jsExampleUsage = `\n    // Example with metadata filtering\n    const result = await callAgent('Your question here', {\n      searchParams: {\n        metadata_filter: {\n          category: 'documents',\n          department: 'engineering'\n        }\n      }\n    });`;
  } else if (agentType === 'ocr_agent') {
    jsExampleUsage = `\n    // Example with file attachment\n    const result = await callAgent('Analyze this document', {\n      attachments: [\n        {\n          file_reference: 'uploaded-file-reference',\n          filename: 'document.pdf'\n        }\n      ]\n    });`;
  }

  return { agentLabel, pythonExtraParams, pythonPayloadBlock, pythonExampleUsage, jsSearchParamsBlock, jsAttachmentsBlock, jsExampleUsage };
}

function APIExamples({ appId, agentId, agentName, agentType = 'agent', hasSilo = false, siloName }: Readonly<APIExamplesProps>) {
  const { t } = useTranslation('common');
  const [copied, setCopied] = useState<string | null>(null);
  const [selectedExample, setSelectedExample] = useState('curl');

  const baseUrl = globalThis.location.origin; // Use current domain
  const endpoint = `${baseUrl}/public/v1/app/${appId}/chat/${agentId}/call`;

  const requestBody = buildRequestBody(agentType, hasSilo);
  const requestBodyJson = JSON.stringify(requestBody, null, 2);
  const capabilityComments = buildCapabilityComments(agentType, hasSilo, siloName);

  const {
    agentLabel,
    pythonExtraParams,
    pythonPayloadBlock,
    pythonExampleUsage,
    jsSearchParamsBlock,
    jsAttachmentsBlock,
    jsExampleUsage,
  } = buildAgentSnippetVars(agentType, hasSilo);

  // Generate Windows-compatible JSON (escape double quotes)
  const requestBodyJsonWindows = requestBodyJson.replaceAll('"', String.raw`\"`);


  const examples: CodeExample[] = [
    {
      id: 'curl',
      title: 'cURL (Linux/Mac)',
      language: 'bash',
      code: `${capabilityComments}
curl -X POST "${endpoint}" \\
  -H "X-API-KEY: your-api-key" \\
  -H "Content-Type: application/json" \\
  -d '${requestBodyJson}'

# Reset conversation
curl -X POST "${baseUrl}/public/v1/app/${appId}/chat/${agentId}/reset" \\
  -H "X-API-KEY: your-api-key"`
    },
    {
      id: 'curl-windows',
      title: 'cURL (Windows)',
      language: 'powershell',
      code: `${capabilityComments.replaceAll('# ', '# ')}
# PowerShell requires curl.exe (not the curl alias)
curl.exe -X POST "${endpoint}" ^
  -H "X-API-KEY: your-api-key" ^
  -H "Content-Type: application/json" ^
  -d "${requestBodyJsonWindows}"

# Reset conversation
curl.exe -X POST "${baseUrl}/public/v1/app/${appId}/chat/${agentId}/reset" ^
  -H "X-API-KEY: your-api-key"

# Alternative: Using PowerShell native Invoke-RestMethod
$headers = @{
    "X-API-KEY" = "your-api-key"
    "Content-Type" = "application/json"
}

$body = @{
    message = "Your question here"
    conversation_id = "optional-conversation-id"
} | ConvertTo-Json

Invoke-RestMethod -Uri "${endpoint}" -Method POST -Headers $headers -Body $body

# Reset conversation (PowerShell)
Invoke-RestMethod -Uri "${baseUrl}/public/v1/app/${appId}/chat/${agentId}/reset" -Method POST -Headers @{"X-API-KEY" = "your-api-key"}`
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

def call_agent(message, conversation_id=None${pythonExtraParams}):
    """Call ${agentName}${agentLabel}"""
    url = f"{BASE_URL}/public/v1/app/{APP_ID}/chat/{AGENT_ID}/call"
    
    headers = {
        "X-API-KEY": API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {"message": message}
    if conversation_id:
        payload["conversation_id"] = conversation_id
${pythonPayloadBlock}
    
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()

def reset_conversation(conversation_id=None):
    """Reset conversation for ${agentName}"""
    url = f"{BASE_URL}/public/v1/app/{APP_ID}/chat/{AGENT_ID}/reset"
    headers = {"X-API-KEY": API_KEY}
    
    params = {}
    if conversation_id:
        params["conversation_id"] = conversation_id
    
    response = requests.post(url, headers=headers, params=params)
    response.raise_for_status()
    return response.json()

# Example usage
try:${pythonExampleUsage}
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
 * Call ${agentName}${agentLabel}
 */
async function callAgent(message, options = {}) {
  const url = \`\${BASE_URL}/public/v1/app/\${APP_ID}/chat/\${AGENT_ID}/call\`;
  
  const payload = { message };
  
  if (options.conversationId) {
    payload.conversation_id = options.conversationId;
  }${jsSearchParamsBlock}${jsAttachmentsBlock}
  
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
  const url = \`\${BASE_URL}/public/v1/app/\${APP_ID}/chat/\${AGENT_ID}/reset\`;
  
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
  try {${jsExampleUsage}
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
 * Call ${agentName}${agentLabel}
 */
async function callAgent(message, options = {}) {
  const url = \`\${BASE_URL}/public/v1/app/\${APP_ID}/chat/\${AGENT_ID}/call\`;
  
  const payload = { message };
  
  if (options.conversationId) {
    payload.conversation_id = options.conversationId;
  }${jsSearchParamsBlock}${jsAttachmentsBlock}
  
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
async function resetConversation(conversationId = null) {
  const url = \`\${BASE_URL}/public/v1/app/\${APP_ID}/chat/\${AGENT_ID}/reset\`;
  
  const params = {};
  if (conversationId) {
    params.conversation_id = conversationId;
  }
  
  try {
    const response = await axios.post(url, {}, {
      headers: {
        'X-API-KEY': API_KEY
      },
      params: params
    });
    
    return response.data;
  } catch (error) {
    console.error('Error resetting conversation:', error.response?.data || error.message);
    throw error;
  }
}

// Example usage
(async () => {
  try {${jsExampleUsage}
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

  const codeBlockClasses = 'overflow-x-auto rounded-md border border-line bg-surface-tint p-3 font-mono text-xs text-fg dark:border-line-dark dark:bg-surface-tint-dark dark:text-fg-dark';
  const inlineCodeClasses = 'rounded border border-line bg-surface-tint px-2 py-1 font-mono text-xs text-fg break-all dark:border-line-dark dark:bg-surface-tint-dark dark:text-fg-dark';

  return (
    <div className="space-y-5 pt-4">
      {/* Page header + Agent Capabilities */}
      <CardApp variant="canvas" className="p-6">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h3 className="font-display text-2xl font-normal tracking-[-0.02em] text-ink dark:text-ink-dark">{t('agentPlayground.apiExamples.title')}</h3>
            <p className="mt-1 text-sm text-fg-secondary dark:text-fg-secondary-dark">
              {t('agentPlayground.apiExamples.description', { agentName })}
            </p>
          </div>
          <div className="flex flex-wrap gap-x-8 gap-y-3">
            <div>
              <h4 className="mb-1 text-xs uppercase tracking-wider text-bronze dark:text-bronze-dark">{t('agentPlayground.apiExamples.type')}</h4>
              <Badge label={t(agentType === 'ocr_agent' ? 'agentPlayground.apiExamples.ocrAgent' : 'agentPlayground.apiExamples.aiAgent')} />
            </div>
            {hasSilo && (
              <div>
                <h4 className="mb-1 text-xs uppercase tracking-wider text-bronze dark:text-bronze-dark">RAG</h4>
                <Badge variant="success" icon={<Check className="w-3 h-3" />} label={t('agentPlayground.apiExamples.enabled', { name: siloName })} />
              </div>
            )}
            {agentType === 'ocr_agent' && (
              <div>
                <h4 className="mb-1 text-xs uppercase tracking-wider text-bronze dark:text-bronze-dark">{t('agentPlayground.apiExamples.files')}</h4>
                <Badge variant="success" icon={<Check className="w-3 h-3" />} label={t('agentPlayground.apiExamples.supportsAttachments')} />
              </div>
            )}
          </div>
        </div>
      </CardApp>

      {/* API Information */}
      <CardApp icon={KeyRound} titulo={t('agentPlayground.apiExamples.information')}>
        <div className="flex flex-wrap gap-x-8 gap-y-3 text-sm">
          <div className="flex min-w-0 items-center gap-2">
            <span className="shrink-0 text-fg-tertiary dark:text-fg-tertiary-dark">{t('agentPlayground.apiExamples.endpoint')}:</span>
            <code className={inlineCodeClasses}>{endpoint}</code>
          </div>
          <div className="flex items-center gap-2">
            <span className="shrink-0 text-fg-tertiary dark:text-fg-tertiary-dark">{t('agentPlayground.apiExamples.authentication')}:</span>
            <code className={inlineCodeClasses}>X-API-KEY header</code>
          </div>
          <div className="flex items-center gap-2">
            <span className="shrink-0 text-fg-tertiary dark:text-fg-tertiary-dark">{t('agentPlayground.apiExamples.method')}:</span>
            <code className={inlineCodeClasses}>POST</code>
          </div>
        </div>
        <Alert
          type="warning"
          polite
          className="mt-4 !p-3"
          message={t('agentPlayground.apiExamples.apiKeyNotice')}
        />
      </CardApp>

      {/* Request Body + Response Format */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <CardApp  titulo={t('agentPlayground.apiExamples.requestBodyFor', { agentName })} icon={ClipboardList}>
          <pre className={codeBlockClasses}>
            <code>{requestBodyJson}</code>
          </pre>
        </CardApp>

        <CardApp  titulo={t('agentPlayground.apiExamples.expectedResponse')} icon={CheckCircle2}>
          <pre className={codeBlockClasses}>
            <code>{`{
  "response": "Agent's response text",
  "conversation_id": "unique-conversation-identifier",
  "usage": {
    "agent_name": "${agentName}",
    "agent_type": "${agentType}",
    "files_processed": ${agentType === 'ocr_agent' ? '1' : '0'},
    "has_memory": false
  }
}`}
            </code>
          </pre>
        </CardApp>
      </div>

      {/* Code Example */}
      <CardApp className="space-y-4">
        {/* Language Selector */}
        <SegmentedTabs
          tabs={examples.map((example) => ({ id: example.id, label: example.title }))}
          activeTab={selectedExample}
          onChange={setSelectedExample}
          ariaLabel={t('agentPlayground.apiExamples.exampleLanguage')}
          className="overflow-x-auto [&>button]:flex-[1_0_auto] [&>button]:whitespace-nowrap [&>button]:px-3"
        />

        {selectedExampleData && (
          <div>
            <div className="mb-2 flex items-center justify-between">
              <h4 className="font-display text-base font-normal text-fg dark:text-fg-dark">{t('agentPlayground.apiExamples.exampleTitle', { title: selectedExampleData.title })}</h4>
              <ButtonApp
                variant={copied === selectedExampleData.id ? 'secondary' : 'muted'}
                size="small"
                icon={copied === selectedExampleData.id ? <Check className="w-4 h-4" /> : <ClipboardList className="w-4 h-4" />}
                label={copied === selectedExampleData.id ? t('agentPlayground.apiExamples.copied') : t('agentPlayground.apiExamples.copy')}
                onClick={() => { void copyToClipboard(selectedExampleData.code, selectedExampleData.id); }}
              />
            </div>
            <pre className="overflow-x-auto rounded-lg bg-ink p-4 font-mono text-xs leading-relaxed text-ink-on dark:border dark:border-line-dark dark:bg-canvas-dark dark:text-fg-dark">
              <code>{selectedExampleData.code}</code>
            </pre>
          </div>
        )}
      </CardApp>

      {/* Error Handling */}
      <CardApp titulo={t('agentPlayground.apiExamples.errorHandling')} icon={AlertTriangle }>
        <div className="flex flex-wrap gap-x-8 gap-y-3 text-sm text-fg-secondary dark:text-fg-secondary-dark">
          <div className="flex items-center gap-3"><Badge variant="error" label="401" className="w-12 justify-center" /><span><strong className="font-medium text-fg dark:text-fg-dark">{t('agentPlayground.apiExamples.unauthorized')}:</strong> {t('agentPlayground.apiExamples.invalidApiKey')}</span></div>
          <div className="flex items-center gap-3"><Badge variant="error" label="404" className="w-12 justify-center" /><span><strong className="font-medium text-fg dark:text-fg-dark">{t('agentPlayground.apiExamples.notFound')}:</strong> {t('agentPlayground.apiExamples.agentNotFound')}</span></div>
          <div className="flex items-center gap-3"><Badge variant="error" label="500" className="w-12 justify-center" /><span><strong className="font-medium text-fg dark:text-fg-dark">{t('agentPlayground.apiExamples.internalServerError')}:</strong> {t('agentPlayground.apiExamples.agentExecutionFailed')}</span></div>
        </div>
      </CardApp>
    </div>
  );
}

export default APIExamples; 