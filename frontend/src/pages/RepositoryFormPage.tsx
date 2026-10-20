import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { apiService } from '../services/api';
import { useApiMutation } from '../hooks/useApiMutation';
import { MESSAGES, errorMessage } from '../constants/messages';
import Title from '../components/ui/Title';
import Alert from '../components/ui/Alert';
import { FormField, FormSelect } from '../components/ui/FormField';
import { FormActions } from '../components/ui/FormActions';
import { LoadingState } from '../components/ui/LoadingState';
import { ServiceOptionStatus, serviceStatusId } from '../components/ui/ServiceOptionStatus';
import { selectableServiceOptions, serviceOptionLabel, type ServiceOptionLike } from '../utils/serviceLifecycle';
import { MediaServicesFields } from '../components/forms/MediaServicesFields';

interface RepositoryFormData {
  name: string;
  embedding_service_id?: number;
  vector_db_type: string;
  transcription_service_id?: number;
  video_ai_service_id?: number;
}

interface EmbeddingService extends ServiceOptionLike {
  provider?: string;
  model_name?: string;
  is_system?: boolean;
}

interface VectorDbOption {
  code: string;
  label: string;
}

interface AIService extends ServiceOptionLike {
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
  // Values saved on the loaded repository (D-4): the only retired services that stay selectable.
  const [savedMedia, setSavedMedia] = useState<{ transcription?: number | null; video?: number | null }>({});
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
        setSavedMedia({ transcription: repository.transcription_service_id, video: repository.video_ai_service_id });

        const normalizedVectorDbType = (repository.vector_db_type || 'PGVECTOR').toUpperCase();
        const resolvedVectorDbType = availableVectorDbOptions.some((option) => option.code === normalizedVectorDbType)
          ? normalizedVectorDbType
          : (availableVectorDbOptions[0]?.code || 'PGVECTOR');

        const nextEmbeddingServiceId = repository.embedding_service_id
          ?? (isNewRepository && servicesToUse.length === 1 && servicesToUse[0].lifecycle_status !== 'retired'
            ? servicesToUse[0].service_id
            : undefined);

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
    <div className="mx-auto max-w-4xl space-y-6">
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
            className={!isNewRepository ? '[&>p]:text-accent dark:text-accent-dark' : ''}
            helpText={isNewRepository
              ? 'Select where embeddings for this repository will be stored.'
              : 'The vector database cannot be changed after a repository is created.'}
          />

          {/* Embedding Service (only for new repositories) */}
          {isNewRepository && (
            <div>
              <FormSelect
                label="Embedding Service"
                id="embedding_service_id"
                value={formData.embedding_service_id || ''}
                onChange={(e) => setFormData({ 
                  ...formData, 
                  embedding_service_id: e.target.value ? Number.parseInt(e.target.value, 10) : undefined 
                })}
                required
                options={[
                  { value: '', label: 'Select an embedding service' },
                  ...selectableServiceOptions(embeddingServices, undefined).map((service) => ({
                    value: service.service_id,
                    label: serviceOptionLabel(service, [
                      service.is_system ? '[System]' : '',
                      service.provider && service.model_name
                        ? `${service.name} (${service.provider} - ${service.model_name})`
                        : service.name,
                    ].filter(Boolean).join(' ')),
                  })),
                ]}
                ariaDescribedBy={serviceStatusId(embeddingServices, formData.embedding_service_id, 'embedding_service_id')}
              />
              <ServiceOptionStatus selectId="embedding_service_id" options={embeddingServices} selectedId={formData.embedding_service_id} />
              <p className="mt-1 text-xs text-fg-tertiary dark:text-fg-tertiary-dark">
                This embedding service will be used for the silo that's automatically created with this repository
              </p>
            </div>
          )}

          <MediaServicesFields
            scope="repository"
            aiServices={aiServices}
            transcriptionServiceId={formData.transcription_service_id}
            videoServiceId={formData.video_ai_service_id}
            savedTranscriptionServiceId={savedMedia.transcription}
            savedVideoServiceId={savedMedia.video}
            onChange={(field, value) => setFormData({ ...formData, [field]: value ?? undefined })}
          />

          {/* Action Buttons */}
          <FormActions
            onCancel={handleCancel}
            isSubmitting={saving}
            submitLabel={isNewRepository ? 'Create Repository' : 'Save Changes'}
            containerClassName="pt-6"
          />
        </form>
      </div>
    </div>
  );
};

export default RepositoryFormPage;