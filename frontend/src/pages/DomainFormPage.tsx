import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { apiService } from '../services/api';
import { useApiMutation } from '../hooks/useApiMutation';
import { errorMessage } from '../constants/messages';
import Title from '../components/ui/Title';
import { FormField, FormSelect, FormTextArea } from '../components/ui/FormField';
import { FormActions } from '../components/ui/FormActions';
import Alert from '../components/ui/Alert';
import { LoadingState } from '../components/ui/LoadingState';
import { ServiceOptionStatus, serviceStatusId } from '../components/ui/ServiceOptionStatus';
import { selectableServiceOptions, serviceOptionLabel, type ServiceOptionLike } from '../utils/serviceLifecycle';
import CardApp from '../components/ui/CardApp';

interface EmbeddingService extends ServiceOptionLike {
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
  const { t } = useTranslation('common');
  const mutate = useApiMutation();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [embeddingServices, setEmbeddingServices] = useState<EmbeddingService[]>([]);
  const [savedEmbeddingServiceId, setSavedEmbeddingServiceId] = useState<number | undefined>(undefined);
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
  let submitButtonLabelKey = 'domainFormPage.actions.update';
  if (saving) {
    submitButtonLabelKey = 'domainFormPage.actions.saving';
  } else if (isNewDomain) {
    submitButtonLabelKey = 'domainFormPage.actions.create';
  }
  const submitButtonLabel = t(submitButtonLabelKey);
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
      setSavedEmbeddingServiceId(domain.embedding_service_id || undefined);
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
      setLoadError(errorMessage(err, t('domainFormPage.loadFailed')));
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
        loading: t(isNewDomain ? 'domainFormPage.notifications.creating' : 'domainFormPage.notifications.updating'),
        success: t(isNewDomain ? 'domainFormPage.notifications.created' : 'domainFormPage.notifications.updated'),
        error: (err) => errorMessage(err, t('domainFormPage.notifications.saveFailed')),
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
  <LoadingState variant="page" message={t('domainFormPage.loading')} />
    );
  }

  if (loadError) {
    return (
      <div className="p-6">
        <Title variant="titPrincipal" titulo={t(isNewDomain ? 'domainFormPage.createTitle' : 'domainFormPage.editTitle')} />
        
        <Alert
          type="error"
          title={t('domainFormPage.errorTitle')}
          message={(
            <>
              {loadError}
              <br />
              <button
                type="button"
                onClick={loadDomainData}
                className="mt-4 bg-red-100 px-2 py-1 rounded-md text-red-800 hover:bg-red-200"
              >
                {t('domainFormPage.tryAgain')}
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
        <Title variant="titPrincipal" titulo={t(isNewDomain ? 'domainFormPage.createTitle' : 'domainFormPage.editTitle')} />
      </div>

      <form onSubmit={handleSubmit} className="space-y-6 ">
        {/* Basic Information */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <FormField
            label={t('domainFormPage.fields.name')}
            id="domain-name"
            type="text"
            value={formData.name}
            onChange={(e) => handleInputChange('name', e.target.value)}
            placeholder={t('domainFormPage.fields.namePlaceholder')}
            required
          />

          <FormField
            label={t('domainFormPage.fields.baseUrl')}
            id="base-url"
            type="url"
            value={formData.base_url}
            onChange={(e) => handleInputChange('base_url', e.target.value)}
            placeholder={t('domainFormPage.fields.baseUrlPlaceholder')}
            required
          />
        </div>

        <FormTextArea
          label={t('domainFormPage.fields.description')}
          id="description"
          value={formData.description}
          onChange={(e) => handleInputChange('description', e.target.value)}
          rows={3}
          placeholder={t('domainFormPage.fields.descriptionPlaceholder')}
        />

        {/* Embedding Service Selection */}
        <div>
          <FormSelect
            label={t('domainFormPage.fields.embeddingService')}
            id="embedding-service"
            value={formData.embedding_service_id || ''}
            onChange={(e) => {
              const value = e.target.value;
              handleInputChange('embedding_service_id', value ? Number.parseInt(value, 10) : undefined);
            }}
            required={isNewDomain}
            disabled={!isNewDomain}
            options={[
              { value: '', label: t('domainFormPage.fields.selectEmbeddingService') },
              ...selectableServiceOptions(embeddingServices, savedEmbeddingServiceId).map((service) => {
                const systemPrefix = service.is_system ? `[${t('domainFormPage.system')}] ` : '';
                return {
                  value: service.service_id,
                  label: serviceOptionLabel(service, `${systemPrefix}${service.name}`),
                };
              }),
            ]}
            ariaDescribedBy={serviceStatusId(embeddingServices, formData.embedding_service_id, 'embedding-service')}
          />
          <ServiceOptionStatus
            options={embeddingServices}
            selectedId={formData.embedding_service_id}
            selectId="embedding-service"
          />
          {embeddingServices.length === 0 && (
            <p className="text-xs text-error dark:text-error-dark mt-1">
              {t('domainFormPage.messages.noEmbeddingServices')}
            </p>
          )}
          {!isNewDomain && (
            <p className="text-xs text-accent dark:text-accent-dark mt-1">
              {t('domainFormPage.messages.embeddingServiceLocked')}
            </p>
          )}
        </div>

        

        {/* Vector Database Selection */}
        <div>
          <FormSelect
            label={t('domainFormPage.fields.vectorDatabase')}
            id="domain-vector-db"
            value={vectorDbSelectValue}
            onChange={(e) => handleInputChange('vector_db_type', e.target.value)}
            required={isNewDomain}
            disabled={vectorDbOptions.length === 0 || !isNewDomain}
            options={vectorDbOptions.map((option) => ({ value: option.code, label: option.label }))}
          />
          {vectorDbOptions.length === 0 && isNewDomain && (
            <p className="text-xs text-accent dark:text-accent-dark mt-1">
              {t('domainFormPage.messages.noVectorDatabases')}
            </p>
          )}
          {!isNewDomain && (
            <p className="text-xs text-accent dark:text-accent-dark mt-1">
              {t('domainFormPage.messages.vectorDatabaseLocked')}
            </p>
          )}
        </div>

        {/* Content Extraction Configuration */}
        <CardApp titulo={t('domainFormPage.contentExtraction')} className="pt-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <FormField
              label={t('domainFormPage.fields.contentTag')}
              id="content-tag"
              type="text"
              value={formData.content_tag}
              onChange={(e) => handleInputChange('content_tag', e.target.value)}
              placeholder="body"
              helpText={t('domainFormPage.fields.contentTagHelp')}
            />

            <FormField
              label={t('domainFormPage.fields.contentClass')}
              id="content-class"
              type="text"
              value={formData.content_class}
              onChange={(e) => handleInputChange('content_class', e.target.value)}
              placeholder="main-content"
              helpText={t('domainFormPage.fields.contentClassHelp')}
            />

            <FormField
              label={t('domainFormPage.fields.contentId')}
              id="content-id"
              type="text"
              value={formData.content_id}
              onChange={(e) => handleInputChange('content_id', e.target.value)}
              placeholder="content"
              helpText={t('domainFormPage.fields.contentIdHelp')}
            />
          </div>
        </CardApp>

        {/* Form Actions */}
        <FormActions
          onCancel={() => navigate(`/apps/${appId}/domains`)}
          isSubmitting={saving}
          submitLabel={submitButtonLabel}
          submittingLabel={t('domainFormPage.actions.saving')}
          cancelLabel={t('domainFormPage.actions.cancel')}
          submitDisabled={embeddingServices.length === 0 || vectorDbOptions.length === 0}
          containerClassName="pt-6"
        />
      </form>
    </div>
  );
}

export default DomainFormPage; 