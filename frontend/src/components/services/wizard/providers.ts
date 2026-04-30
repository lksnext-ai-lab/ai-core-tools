import type { LucideIcon } from 'lucide-react';
import { Bot, Cloud, Cpu, Globe, Server, Sparkles, Zap } from 'lucide-react';
import type { ServiceKind } from '../../../types/services';

export type ApiKeyMode = 'required' | 'optional' | 'none';

export interface ProviderUIDescriptor {
  readonly value: string;
  readonly label: string;
  readonly description: string;
  readonly Icon: LucideIcon;
  /**
   * Whether the API key field is shown and validated:
   * - "required": always shown and must be filled before Next
   * - "optional": shown but Next does not enforce a value
   * - "none": not shown at all
   */
  readonly apiKey: ApiKeyMode;
  readonly needsBaseUrl: boolean;
  readonly baseUrlPlaceholder?: string;
  readonly defaultBaseUrl?: string;
  /** False for providers without a /models endpoint (Azure, GoogleCloud). */
  readonly supportsModelListing: boolean;
  /** Extra fields shown in the credentials step for manual-input providers. */
  readonly manualFields?: readonly ('api_version' | 'project_id' | 'region')[];
  readonly apiKeyPlaceholder: string;
  readonly apiKeyHelp: string;
  /** Optional link to the provider's API key management page. Rendered
   *  next to the api_key field as a "Get your key →" affordance. */
  readonly apiKeyDocUrl?: string;
  readonly supportedFor: readonly ServiceKind[];
}

