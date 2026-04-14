import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { apiService } from '../services/api';

interface RepositoryFormData {
  name: string;
  embedding_service_id?: number;
  vector_db_type: string;
  transcription_service_id?: number;
  video_ai_service_id?: number;
}

interface EmbeddingService {
  service_id: number;
  name: string;
  provider?: string;
  model_name?: string;
  is_system?: boolean;
}

interface VectorDbOption {
  code: string;
  label: string;
}

interface AIService {
  service_id: number;
  name: string;
  supports_video?: boolean;
}

const RepositoryFormPage: React.FC = () => {
  const { appId, repositoryId } = useParams<{ appId: string; repositoryId: string }>();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [embeddingServices, setEmbeddingServices] = useState<EmbeddingService[]>([]);
  const [aiServices, setAiServices] = useState<AIService[]>([]);
  const [vectorDbOptions, setVectorDbOptions] = useState<VectorDbOption[]>([]);
  const [formData, setFormData] = useState<RepositoryFormData>({
    name: '',
    embedding_service_id: undefined,
    vector_db_type: 'PGVECTOR',
    transcription_service_id: undefined,
    video_ai_service_id: undefined,
  });

  const isNewRepository = repositoryId === '0';

  useEffect(() => {
    if (!appId || repositoryId === undefined) {
      return;
    }

    const appIdNumber = Number.parseInt(appId, 10);
    const repositoryIdNumber = Number.parseInt(repositoryId, 10);

    if (Number.isNaN(appIdNumber) || Number.isNaN(repositoryIdNumber)) {
      return;
    }

    const fetchRepository = async () => {
      try {
        setLoading(true);
        setError(null);

        const repository = await apiService.getRepository(appIdNumber, repositoryIdNumber);
        const embeddingServiceList: EmbeddingService[] = repository.embedding_services ?? [];
        const availableVectorDbOptions: VectorDbOption[] = repository.vector_db_options ?? [];

        let servicesToUse = embeddingServiceList;
        if (servicesToUse.length === 0) {
          try {
            servicesToUse = await apiService.getEmbeddingServices(appIdNumber);
          } catch (serviceErr) {
            console.error('Error loading embedding services:', serviceErr);
          }
        }

        setEmbeddingServices(servicesToUse);
        setVectorDbOptions(availableVectorDbOptions);
        setAiServices(repository.ai_services ?? []);

        const normalizedVectorDbType = (repository.vector_db_type || 'PGVECTOR').toUpperCase();
        const resolvedVectorDbType = availableVectorDbOptions.some((option) => option.code === normalizedVectorDbType)
          ? normalizedVectorDbType
          : (availableVectorDbOptions[0]?.code || 'PGVECTOR');

        const nextEmbeddingServiceId = repository.embedding_service_id
          ?? (isNewRepository && servicesToUse.length === 1 ? servicesToUse[0].service_id : undefined);

        setFormData({
          name: repository.name ?? '',
          embedding_service_id: nextEmbeddingServiceId,
          vector_db_type: resolvedVectorDbType,
          transcription_service_id: repository.transcription_service_id ?? undefined,
          video_ai_service_id: repository.video_ai_service_id ?? undefined,
        });
      } catch (err) {
        console.error('Error loading repository:', err);
        setError('Failed to load repository');
      } finally {
        setLoading(false);
      }
    };

    void fetchRepository();
  }, [appId, repositoryId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!appId) {
      setError('Invalid application context');
      return;
    }

    const appIdNumber = Number.parseInt(appId, 10);
    if (Number.isNaN(appIdNumber)) {
      setError('Invalid application context');
      return;
    }

    const trimmedName = formData.name.trim();
    if (!trimmedName) {
      setError('Repository name is required');
      return;
    }

    if (!formData.vector_db_type) {
      setError('Vector database selection is required');
      return;
    }

    if (isNewRepository && !formData.embedding_service_id) {
      setError('Embedding service is required for new repositories');
      return;
    }

    const normalizedVectorDbType = formData.vector_db_type.toUpperCase();
    const repositoryIdNumber = repositoryId ? Number.parseInt(repositoryId, 10) : 0;
    if (!isNewRepository && Number.isNaN(repositoryIdNumber)) {
      setError('Invalid repository context');
      return;
    }

    try {
      setSaving(true);
      setError(null);

      if (isNewRepository) {
        await apiService.createRepository(appIdNumber, { 
          name: trimmedName,
          embedding_service_id: formData.embedding_service_id,
          vector_db_type: normalizedVectorDbType,
          transcription_service_id: formData.transcription_service_id,
          video_ai_service_id: formData.video_ai_service_id,
        });
      } else {
        await apiService.updateRepository(appIdNumber, repositoryIdNumber, { 
          name: trimmedName,
          embedding_service_id: formData.embedding_service_id,
          vector_db_type: normalizedVectorDbType,
          transcription_service_id: formData.transcription_service_id,
          video_ai_service_id: formData.video_ai_service_id,
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

          {/* Vector Database */}
          <div>
            <label htmlFor="vector_db_type" className="block text-sm font-medium text-gray-700 mb-2">
              Vector Database <span className="text-red-500">*</span>
            </label>
            <select
              id="vector_db_type"
              value={formData.vector_db_type}
              onChange={(e) =>
                setFormData({
                  ...formData,
                  vector_db_type: e.target.value.toUpperCase(),
                })
              }
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              required
            >
              {vectorDbOptions.length === 0
                ? (
                  <option value={formData.vector_db_type}>{formData.vector_db_type}</option>
                ) : (
                  vectorDbOptions.map((option) => (
                    <option key={option.code} value={option.code}>
                      {option.label}
                    </option>
                  ))
                )}
            </select>
            <p className="text-sm text-gray-500 mt-1">
              Select where embeddings for this repository will be stored.
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
                  embedding_service_id: e.target.value ? Number.parseInt(e.target.value, 10) : undefined 
                })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                required
              >
                <option value="">Select an embedding service</option>
                {embeddingServices.map((service) => (
                  <option key={service.service_id} value={service.service_id}>
                    {service.is_system ? '[System] ' : ''}{service.provider && service.model_name
                      ? `${service.name} (${service.provider} - ${service.model_name})`
                      : service.name}
                  </option>
                ))}
              </select>
              <p className="text-sm text-gray-500 mt-1">
                This embedding service will be used for the silo that's automatically created with this repository
              </p>
            </div>
          )}

          {/* Transcription Service */}
          {aiServices.length > 0 && (
            <div>
              <label htmlFor="transcription_service_id" className="block text-sm font-medium text-gray-700 mb-2">
                Transcription Service (Whisper)
              </label>
              <select
                id="transcription_service_id"
                value={formData.transcription_service_id || ''}
                onChange={(e) => setFormData({
                  ...formData,
                  transcription_service_id: e.target.value ? parseInt(e.target.value, 10) : undefined,
                })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="">None (select per upload)</option>
                {aiServices.map((service) => (
                  <option key={service.service_id} value={service.service_id}>
                    {service.name}
                  </option>
                ))}
              </select>
              <p className="text-sm text-gray-500 mt-1">
                Default transcription service for all media in this repository. Can be overridden per upload.
              </p>
            </div>
          )}

          {/* Video AI Service */}
          {aiServices.filter(s => s.supports_video).length > 0 && (
            <div>
              <label htmlFor="video_ai_service_id" className="block text-sm font-medium text-gray-700 mb-2">
                Video Analysis Service (Gemini)
              </label>
              <select
                id="video_ai_service_id"
                value={formData.video_ai_service_id || ''}
                onChange={(e) => setFormData({
                  ...formData,
                  video_ai_service_id: e.target.value ? parseInt(e.target.value, 10) : undefined,
                })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="">None (no visual analysis)</option>
                {aiServices.filter(s => s.supports_video).map((service) => (
                  <option key={service.service_id} value={service.service_id}>
                    {service.name}
                  </option>
                ))}
              </select>
              <p className="text-sm text-gray-500 mt-1">
                When set, media uploaded in multimodal mode will use this service for visual frame analysis.
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