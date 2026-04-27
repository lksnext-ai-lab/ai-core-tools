import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { CheckCircle2, XCircle } from 'lucide-react';
import FormActions from './FormActions';
import { apiService } from '../../services/api';
import Alert from '../ui/Alert';

export interface ServiceFormData {
  name: string;
  provider: string;
  model_name: string;
  api_key: string;
  base_url: string;
  supports_video?: boolean;
}

export interface ServiceData {
  service_id: number;
  name: string;
  provider: string;
  model_name: string;
  api_key: string;
  base_url: string;
  supports_video?: boolean;
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
  formTitle: _formTitle,
  serviceType,
  needsApiKey = false
}: Readonly<BaseServiceFormProps>) {
  const { appId } = useParams();
  const [formData, setFormData] = useState<ServiceFormData>({
    name: '',
    provider: '',
    model_name: '',
    api_key: '',
    base_url: '',
    supports_video: false
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ status: string; message: string; response?: string } | null>(null);
  const [isTesting, setIsTesting] = useState(false);
  const [apiKeyChanged, setApiKeyChanged] = useState(false);

  const isEditing = !!service && service.service_id !== 0;
  const MASKED_KEY_PREFIX = '****';

  // Initialize form with existing service data
  useEffect(() => {
    if (service) {
      setFormData({
        name: service.name || '',
        provider: service.provider || '',
        model_name: service.model_name || '',
        supports_video: service.supports_video || false,
        api_key: service.api_key === 'CHANGE_ME' ? '' : (service.api_key || ''),
        base_url: service.base_url || ''
      });
      setApiKeyChanged(false);
    }
  }, [service]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    if (name === 'api_key') {
      setApiKeyChanged(true);
    }
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));

    // Auto-fill base URL when provider changes
    if (name === 'provider' && value) {
      const defaults = getProviderDefaults(value);
      const isGoogleProvider = value === 'Google' || value === 'GoogleCloud';
      setFormData(prev => ({
        ...prev,
        base_url: prev.base_url || defaults.baseUrl,
        // Clear video flag when switching to a non-Google provider
        ...((!isGoogleProvider) && { supports_video: false }),
      }));
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
        result = await apiService.testAIServiceConnectionWithConfig(Number.parseInt(appId), formData);
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

    setIsSubmitting(true);
    try {
      const submitData = { ...formData };
      // If editing and api_key was not changed, send the original masked value
      // so the backend knows to preserve the existing key
      if (isEditing && !apiKeyChanged && service) {
        submitData.api_key = service.api_key || MASKED_KEY_PREFIX;
      }
      await onSubmit(submitData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setIsSubmitting(false);
    }
  };

  const currentProviderDefaults = formData.provider ? getProviderDefaults(formData.provider) : null;

  const isApiKeyRequired = formData.provider !== 'Custom' && formData.provider !== 'Ollama' && formData.provider !== 'GoogleCloud';
  const hasValidApiKey = isEditing
    ? (!apiKeyChanged || formData.api_key.trim() !== '' || !isApiKeyRequired)
    : (!isApiKeyRequired || formData.api_key.trim() !== '');
  const isValid =
    formData.name.trim() !== '' &&
    formData.provider !== '' &&
    formData.model_name.trim() !== '' &&
    hasValidApiKey;

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

        {/* Base URL / Project ID */}
        <div>
          <label htmlFor="base_url" className="block text-sm font-medium text-gray-700 mb-2">
            {formData.provider === 'GoogleCloud' ? 'GCP Project ID *' : 'Base URL *'}
          </label>
          <input
            type="text"
            id="base_url"
            name="base_url"
            value={formData.base_url}
            onChange={handleChange}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            placeholder={formData.provider === 'GoogleCloud' ? 'my-gcp-project-id' : 'https://api.example.com/v1'}
            required
          />
          {formData.provider === 'GoogleCloud' ? (
            <p className="mt-1 text-sm text-gray-500">
              Your Google Cloud Project ID (e.g., my-project-123)
            </p>
          ) : currentProviderDefaults && currentProviderDefaults.baseUrl ? (
            <p className="mt-1 text-sm text-gray-500">
              Default: {currentProviderDefaults.baseUrl}
            </p>
          ) : null}
        </div>

        {/* API Key */}
        <div>
          <label htmlFor="api_key" className="block text-sm font-medium text-gray-700 mb-2">
            API Key {formData.provider !== 'Custom' && formData.provider !== 'Ollama' && formData.provider !== 'GoogleCloud' && '*'}
          </label>
          <input
            type="password"
            id="api_key"
            name="api_key"
            value={formData.api_key}
            onChange={handleChange}
            onFocus={() => {
              if (!apiKeyChanged && formData.api_key.startsWith(MASKED_KEY_PREFIX)) {
                setFormData(prev => ({ ...prev, api_key: '' }));
                setApiKeyChanged(true);
              }
            }}
            autoComplete="off"
            data-lpignore="true"
            data-form-type="other"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            placeholder={formData.provider === 'GoogleCloud' ? '{"type":"service_account","project_id":...}' : formData.provider === 'Google' ? 'AIza...' : 'sk-...'}
            required={formData.provider !== 'Custom' && formData.provider !== 'Ollama'}
          />
          <p className="mt-1 text-sm text-gray-500">
            {formData.provider === 'GoogleCloud'
              ? 'Paste the full Service Account JSON key content'
              : formData.provider === 'Ollama' || formData.provider === 'Custom' 
              ? 'Optional for local/custom providers' 
              : 'Required for cloud providers'}
          </p>
        </div>

        {/* Google AI Studio setup hint */}
        {formData.provider === 'Google' && (
          <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
            <p className="text-xs font-medium text-blue-800 mb-1">Google AI Studio Setup</p>
            <ul className="text-xs text-blue-700 space-y-1 list-disc list-inside">
              <li><strong>API Key:</strong> Get it at <span className="font-mono">aistudio.google.com</span> → Get API key</li>
              <li><strong>Model:</strong> e.g., gemini-2.5-pro, gemini-2.0-flash, gemini-1.5-pro</li>
              <li><strong>Base URL:</strong> Leave as default unless using a custom endpoint</li>
            </ul>
          </div>
        )}

        {/* Google Cloud Vertex AI setup hint */}
        {formData.provider === 'GoogleCloud' && (
          <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg">
            <p className="text-xs font-medium text-emerald-800 mb-1">Google Cloud (Vertex AI) Setup</p>
            <ul className="text-xs text-emerald-700 space-y-1 list-disc list-inside">
              <li><strong>GCP Project ID:</strong> Your Google Cloud project identifier</li>
              <li><strong>Model:</strong> e.g., gemini-2.0-flash, gemini-1.5-pro</li>
            </ul>
            <p className="text-xs font-semibold text-emerald-800 mt-2 mb-1">Authentication:</p>
            <ol className="text-xs text-emerald-700 space-y-1 list-decimal list-inside">
              <li><strong>Service Account JSON:</strong> Paste the full JSON key content in the API Key field above</li>
            </ol>
            <p className="text-xs text-emerald-600 mt-1">
              Region defaults to europe-west1.
            </p>
          </div>
        )}

        {/* Video Capabilities — only available for Google providers */}
        {serviceType === 'AI' && (formData.provider === 'Google' || formData.provider === 'GoogleCloud') && (
          <div className="flex items-center space-x-3 p-3 bg-purple-50 border border-purple-200 rounded-lg">
            <input
              type="checkbox"
              id="supports_video"
              checked={formData.supports_video}
              onChange={(e) => setFormData(prev => ({ ...prev, supports_video: e.target.checked }))}
              className="h-4 w-4 text-purple-600 focus:ring-purple-500 border-gray-300 rounded"
            />
            <div>
              <label htmlFor="supports_video" className="text-sm font-medium text-gray-700 cursor-pointer">
                🎬 Video Analysis Capable
              </label>
              <p className="text-xs text-gray-500">
                Enable if this model can analyze video content (e.g., Gemini Flash, Gemini Pro)
              </p>
            </div>
          </div>
        )}

        {/* Test Result */}
        {testResult && (
          <div className={`p-3 rounded-lg border ${testResult.status === 'success' ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'}`}>
            <div className="flex items-start">
              <div className="flex-shrink-0">
                {testResult.status === 'success' ? <CheckCircle2 className="w-4 h-4 text-green-500" /> : <XCircle className="w-4 h-4 text-red-500" />}
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