const ALL_PROVIDERS: readonly ProviderUIDescriptor[] = [
  {
    value: 'OpenAI',
    label: 'OpenAI',
    description: 'GPT-4o, o-series, embeddings and Whisper.',
    Icon: Sparkles,
    apiKey: 'required',
    needsBaseUrl: false,
    supportsModelListing: true,
    apiKeyPlaceholder: 'sk-...',
    apiKeyHelp: 'Find your API key at platform.openai.com',
    apiKeyDocUrl: 'https://platform.openai.com/api-keys',
    supportedFor: ['ai', 'embedding'],
  },
  {
    value: 'Anthropic',
    label: 'Anthropic',
    description: 'Claude Opus, Sonnet and Haiku.',
    Icon: Bot,
    apiKey: 'required',
    needsBaseUrl: false,
    supportsModelListing: true,
    apiKeyPlaceholder: 'sk-ant-...',
    apiKeyHelp: 'Find your API key at console.anthropic.com',
    apiKeyDocUrl: 'https://console.anthropic.com/settings/keys',
    supportedFor: ['ai'],
  },
  {
    value: 'MistralAI',
    label: 'Mistral AI',
    description: 'Mistral Large, Pixtral and embeddings.',
    Icon: Zap,
    apiKey: 'required',
    needsBaseUrl: false,
    supportsModelListing: true,
    apiKeyPlaceholder: 'mistral-...',
    apiKeyHelp: 'Find your API key at console.mistral.ai',
    apiKeyDocUrl: 'https://console.mistral.ai/api-keys',
    supportedFor: ['ai', 'embedding'],
  },
  {
    value: 'Google',
    label: 'Google AI Studio',
    description: 'Gemini family via the AI Studio API.',
    Icon: Sparkles,
    apiKey: 'required',
    needsBaseUrl: false,
    supportsModelListing: true,
    apiKeyPlaceholder: 'AIza...',
    apiKeyHelp: 'Generate an API key at aistudio.google.com',
    apiKeyDocUrl: 'https://aistudio.google.com/apikey',
    supportedFor: ['ai'],
  },
  {
    // Single AI Services option that covers both pure Ollama and any
    // self-hosted endpoint speaking the Ollama wire protocol. The backend
    // builds a ChatOllama instance for this provider, so the listing
    // also goes through Ollama's /api/tags.
    value: 'Custom',
    label: 'Ollama / Self-hosted',
    description: 'Local Ollama instance or any self-hosted endpoint speaking the Ollama protocol.',
    Icon: Cpu,
    apiKey: 'optional',
    needsBaseUrl: true,
    baseUrlPlaceholder: 'http://localhost:11434',
    defaultBaseUrl: 'http://localhost:11434',
    supportsModelListing: true,
    apiKeyPlaceholder: 'optional bearer token',
    apiKeyHelp: 'Optional. Only needed if your endpoint is behind auth.',
    supportedFor: ['ai'],
  },
  {
    // Embedding-only Ollama remains a separate option because the
    // EmbeddingProvider enum keeps "Ollama" distinct from "Custom"
    // (Custom uses HuggingFace Inference under the hood for embeddings).
    value: 'Ollama',
    label: 'Ollama',
    description: 'Local Ollama instance for embeddings.',
    Icon: Cpu,
    apiKey: 'optional',
    needsBaseUrl: true,
    baseUrlPlaceholder: 'http://localhost:11434',
    defaultBaseUrl: 'http://localhost:11434',
    supportsModelListing: true,
    apiKeyPlaceholder: 'optional bearer token',
    apiKeyHelp: 'Optional. Only needed if your endpoint is behind auth.',
    supportedFor: ['embedding'],
  },
  {
    // Custom for embeddings is the HuggingFace Inference API. There is
    // no generic /models listing — the user types the model id manually.
    value: 'Custom',
    label: 'HuggingFace Inference',
    description: 'Embedding models hosted on the HuggingFace Inference API.',
    Icon: Server,
    apiKey: 'required',
    needsBaseUrl: true,
    baseUrlPlaceholder: 'sentence-transformers/all-MiniLM-L6-v2',
    supportsModelListing: false,
    apiKeyPlaceholder: 'hf_...',
    apiKeyHelp: 'Token from huggingface.co/settings/tokens',
    apiKeyDocUrl: 'https://huggingface.co/settings/tokens',
    supportedFor: ['embedding'],
  },
  {
    value: 'Azure',
    label: 'Azure OpenAI',
    description: 'Azure OpenAI deployments. Listing is not available — enter the deployment manually.',
    Icon: Cloud,
    apiKey: 'required',
    needsBaseUrl: true,
    baseUrlPlaceholder: 'https://<resource>.openai.azure.com',
    supportsModelListing: false,
    // The deployment name is collected as the model id in the model step
    // (manualModelName), not here. Avoid asking for it twice.
    manualFields: ['api_version'],
    apiKeyPlaceholder: 'azure-key',
    apiKeyHelp: 'Use the key from your Azure OpenAI resource.',
    apiKeyDocUrl: 'https://learn.microsoft.com/azure/ai-services/openai/how-to/create-resource',
    supportedFor: ['ai', 'embedding'],
  },
  {
    value: 'GoogleCloud',
    label: 'Google Cloud (Vertex AI)',
    description: 'Vertex AI deployments. Authenticated with a service-account JSON.',
    Icon: Globe,
    apiKey: 'required',
    needsBaseUrl: true,
    baseUrlPlaceholder: 'my-gcp-project-id',
    supportsModelListing: false,
    manualFields: ['project_id', 'region'],
    apiKeyPlaceholder: '{"type":"service_account",...}',
    apiKeyHelp: 'Paste the full Service Account JSON key content.',
    apiKeyDocUrl: 'https://console.cloud.google.com/iam-admin/serviceaccounts',
    supportedFor: ['ai'],
  },
];

export function getProvidersForKind(kind: ServiceKind): readonly ProviderUIDescriptor[] {
  return ALL_PROVIDERS.filter((p) => p.supportedFor.includes(kind));
}

export function getProviderDescriptor(value: string): ProviderUIDescriptor | undefined {
  return ALL_PROVIDERS.find((p) => p.value === value);
}
