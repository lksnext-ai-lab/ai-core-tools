import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { apiService } from '../services/api';

interface EmbeddingService {
  service_id: number;
  name: string;
}

interface VectorDbOption {
  code: string;
  label: string;
}

interface DomainFormData {
  name: string;
  description: string;
  base_url: string;
  content_tag: string;
  content_class: string;
  content_id: string;
  embedding_service_id?: number;
  vector_db_type: string;
}

function DomainFormPage() {
  const { appId, domainId } = useParams<{ appId: string; domainId: string }>();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [embeddingServices, setEmbeddingServices] = useState<EmbeddingService[]>([]);
  const [vectorDbOptions, setVectorDbOptions] = useState<VectorDbOption[]>([]);

  const [formData, setFormData] = useState<DomainFormData>({
    name: '',
    description: '',
    base_url: '',
    content_tag: 'body',
    content_class: '',
    content_id: '',
    embedding_service_id: undefined,
    vector_db_type: 'PGVECTOR'
  });

  const isNewDomain = domainId === 'new' || domainId === '0';
  let submitButtonLabel = 'Update Domain';
  if (isNewDomain) {
    submitButtonLabel = 'Create Domain';
  }
  if (saving) {
    submitButtonLabel = 'Saving...';
  }
  const vectorDbSelectValue = vectorDbOptions.length === 0 ? '' : formData.vector_db_type;

  useEffect(() => {
    loadDomainData();
  }, [appId, domainId]);

  async function loadDomainData() {
    if (!appId) return;
    
    try {
      setLoading(true);
      setError(null);
      
      const numericAppId = Number.parseInt(appId, 10);
      const domainIdNum = isNewDomain ? 0 : Number.parseInt(domainId ?? '0', 10);
      const response = await apiService.getDomain(numericAppId, domainIdNum);

      // Extract form data from response
      const domain = response; // Response is the domain object directly, not response.data
      const availableVectorDbOptions: VectorDbOption[] = domain.vector_db_options || [];
      const normalizedVectorDbType = domain.vector_db_type?.toUpperCase();
      const matchedVectorDbOption = availableVectorDbOptions.find(
        (option: VectorDbOption) => option.code.toUpperCase() === normalizedVectorDbType
      );
      const vectorDbTypeValue = matchedVectorDbOption?.code
        || availableVectorDbOptions[0]?.code
        || normalizedVectorDbType
        || 'PGVECTOR';

      setEmbeddingServices(domain.embedding_services || []);
      setVectorDbOptions(availableVectorDbOptions);

      if (!isNewDomain) {
        setFormData({
          name: domain.name || '',
          description: domain.description || '',
          base_url: domain.base_url || '',
          content_tag: domain.content_tag || 'body',
          content_class: domain.content_class || '',
          content_id: domain.content_id || '',
          embedding_service_id: domain.embedding_service_id || undefined,
          vector_db_type: vectorDbTypeValue
        });
      }

      // If creating a new domain and there is a single embedding service,
      // preselect it as the default. Kept outside the else to avoid a
      // single-statement else block.
      if (isNewDomain && domain.embedding_services?.length === 1) {
        setFormData(prev => ({
          ...prev,
          embedding_service_id: domain.embedding_services[0].service_id
        }));
      }
    } catch (err) {
      console.error('Error loading domain data:', err);
      setError('Failed to load domain data');
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    
    if (!appId) return;
    
    try {
      setSaving(true);
      setError(null);
      
      const numericAppId = Number.parseInt(appId, 10);
      const domainIdNum = isNewDomain ? 0 : Number.parseInt(domainId ?? '0', 10);

      if (isNewDomain) {
        await apiService.createDomain(numericAppId, domainIdNum, formData);
      } else {
        await apiService.updateDomain(numericAppId, domainIdNum, formData);
      }
      
      // Navigate back to domains list
      navigate(`/apps/${appId}/domains`);
    } catch (err) {
      console.error('Error saving domain:', err);
      setError('Failed to save domain');
      setSaving(false);
    }
  }

  function handleInputChange(field: keyof DomainFormData, value: string | number | undefined) {
    setFormData(prev => ({
      ...prev,
      [field]: value
    }));
  }

  if (loading) {
    return (
      <div className="p-6">
        <div className="animate-pulse">
          <div className="h-8 bg-gray-200 rounded w-1/4 mb-6"></div>
          <div className="space-y-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-12 bg-gray-200 rounded"></div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="bg-red-50 border border-red-200 rounded-md p-4">
          <div className="flex">
            <div className="ml-3">
              <h3 className="text-sm font-medium text-red-800">Error</h3>
              <div className="mt-2 text-sm text-red-700">
                <p>{error}</p>
              </div>
              <div className="mt-4">
                <button
                  onClick={loadDomainData}
                  className="bg-red-100 px-2 py-1 rounded-md text-red-800 hover:bg-red-200"
                >
                  Try Again
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="mb-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-gray-900">
            {isNewDomain ? 'Create Domain' : 'Edit Domain'}
          </h1>
          <button
            onClick={() => navigate(`/apps/${appId}/domains`)}
            className="text-gray-600 hover:text-gray-900 px-3 py-1 rounded-md hover:bg-gray-100"
          >
            ← Back to Domains
          </button>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6 bg-white p-6 rounded-lg shadow">
        {/* Basic Information */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <label htmlFor="domain-name" className="block text-sm font-medium text-gray-700 mb-2">
              Domain Name *
            </label>
            <input
              id="domain-name"
              type="text"
              value={formData.name}
              onChange={(e) => handleInputChange('name', e.target.value)}
              className="w-full p-3 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="My Website"
              required
            />
          </div>

          <div>
            <label htmlFor="base-url" className="block text-sm font-medium text-gray-700 mb-2">
              Base URL *
            </label>
            <input
              id="base-url"
              type="url"
              value={formData.base_url}
              onChange={(e) => handleInputChange('base_url', e.target.value)}
              className="w-full p-3 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="https://example.com"
              required
            />
          </div>
        </div>

        <div>
          <label htmlFor="description" className="block text-sm font-medium text-gray-700 mb-2">
            Description
          </label>
          <textarea
            id="description"
            value={formData.description}
            onChange={(e) => handleInputChange('description', e.target.value)}
            className="w-full p-3 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            rows={3}
            placeholder="Description of this domain..."
          />
        </div>

        {/* Embedding Service Selection */}
        <div>
          <label htmlFor="embedding-service" className="block text-sm font-medium text-gray-700 mb-2">
            Embedding Service *
          </label>
          <select
            id="embedding-service"
            value={formData.embedding_service_id || ''}
            onChange={(e) => {
              const value = e.target.value;
              handleInputChange('embedding_service_id', value ? Number.parseInt(value, 10) : undefined);
            }}
            className="w-full p-3 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            required
          >
            <option value="">Select an embedding service</option>
            {embeddingServices.map((service) => (
              <option key={service.service_id} value={service.service_id}>
                {service.name}
              </option>
            ))}
          </select>
          {embeddingServices.length === 0 && (
            <p className="text-sm text-red-600 mt-1">
              No embedding services available. Please create one first.
            </p>
          )}
        </div>

        {/* Vector Database Selection */}
        <div>
          <label htmlFor="domain-vector-db" className="block text-sm font-medium text-gray-700 mb-2">
            Vector Database *
          </label>
          <select
            id="domain-vector-db"
            value={vectorDbSelectValue}
            onChange={(e) => handleInputChange('vector_db_type', e.target.value)}
            className="w-full p-3 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            required
            disabled={vectorDbOptions.length === 0}
          >
            {vectorDbOptions.map((option) => (
              <option key={option.code} value={option.code}>
                {option.label}
              </option>
            ))}
          </select>
          {vectorDbOptions.length === 0 && (
            <p className="text-sm text-red-600 mt-1">
              No vector databases available. Please configure a silo with vector support first.
            </p>
          )}
        </div>

        {/* Content Extraction Configuration */}
        <div className="border-t pt-6">
          <h3 className="text-lg font-medium text-gray-900 mb-4">Content Extraction Settings</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div>
              <label htmlFor="content-tag" className="block text-sm font-medium text-gray-700 mb-2">
                Content Tag
              </label>
              <input
                id="content-tag"
                type="text"
                value={formData.content_tag}
                onChange={(e) => handleInputChange('content_tag', e.target.value)}
                className="w-full p-3 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="body"
              />
              <p className="text-xs text-gray-500 mt-1">HTML tag to extract content from (default: body)</p>
            </div>

            <div>
              <label htmlFor="content-class" className="block text-sm font-medium text-gray-700 mb-2">
                Content Class
              </label>
              <input
                id="content-class"
                type="text"
                value={formData.content_class}
                onChange={(e) => handleInputChange('content_class', e.target.value)}
                className="w-full p-3 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="main-content"
              />
              <p className="text-xs text-gray-500 mt-1">CSS class to filter content (optional)</p>
            </div>

            <div>
              <label htmlFor="content-id" className="block text-sm font-medium text-gray-700 mb-2">
                Content ID
              </label>
              <input
                id="content-id"
                type="text"
                value={formData.content_id}
                onChange={(e) => handleInputChange('content_id', e.target.value)}
                className="w-full p-3 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="content"
              />
              <p className="text-xs text-gray-500 mt-1">HTML ID to filter content (optional)</p>
            </div>
          </div>
        </div>

        {/* Form Actions */}
        <div className="flex justify-end space-x-4 pt-6 border-t">
          <button
            type="button"
            onClick={() => navigate(`/apps/${appId}/domains`)}
            className="px-4 py-2 text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200"
            disabled={saving}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
            disabled={saving || embeddingServices.length === 0 || vectorDbOptions.length === 0}
          >
            {submitButtonLabel}
          </button>
        </div>
      </form>
    </div>
  );
}

export default DomainFormPage; 