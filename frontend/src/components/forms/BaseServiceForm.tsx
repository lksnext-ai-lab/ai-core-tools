import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import FormActions from './FormActions';
import { apiService } from '../../services/api';
import Alert from '../ui/Alert';

export interface ServiceFormData {
  name: string;
  provider: string;
  model_name: string;
  api_key: string;
  base_url: string;
}

export interface ServiceData {
  service_id: number;
  name: string;
  provider: string;
  model_name: string;
  api_key: string;
  base_url: string;
  created_at: string;
}

export interface ProviderConfig {
  value: string;
  name: string;
}

export interface ProviderDefaults {
  baseUrl: string;
  modelPlaceholder: string;
}

interface BaseServiceFormProps {
  service?: ServiceData | null;
  onSubmit: (data: ServiceFormData) => Promise<void>;
  onCancel: () => void;
  loading?: boolean;
  providers: ProviderConfig[];
  getProviderDefaults: (provider: string) => ProviderDefaults;
  formTitle: string;
  serviceType: string; // "AI Service" or "Embedding Service"
  needsApiKey?: boolean;
}

function BaseServiceForm({
  service,
  onSubmit,
  onCancel,
  providers,
  getProviderDefaults,
  formTitle,
  serviceType,
  needsApiKey = false
}: Readonly<BaseServiceFormProps>) {
  const { appId } = useParams();
  const [formData, setFormData] = useState<ServiceFormData>({
    name: '',
    provider: '',
    model_name: '',
    api_key: '',
    base_url: ''
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<any>(null);
  const [isTesting, setIsTesting] = useState(false);

  const isEditing = !!service && service.service_id !== 0;

  // Initialize form with existing service data
  useEffect(() => {
    if (service) {
      setFormData({
        name: service.name || '',
        provider: service.provider || '',
        model_name: service.model_name || '',
        api_key: service.api_key === 'CHANGE_ME' ? '' : (service.api_key || ''),
        base_url: service.base_url || ''
      });
    }
  }, [service]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));

    // Auto-fill base URL when provider changes
    if (name === 'provider' && value) {
      const defaults = getProviderDefaults(value);
      if (!formData.base_url || formData.base_url === '') {
        setFormData(prev => ({
          ...prev,
          base_url: defaults.baseUrl
        }));
      }
    }
  };

  const handleTestConnection = async () => {
    if (!appId) return;
    
    setIsTesting(true);
    setTestResult(null);
    setError(null);
    
    try {
      let result;
      if (serviceType === 'AI') {
        result = await apiService.testAIServiceConnectionWithConfig(parseInt(appId), formData);
      } else {
        // Embedding service test not implemented yet
        result = { status: 'error', message: 'Testing not supported for this service type yet' };
      }
      setTestResult(result);
    } catch (err) {
      setTestResult({ status: 'error', message: err instanceof Error ? err.message : 'Failed to test connection' });
    } finally {
      setIsTesting(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    
    // Validate required fields
    if (!formData.name.trim()) {
      setError('Name is required');
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
    if (!formData.base_url.trim()) {
      setError('Base URL is required');
      return;
    }

    setIsSubmitting(true);
    try {
      await onSubmit(formData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setIsSubmitting(false);
    }
  };

  const currentProviderDefaults = formData.provider ? getProviderDefaults(formData.provider) : null;

  const isApiKeyRequired = formData.provider !== 'Custom' && formData.provider !== 'Ollama';
  const isValid = 
    formData.name.trim() !== '' && 
    formData.provider !== '' && 
    formData.model_name.trim() !== '' && 
    formData.base_url.trim() !== '' &&
    (!isApiKeyRequired || formData.api_key.trim() !== '');

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <h2 className="text-2xl font-bold text-gray-900 mb-6">
        {isEditing ? `Edit ${serviceType}` : `Create New ${serviceType}`}
      </h2>

      {error && (
        <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg">
          <p className="text-red-800 text-sm">{error}</p>
        </div>
      )}

      {needsApiKey && (
        <Alert
          type="warning"
          title="API Key Required"
          message="This service was imported without an API key. Please enter a valid API key before saving."
          className="mb-4"
        />
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Name */}
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
            placeholder="My Service"
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
            {providers.map(provider => (
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
            placeholder={currentProviderDefaults?.modelPlaceholder || 'model-name'}
            required
          />
          {currentProviderDefaults && (
            <p className="mt-1 text-sm text-gray-500">
              Example: {currentProviderDefaults.modelPlaceholder}
            </p>
          )}
        </div>

        {/* Base URL */}
        <div>
          <label htmlFor="base_url" className="block text-sm font-medium text-gray-700 mb-2">
            Base URL *
          </label>
          <input
            type="text"
            id="base_url"
            name="base_url"
            value={formData.base_url}
            onChange={handleChange}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            placeholder="https://api.example.com/v1"
            required
          />
          {currentProviderDefaults && (
            <p className="mt-1 text-sm text-gray-500">
              Default: {currentProviderDefaults.baseUrl}
            </p>
          )}
        </div>

        {/* API Key */}
        <div>
          <label htmlFor="api_key" className="block text-sm font-medium text-gray-700 mb-2">
            API Key {formData.provider !== 'Custom' && formData.provider !== 'Ollama' && '*'}
          </label>
          <input
            type="password"
            id="api_key"
            name="api_key"
            value={formData.api_key}
            onChange={handleChange}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            placeholder="sk-..."
            required={formData.provider !== 'Custom' && formData.provider !== 'Ollama'}
          />
          <p className="mt-1 text-sm text-gray-500">
            {formData.provider === 'Ollama' || formData.provider === 'Custom' 
              ? 'Optional for local/custom providers' 
              : 'Required for cloud providers'}
          </p>
        </div>

        {/* Test Result */}
        {testResult && (
          <div className={`p-3 rounded-lg border ${testResult.status === 'success' ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'}`}>
            <div className="flex items-start">
              <div className="flex-shrink-0">
                <span className="text-xl">{testResult.status === 'success' ? '✅' : '❌'}</span>
              </div>
              <div className="ml-3 w-full">
                <h3 className={`text-sm font-medium ${testResult.status === 'success' ? 'text-green-800' : 'text-red-800'}`}>
                  {testResult.status === 'success' ? 'Connection Successful' : 'Connection Failed'}
                </h3>
                <div className={`mt-1 text-sm ${testResult.status === 'success' ? 'text-green-700' : 'text-red-700'}`}>
                  {testResult.message}
                </div>
                {testResult.response && (
                  <div className="mt-3">
                    <h4 className="text-xs font-semibold text-green-800 uppercase tracking-wider mb-2">Response</h4>
                    <div className="bg-white p-2 rounded border border-green-200 text-xs font-mono whitespace-pre-wrap max-h-40 overflow-y-auto">
                      {testResult.response}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        <div className="flex justify-between items-center pt-4 border-t border-gray-200">
          <div>
            {serviceType === 'AI' && (
              <button
                type="button"
                onClick={handleTestConnection}
                disabled={isTesting || isSubmitting}
                className={`px-4 py-2 rounded-lg text-sm font-medium border ${
                  isTesting 
                    ? 'bg-gray-100 text-gray-400 border-gray-200 cursor-not-allowed' 
                    : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                }`}
              >
                {isTesting ? 'Testing...' : 'Test Connection'}
              </button>
            )}
          </div>
          <FormActions
            onCancel={onCancel}
            isSubmitting={isSubmitting}
            isEditing={isEditing}
            submitButtonColor={serviceType === 'AI' ? 'blue' : 'green'}
            disabled={!isValid}
          />
        </div>
      </form>
    </div>
  );
}

export default BaseServiceForm;
