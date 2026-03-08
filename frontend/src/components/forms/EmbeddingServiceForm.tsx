import BaseServiceForm, { type ServiceFormData, type ServiceData, type ProviderConfig, type ProviderDefaults } from './BaseServiceForm';

interface EmbeddingService {
  service_id: number;
  name: string;
  provider: string;
  model_name: string;
  api_key: string;
  base_url: string;
  created_at: string;
  available_providers: Array<{value: string, name: string}>;
  needs_api_key?: boolean;
}

interface EmbeddingServiceFormProps {
  embeddingService?: EmbeddingService | null;
  onSubmit: (data: ServiceFormData) => Promise<void>;
  onCancel: () => void;
}

const EMBEDDING_PROVIDERS: ProviderConfig[] = [
  { value: 'OpenAI', name: 'OpenAI' },
  { value: 'Azure', name: 'Azure OpenAI' },
  { value: 'Ollama', name: 'Ollama' },
  { value: 'MistralAI', name: 'Mistral' },
  { value: 'Custom', name: 'Custom' }
];

const getEmbeddingProviderDefaults = (provider: string): ProviderDefaults => {
  const defaults: Record<string, ProviderDefaults> = {
    'OpenAI': {
      baseUrl: 'https://api.openai.com/v1',
      modelPlaceholder: 'text-embedding-3-large, text-embedding-3-small'
    },
    'Azure': {
      baseUrl: '',
      modelPlaceholder: 'text-embedding-ada-002'
    },
    'Ollama': {
      baseUrl: 'http://localhost:11434',
      modelPlaceholder: 'nomic-embed-text, mxbai-embed-large'
    },
    'MistralAI': {
      baseUrl: 'https://api.mistral.ai/v1',
      modelPlaceholder: 'mistral-embed'
    },
    'Custom': {
      baseUrl: '',
      modelPlaceholder: 'custom-embedding-model'
    }
  };
  return defaults[provider] || { baseUrl: '', modelPlaceholder: '' };
};

function EmbeddingServiceForm({ embeddingService, onSubmit, onCancel }: Readonly<EmbeddingServiceFormProps>) {
  // Convert EmbeddingService to ServiceData format if it exists
  const serviceData: ServiceData | null = embeddingService ? {
    service_id: embeddingService.service_id,
    name: embeddingService.name,
    provider: embeddingService.provider,
    model_name: embeddingService.model_name,
    api_key: embeddingService.api_key,
    base_url: embeddingService.base_url,
    created_at: embeddingService.created_at
  } : null;

  const needsApiKey = embeddingService?.needs_api_key ?? false;

  return (
    <BaseServiceForm
      service={serviceData}
      providers={EMBEDDING_PROVIDERS}
      getProviderDefaults={getEmbeddingProviderDefaults}
      formTitle="Embedding Service Configuration"
      serviceType="Embedding"
      onSubmit={onSubmit}
      onCancel={onCancel}
      needsApiKey={needsApiKey}
    />
  );
}

export default EmbeddingServiceForm;

 