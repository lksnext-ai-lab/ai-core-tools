import BaseServiceForm, { type ServiceFormData, type ServiceData, type ProviderConfig, type ProviderDefaults } from './BaseServiceForm';

interface AIService {
  service_id: number;
  name: string;
  provider: string;
  model_name: string;
  api_key: string;
  base_url: string;
  created_at: string;
  available_providers: Array<{value: string, name: string}>;
}

interface AIServiceFormProps {
  aiService?: AIService | null;
  onSubmit: (data: ServiceFormData) => Promise<void>;
  onCancel: () => void;
}

const AI_PROVIDERS: ProviderConfig[] = [
  { value: 'OpenAI', name: 'OpenAI' },
  { value: 'Azure', name: 'Azure OpenAI' },
  { value: 'Anthropic', name: 'Anthropic' },
  { value: 'Custom', name: 'Custom/Ollama' },
  { value: 'MistralAI', name: 'Mistral' }
];

const getAIProviderDefaults = (provider: string): ProviderDefaults => {
  const defaults: Record<string, ProviderDefaults> = {
    'OpenAI': {
      baseUrl: 'https://api.openai.com/v1',
      modelPlaceholder: 'gpt-4o, gpt-4o-mini, o1, o1-mini'
    },
    'Azure': {
      baseUrl: '',
      modelPlaceholder: 'your-deployment-name'
    },
    'Anthropic': {
      baseUrl: 'https://api.anthropic.com/v1',
      modelPlaceholder: 'claude-3-5-sonnet-20241022, claude-3-5-haiku-20241022'
    },
    'Custom': {
      baseUrl: 'http://localhost:11434',
      modelPlaceholder: 'llama3.2, qwen2.5, etc.'
    },
    'MistralAI': {
      baseUrl: 'https://api.mistral.ai/v1',
      modelPlaceholder: 'mistral-large-latest, mistral-small-latest'
    }
  };
  return defaults[provider] || { baseUrl: '', modelPlaceholder: '' };
};

function AIServiceForm({ aiService, onSubmit, onCancel }: Readonly<AIServiceFormProps>) {
  // Convert AIService to ServiceData format if it exists
  const serviceData: ServiceData | null = aiService ? {
    service_id: aiService.service_id,
    name: aiService.name,
    provider: aiService.provider,
    model_name: aiService.model_name,
    api_key: aiService.api_key,
    base_url: aiService.base_url,
    created_at: aiService.created_at
  } : null;

  return (
    <BaseServiceForm
      service={serviceData}
      providers={AI_PROVIDERS}
      getProviderDefaults={getAIProviderDefaults}
      formTitle="AI Service Configuration"
      serviceType="AI"
      onSubmit={onSubmit}
      onCancel={onCancel}
    />
  );
}

export default AIServiceForm;

 