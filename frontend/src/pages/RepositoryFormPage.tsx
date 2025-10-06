import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { apiService } from '../services/api';

interface RepositoryFormData {
  name: string;
  embedding_service_id?: number;
}

interface EmbeddingService {
  service_id: number;
  name: string;
  provider: string;
  model_name: string;
}

const RepositoryFormPage: React.FC = () => {
  const { appId, repositoryId } = useParams<{ appId: string; repositoryId: string }>();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [embeddingServices, setEmbeddingServices] = useState<EmbeddingService[]>([]);
  const [formData, setFormData] = useState<RepositoryFormData>({
    name: '',
    embedding_service_id: undefined,
  });

  const isNewRepository = repositoryId === '0';

  useEffect(() => {
    loadEmbeddingServices();
    if (!isNewRepository) {
      loadRepository();
    }
  }, [repositoryId]);

  const loadEmbeddingServices = async () => {
    try {
      const services = await apiService.getEmbeddingServices(parseInt(appId!));
      setEmbeddingServices(services);
    } catch (err) {
      console.error('Error loading embedding services:', err);
      setError('Failed to load embedding services');
    }
  };

  const loadRepository = async () => {
    try {
      setLoading(true);
      const repository = await apiService.getRepository(parseInt(appId!), parseInt(repositoryId!));
      setFormData({
        name: repository.name,
        embedding_service_id: repository.embedding_service_id,
      });
    } catch (err) {
      console.error('Error loading repository:', err);
      setError('Failed to load repository');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!formData.name.trim()) {
      setError('Repository name is required');
      return;
    }

    if (isNewRepository && !formData.embedding_service_id) {
      setError('Embedding service is required for new repositories');
      return;
    }

    try {
      setSaving(true);
      setError(null);

      if (isNewRepository) {
        await apiService.createRepository(parseInt(appId!), { 
          name: formData.name,
          embedding_service_id: formData.embedding_service_id
        });
      } else {
        await apiService.updateRepository(parseInt(appId!), parseInt(repositoryId!), { 
          name: formData.name,
          embedding_service_id: formData.embedding_service_id
        });
      }

      navigate(`/apps/${appId}/repositories`);
    } catch (err) {
      console.error('Error saving repository:', err);
      setError('Failed to save repository');
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    navigate(`/apps/${appId}/repositories`);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">
          {isNewRepository ? 'Create Repository' : 'Edit Repository'}
        </h1>
        <p className="text-gray-600 mt-2">
          {isNewRepository 
            ? 'Create a new repository to organize your documents. A silo will be automatically created for vector search.' 
            : 'Update repository settings and configuration'
          }
        </p>
      </div>

      {/* Error Message */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-6">
          {error}
        </div>
      )}

      {/* Form */}
      <div className="bg-white border border-gray-200 rounded-lg p-6 max-w-2xl">
        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Repository Name */}
          <div>
            <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-2">
              Repository Name
            </label>
            <input
              type="text"
              id="name"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              placeholder="Enter repository name"
              required
            />
            <p className="text-sm text-gray-500 mt-1">
              Choose a descriptive name for your repository
            </p>
          </div>

          {/* Embedding Service (only for new repositories) */}
          {isNewRepository && (
            <div>
              <label htmlFor="embedding_service_id" className="block text-sm font-medium text-gray-700 mb-2">
                Embedding Service <span className="text-red-500">*</span>
              </label>
              <select
                id="embedding_service_id"
                value={formData.embedding_service_id || ''}
                onChange={(e) => setFormData({ 
                  ...formData, 
                  embedding_service_id: e.target.value ? parseInt(e.target.value) : undefined 
                })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                required
              >
                <option value="">Select an embedding service</option>
                {embeddingServices.map((service) => (
                  <option key={service.service_id} value={service.service_id}>
                    {service.name} ({service.provider} - {service.model_name})
                  </option>
                ))}
              </select>
              <p className="text-sm text-gray-500 mt-1">
                This embedding service will be used for the silo that's automatically created with this repository
              </p>
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex justify-end gap-3 pt-6 border-t border-gray-200">
            <button
              type="button"
              onClick={handleCancel}
              className="px-4 py-2 text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {saving && (
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
              )}
              {isNewRepository ? 'Create Repository' : 'Save Changes'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default RepositoryFormPage; 