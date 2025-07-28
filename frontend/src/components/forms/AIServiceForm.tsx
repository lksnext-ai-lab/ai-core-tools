import { useState, useEffect } from 'react';

interface AIServiceFormData {
  name: string;
  provider: string;
  model_name: string;
  api_key: string;
  base_url: string;
}

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
  onSubmit: (data: AIServiceFormData) => Promise<void>;
  onCancel: () => void;
  loading?: boolean;
}

function AIServiceForm({ aiService, onSubmit, onCancel, loading = false }: AIServiceFormProps) {
  const [formData, setFormData] = useState<AIServiceFormData>({
    name: '',
    provider: '',
    model_name: '',
    api_key: '',
    base_url: ''
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isEditing = !!aiService && aiService.service_id !== 0;

  // Available providers (matching backend ProviderEnum values)
  const providers = [
    { value: 'OpenAI', name: 'OpenAI' },
    { value: 'Azure', name: 'Azure OpenAI' },
    { value: 'Anthropic', name: 'Anthropic' },
    { value: 'Custom', name: 'Custom/Ollama' },
    { value: 'MistralAI', name: 'Mistral' }
  ];

  // Provider-specific configurations (matching backend ProviderEnum values)
  const getProviderDefaults = (provider: string) => {
    const defaults: Record<string, {baseUrl: string, modelPlaceholder: string}> = {
      'OpenAI': {
        baseUrl: 'https://api.openai.com/v1',
        modelPlaceholder: 'gpt-4-turbo-preview'
      },
      'Azure': {
        baseUrl: 'https://your-resource.openai.azure.com',
        modelPlaceholder: 'gpt-4'
      },
      'Anthropic': {
        baseUrl: 'https://api.anthropic.com',
        modelPlaceholder: 'claude-3-opus-20240229'
      },
      'Custom': {
        baseUrl: 'http://localhost:11434',
        modelPlaceholder: 'llama2'
      },
      'MistralAI': {
        baseUrl: 'https://api.mistral.ai/v1',
        modelPlaceholder: 'mistral-large-latest'
      }
    };
    return defaults[provider] || { baseUrl: '', modelPlaceholder: 'model-name' };
  };

  // Initialize form with existing service data
  useEffect(() => {
    if (aiService) {
      setFormData({
        name: aiService.name || '',
        provider: aiService.provider || '',
        model_name: aiService.model_name || '',
        api_key: aiService.api_key || '',
        base_url: aiService.base_url || ''
      });
    }
  }, [aiService]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));

    // Auto-fill base URL when provider changes
    if (name === 'provider' && value) {
      const defaults = getProviderDefaults(value);
      setFormData(prev => ({
        ...prev,
        provider: value,
        base_url: prev.base_url || defaults.baseUrl
      }));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    // Basic validation
    if (!formData.name.trim()) {
      setError('Service name is required');
      return;
    }
    if (!formData.provider) {
      setError('Provider is required');
      return;
    }
    if (!formData.model_name.trim()) {
      setError('Model name is required');
      return;
    }
    if (!formData.api_key.trim() && formData.provider !== 'ollama') {
      setError('API key is required for this provider');
      return;
    }

    try {
      setIsSubmitting(true);
      setError(null);
      await onSubmit(formData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save AI service');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3">
          <p className="text-red-600 text-sm">{error}</p>
        </div>
      )}

      {/* Service Name */}
      <div>
        <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-2">
          Service Name *
        </label>
        <input
          type="text"
          id="name"
          name="name"
          value={formData.name}
          onChange={handleChange}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          placeholder="e.g., GPT-4 Production"
          required
        />
      </div>

      {/* Provider */}
      <div>
        <label htmlFor="provider" className="block text-sm font-medium text-gray-700 mb-2">
          Provider *
        </label>
        <select
          id="provider"
          name="provider"
          value={formData.provider}
          onChange={handleChange}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          required
        >
          <option value="">Select a provider</option>
          {providers.map((provider) => (
            <option key={provider.value} value={provider.value}>
              {provider.name}
            </option>
          ))}
        </select>
      </div>

      {/* Model Name */}
      <div>
        <label htmlFor="model_name" className="block text-sm font-medium text-gray-700 mb-2">
          Model Name *
        </label>
        <input
          type="text"
          id="model_name"
          name="model_name"
          value={formData.model_name}
          onChange={handleChange}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          placeholder={formData.provider ? getProviderDefaults(formData.provider).modelPlaceholder : 'e.g., gpt-4-turbo-preview'}
          required
        />
        {formData.provider && (
          <p className="mt-1 text-xs text-gray-500">
            Example for {providers.find(p => p.value === formData.provider)?.name}: {getProviderDefaults(formData.provider).modelPlaceholder}
          </p>
        )}
      </div>

      {/* API Key */}
      <div>
        <label htmlFor="api_key" className="block text-sm font-medium text-gray-700 mb-2">
          API Key {formData.provider !== 'ollama' && '*'}
        </label>
        <input
          type="password"
          id="api_key"
          name="api_key"
          value={formData.api_key}
          onChange={handleChange}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          placeholder={formData.provider === 'ollama' ? 'Not required for Ollama' : 'Enter your API key'}
          required={formData.provider !== 'ollama'}
        />
        {formData.provider === 'ollama' && (
          <p className="mt-1 text-xs text-gray-500">
            API key not required for local Ollama installations
          </p>
        )}
      </div>

      {/* Base URL */}
      <div>
        <label htmlFor="base_url" className="block text-sm font-medium text-gray-700 mb-2">
          Base URL
        </label>
        <input
          type="url"
          id="base_url"
          name="base_url"
          value={formData.base_url}
          onChange={handleChange}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          placeholder={formData.provider ? getProviderDefaults(formData.provider).baseUrl : 'https://api.example.com'}
        />
        <p className="mt-1 text-xs text-gray-500">
          Leave empty to use default endpoint for the provider
        </p>
      </div>

      {/* Provider-specific help */}
      {formData.provider && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
          <h4 className="text-sm font-medium text-blue-800 mb-1">
            {providers.find(p => p.value === formData.provider)?.name} Configuration
          </h4>
          <div className="text-xs text-blue-700">
            {formData.provider === 'azure' && (
              <p>For Azure OpenAI, use your deployment URL and include the deployment name in the model field.</p>
            )}
            {formData.provider === 'ollama' && (
              <p>Make sure Ollama is running locally. Default port is 11434. No API key required.</p>
            )}
            {formData.provider === 'openai' && (
              <p>Get your API key from the OpenAI platform. Models include gpt-4, gpt-3.5-turbo, etc.</p>
            )}
            {formData.provider === 'anthropic' && (
              <p>Get your API key from the Anthropic Console. Models include claude-3-opus, claude-3-sonnet, etc.</p>
            )}
          </div>
        </div>
      )}

      {/* Form Actions */}
      <div className="flex items-center justify-end space-x-3 pt-4 border-t border-gray-200">
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
          disabled={isSubmitting}
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={isSubmitting}
          className="px-6 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white rounded-lg flex items-center transition-colors"
        >
          {isSubmitting && (
            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
          )}
          {isSubmitting ? 'Saving...' : (isEditing ? 'Update Service' : 'Create Service')}
        </button>
      </div>
    </form>
  );
}

export default AIServiceForm; 