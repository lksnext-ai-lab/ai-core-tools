import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { apiService } from '../services/api';
import { useApiMutation } from '../hooks/useApiMutation';
import { MESSAGES, errorMessage } from '../constants/messages';
import Title from '../components/ui/Title';
import { FormField, FormSelect, FormTextArea } from '../components/ui/FormField';
import { ButtonApp } from '../components/ui/ButtonApp';
import Alert from '../components/ui/Alert';
import { LoadingState } from '../components/ui/LoadingState';

interface EmbeddingService {
  service_id: number;
  name: string;
  is_system?: boolean;
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
  const mutate = useApiMutation();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
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
    void loadDomainData();
  }, [appId, domainId]);

  async function loadDomainData() {
    if (!appId) return;

    try {
      setLoading(true);
      setLoadError(null);

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
      setLoadError(errorMessage(err, MESSAGES.LOAD_FAILED('domain')));
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    if (!appId) return;

    const numericAppId = Number.parseInt(appId, 10);
    const domainIdNum = isNewDomain ? 0 : Number.parseInt(domainId ?? '0', 10);

    setSaving(true);
    const result = await mutate(
      () => {
        if (isNewDomain) {
          return apiService.createDomain(numericAppId, formData);
        }
        const { vector_db_type: _vdb, embedding_service_id: _esi, ...updatePayload } = formData;
        return apiService.updateDomain(numericAppId, domainIdNum, updatePayload);
      },
      {
        loading: isNewDomain ? MESSAGES.CREATING('domain') : MESSAGES.UPDATING('domain'),
        success: isNewDomain ? MESSAGES.CREATED('domain') : MESSAGES.UPDATED('domain'),
        error: (err) => errorMessage(err, MESSAGES.SAVE_FAILED('domain')),
      },
    );
    setSaving(false);

    if (result !== undefined) {
      navigate(`/apps/${appId}/domains`);
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
      <LoadingState variant="page" message="Loading domain..." />
    );
  }

  if (loadError) {
    return (
      <div className="p-6">
        <Title variant="titPrincipal" titulo={isNewDomain ? 'Create Domain' : 'Edit Domain'} />
        
        <Alert
          type="error"
          title="Error"
          message={(
            <>
              {loadError}
              <br />
              <button
                type="button"
                onClick={loadDomainData}
                className="mt-4 bg-red-100 px-2 py-1 rounded-md text-red-800 hover:bg-red-200"
              >
                Try Again
              </button>
            </>
          )}
        />
      </div>
    );
  }

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="mb-6">
        <Title variant="titPrincipal" titulo={isNewDomain ? 'Create Domain' : 'Edit Domain'} />
      </div>

      <form onSubmit={handleSubmit} className="space-y-6 ">
        {/* Basic Information */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <FormField
            label="Domain Name"
            id="domain-name"
            type="text"
            value={formData.name}
            onChange={(e) => handleInputChange('name', e.target.value)}
            placeholder="My Website"
            required
          />

          <FormField
            label="Base URL"
            id="base-url"
            type="url"
            value={formData.base_url}
            onChange={(e) => handleInputChange('base_url', e.target.value)}
            placeholder="https://example.com"
            required
          />
        </div>

        <FormTextArea
          label="Description"
          id="description"
          value={formData.description}
          onChange={(e) => handleInputChange('description', e.target.value)}
          rows={3}
          placeholder="Description of this domain..."
        />

        {/* Embedding Service Selection */}
        <div>
          <FormSelect
            label="Embedding Service"
            id="embedding-service"
            value={formData.embedding_service_id || ''}
            onChange={(e) => {
              const value = e.target.value;
              handleInputChange('embedding_service_id', value ? Number.parseInt(value, 10) : undefined);
            }}
            required={isNewDomain}
            disabled={!isNewDomain}
            options={[
              { value: '', label: 'Select an embedding service' },
              ...embeddingServices.map((service) => ({
                value: service.service_id,
                label: service.is_system ? `[System] ${service.name}` : service.name,
              })),
            ]}
          />
          {embeddingServices.length === 0 && (
            <p className="text-sm text-error dark:text-error-dark mt-1">
              No embedding services available. Please create one first.
            </p>
          )}
          {!isNewDomain && (
            <p className="text-sm text-accent dark:text-accent-dark mt-1">
              The embedding service cannot be changed after a domain is created.
            </p>
          )}
        </div>

        {/* Vector Database Selection */}
        <div>
          <FormSelect
            label="Vector Database"
            id="domain-vector-db"
            value={vectorDbSelectValue}
            onChange={(e) => handleInputChange('vector_db_type', e.target.value)}
            required={isNewDomain}
            disabled={vectorDbOptions.length === 0 || !isNewDomain}
            options={vectorDbOptions.map((option) => ({ value: option.code, label: option.label }))}
          />
          {vectorDbOptions.length === 0 && isNewDomain && (
            <p className="text-sm text-accent dark:text-accent-dark mt-1">
              No vector databases available. Please configure a silo with vector support first.
            </p>
          )}
          {!isNewDomain && (
            <p className="text-sm text-accent dark:text-accent-dark mt-1">
              The vector database cannot be changed after a domain is created.
            </p>
          )}
        </div>

        {/* Content Extraction Configuration */}
        <div className="border-t pt-6">
          <h3 className="text-lg font-medium text-gray-900 mb-4">Content Extraction Settings</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <FormField
              label="Content Tag"
              id="content-tag"
              type="text"
              value={formData.content_tag}
              onChange={(e) => handleInputChange('content_tag', e.target.value)}
              placeholder="body"
              helpText="HTML tag to extract content from (default: body)"
            />

            <FormField
              label="Content Class"
              id="content-class"
              type="text"
              value={formData.content_class}
              onChange={(e) => handleInputChange('content_class', e.target.value)}
              placeholder="main-content"
              helpText="CSS class to filter content (optional)"
            />

            <FormField
              label="Content ID"
              id="content-id"
              type="text"
              value={formData.content_id}
              onChange={(e) => handleInputChange('content_id', e.target.value)}
              placeholder="content"
              helpText="HTML ID to filter content (optional)"
            />
          </div>
        </div>

        {/* Form Actions */}
        <div className="flex justify-end space-x-4 pt-6 border-t">
          <ButtonApp
            type="button"
            onClick={() => navigate(`/apps/${appId}/domains`)}
            label="Cancel"
            variant="secondary"
            size="medium"
            disabled={saving}
          />
          <ButtonApp
            type="submit"
            label={submitButtonLabel}
            variant="primary"
            size="medium"
            disabled={saving || embeddingServices.length === 0 || vectorDbOptions.length === 0}
          />
        </div>
      </form>
    </div>
  );
}

export default DomainFormPage; 