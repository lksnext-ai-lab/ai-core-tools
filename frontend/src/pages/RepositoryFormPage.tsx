import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { apiService } from '../services/api';
import { useApiMutation } from '../hooks/useApiMutation';
import { MESSAGES, errorMessage } from '../constants/messages';
import Title from '../components/ui/Title';
import Alert from '../components/ui/Alert';
import { FormField, FormSelect } from '../components/ui/FormField';
import ButtonApp from '../components/ui/ButtonApp';
import { LoadingState } from '../components/ui/LoadingState';

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
  const mutate = useApiMutation();
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

    if (isNewRepository && !formData.vector_db_type) {
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

    const payload = {
      name: trimmedName,
      embedding_service_id: formData.embedding_service_id,
      vector_db_type: normalizedVectorDbType,
      transcription_service_id: formData.transcription_service_id,
      video_ai_service_id: formData.video_ai_service_id,
    };

    setError(null);
    setSaving(true);
    const result = await mutate(
      () =>
        isNewRepository
          ? apiService.createRepository(appIdNumber, payload)
          : apiService.updateRepository(appIdNumber, repositoryIdNumber, payload),
      {
        loading: isNewRepository
          ? MESSAGES.CREATING('repository')
          : MESSAGES.UPDATING('repository'),
        success: isNewRepository
          ? MESSAGES.CREATED('repository')
          : MESSAGES.UPDATED('repository'),
        error: (err) => errorMessage(err, MESSAGES.SAVE_FAILED('repository')),
      },
    );
    setSaving(false);

    if (result !== undefined) {
      navigate(`/apps/${appId}/repositories`);
    }
  };

  const handleCancel = () => {
    navigate(`/apps/${appId}/repositories`);
  };

  if (loading) {
    return (
      <LoadingState variant="page" />
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}

      <Title variant="titPrincipal"
        titulo={isNewRepository ? 'Create Repository' : 'Edit Repository'}
        subtitulo={isNewRepository 
          ? 'Create a new repository to organize your documents. A silo will be automatically created for vector search.' 
          : 'Update repository settings and configuration'
        } 
      />

      {/* Error Message */}
      {error && (
        <Alert type="error" message={error} />
      )}

      {/* Form */}
      <div className="max-w-2xl">
        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Repository Name */}
          <FormField
            label="Repository Name"
            id="name"
            value={formData.name}
            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            placeholder="Enter repository name"
            required
            helpText="Choose a descriptive name for your repository"
          />

          {/* Vector Database */}
          <FormSelect
            label="Vector Database"
            id="vector_db_type"
            value={formData.vector_db_type}
            onChange={(e) =>
              setFormData({
                ...formData,
                vector_db_type: e.target.value.toUpperCase(),
              })
            }
            options={vectorDbOptions.length === 0
              ? [{ value: formData.vector_db_type, label: formData.vector_db_type }]
              : vectorDbOptions.map((option) => ({ value: option.code, label: option.label }))}
            required={isNewRepository}
            disabled={!isNewRepository}
            className={!isNewRepository ? '[&>p]:text-amber-600' : ''}
            helpText={isNewRepository
              ? 'Select where embeddings for this repository will be stored.'
              : 'The vector database cannot be changed after a repository is created.'}
          />

          {/* Embedding Service (only for new repositories) */}
          {isNewRepository && (
            <FormSelect
              label="Embedding Service"
              id="embedding_service_id"
              value={formData.embedding_service_id || ''}
              onChange={(e) => setFormData({ 
                ...formData, 
                embedding_service_id: e.target.value ? Number.parseInt(e.target.value, 10) : undefined 
              })}
              options={[
                { value: '', label: 'Select an embedding service' },
                ...embeddingServices.map((service) => ({
                  value: service.service_id,
                  label: `${service.is_system ? '[System] ' : ''}${service.provider && service.model_name
                    ? `${service.name} (${service.provider} - ${service.model_name})`
                    : service.name}`,
                })),
              ]}
              required
              helpText="This embedding service will be used for the silo that's automatically created with this repository"
            />
          )}

          {/* Transcription Service */}
          {aiServices.length > 0 && (
            <FormSelect
              label="Transcription Service (Whisper)"
              id="transcription_service_id"
              value={formData.transcription_service_id || ''}
              onChange={(e) => setFormData({
                ...formData,
                transcription_service_id: e.target.value ? parseInt(e.target.value, 10) : undefined,
              })}
              options={[
                { value: '', label: 'None (no transcription analysis) ' },
                ...aiServices.map((service) => ({ value: service.service_id, label: service.name })),
              ]}
              helpText="Transcription service used for all media uploads in this repository."
            />
          )}

          {/* Video AI Service */}
          {aiServices.filter(s => s.supports_video).length > 0 && (
            <FormSelect
              label="Video Analysis Service (Gemini)"
              id="video_ai_service_id"
              value={formData.video_ai_service_id || ''}
              onChange={(e) => setFormData({
                ...formData,
                video_ai_service_id: e.target.value ? parseInt(e.target.value, 10) : undefined,
              })}
              options={[
                { value: '', label: 'None (no visual analysis)' },
                ...aiServices.filter(s => s.supports_video).map((service) => ({
                  value: service.service_id,
                  label: service.name,
                })),
              ]}
              helpText="When set, media uploaded in multimodal mode will use this service for visual frame analysis."
            />
          )}

          {/* Action Buttons */}
          <div className="flex justify-end gap-3 pt-6">
            <ButtonApp
              label="Cancel"
              type="button"
              onClick={handleCancel}
              variant="secondary"
              size="medium"
            />
            <ButtonApp
              label={isNewRepository ? 'Create Repository' : 'Save Changes'}
              type="submit"
              disabled={saving}
              loading={saving}
              variant="primary"
              size="medium"
            />
          </div>
        </form>
      </div>
    </div>
  );
};

export default RepositoryFormPage;