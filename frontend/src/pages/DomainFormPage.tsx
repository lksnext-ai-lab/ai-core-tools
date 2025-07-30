import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { apiService } from '../services/api';

interface EmbeddingService {
  service_id: number;
  name: string;
}

interface DomainFormData {
  name: string;
  description: string;
  base_url: string;
  content_tag: string;
  content_class: string;
  content_id: string;
  embedding_service_id?: number;
}

function DomainFormPage() {
  const { appId, domainId } = useParams<{ appId: string; domainId: string }>();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [embeddingServices, setEmbeddingServices] = useState<EmbeddingService[]>([]);
  
  const [formData, setFormData] = useState<DomainFormData>({
    name: '',
    description: '',
    base_url: '',
    content_tag: 'body',
    content_class: '',
    content_id: '',
    embedding_service_id: undefined
  });

  const isNewDomain = domainId === 'new' || domainId === '0';

  useEffect(() => {
    loadDomainData();
  }, [appId, domainId]);

  async function loadDomainData() {
    if (!appId) return;
    
    try {
      setLoading(true);
      setError(null);
      
      const domainIdNum = isNewDomain ? 0 : parseInt(domainId || '0');
      const response = await apiService.getDomain(parseInt(appId), domainIdNum);
      
      // Extract form data from response
      const domain = response; // Response is the domain object directly, not response.data
      setEmbeddingServices(domain.embedding_services || []);
      
      if (!isNewDomain) {
        setFormData({
          name: domain.name || '',
          description: domain.description || '',
          base_url: domain.base_url || '',
          content_tag: domain.content_tag || 'body',
          content_class: domain.content_class || '',
          content_id: domain.content_id || '',
          embedding_service_id: domain.embedding_service_id || undefined
        });
      } else {
        // Set default embedding service if only one exists
        if (domain.embedding_services?.length === 1) {
          setFormData(prev => ({
            ...prev,
            embedding_service_id: domain.embedding_services[0].service_id
          }));
        }
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
      
      const domainIdNum = isNewDomain ? 0 : parseInt(domainId || '0');
      await apiService.createDomain(parseInt(appId), domainIdNum, formData);
      
      // Navigate back to domains list
      navigate(`/apps/${appId}/domains`);
    } catch (err) {
      console.error('Error saving domain:', err);
      setError('Failed to save domain');
      setSaving(false);
    }
  }

  function handleInputChange(field: keyof DomainFormData, value: string | number) {
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
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Domain Name *
            </label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => handleInputChange('name', e.target.value)}
              className="w-full p-3 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="My Website"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Base URL *
            </label>
            <input
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
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Description
          </label>
          <textarea
            value={formData.description}
            onChange={(e) => handleInputChange('description', e.target.value)}
            className="w-full p-3 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            rows={3}
            placeholder="Description of this domain..."
          />
        </div>

        {/* Embedding Service Selection */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Embedding Service *
          </label>
          <select
            value={formData.embedding_service_id || ''}
            onChange={(e) => handleInputChange('embedding_service_id', parseInt(e.target.value))}
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

        {/* Content Extraction Configuration */}
        <div className="border-t pt-6">
          <h3 className="text-lg font-medium text-gray-900 mb-4">Content Extraction Settings</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Content Tag
              </label>
              <input
                type="text"
                value={formData.content_tag}
                onChange={(e) => handleInputChange('content_tag', e.target.value)}
                className="w-full p-3 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="body"
              />
              <p className="text-xs text-gray-500 mt-1">HTML tag to extract content from (default: body)</p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Content Class
              </label>
              <input
                type="text"
                value={formData.content_class}
                onChange={(e) => handleInputChange('content_class', e.target.value)}
                className="w-full p-3 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="main-content"
              />
              <p className="text-xs text-gray-500 mt-1">CSS class to filter content (optional)</p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Content ID
              </label>
              <input
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
            disabled={saving || embeddingServices.length === 0}
          >
            {saving ? 'Saving...' : isNewDomain ? 'Create Domain' : 'Update Domain'}
          </button>
        </div>
      </form>
    </div>
  );
}

export default DomainFormPage; 