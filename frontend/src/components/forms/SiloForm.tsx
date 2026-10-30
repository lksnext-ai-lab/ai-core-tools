import Alert from '../ui/Alert';
import { FormActions } from '../ui/FormActions';
import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Info } from 'lucide-react';
import { apiService } from '../../services/api';
import { ServiceOptionStatus, serviceStatusId } from '../ui/ServiceOptionStatus';
import { selectableServiceOptions, serviceOptionLabel, type ServiceOptionLike } from '../../utils/serviceLifecycle';
import { MediaServicesFields, type MediaAIServiceOption } from './MediaServicesFields';
import { FormField, FormSelect } from '../ui/FormField';

interface VectorDbOption {
  code: string;
  label: string;
}

// Define the Silo type for form data
interface Silo {
  silo_id: number;
  name: string;
  description?: string;
  type?: string;
  created_at?: string;
  docs_count: number;
  vector_db_type?: string;
  metadata_definition_id?: number;
  embedding_service_id?: number;
  output_parsers?: { parser_id: number; name: string }[];
  embedding_services?: (ServiceOptionLike & { provider?: string; is_system?: boolean })[];
  vector_db_options?: VectorDbOption[];
  transcription_service_id?: number | null;
  video_ai_service_id?: number | null;
  ai_services?: MediaAIServiceOption[];
}

// Define the form data type
interface SiloFormData {
  name: string;
  description?: string;
  type?: string;
  output_parser_id?: number;
  embedding_service_id?: number;
  vector_db_type?: string;
  // null clears the service; the backend keeps a field only when it is omitted
  transcription_service_id?: number | null;
  video_ai_service_id?: number | null;
}

// Define the props for the component
interface SiloFormProps {
  silo?: Silo;
  onSubmit: (data: SiloFormData) => Promise<void>;
  onCancel: () => void;
}

function SiloForm({ silo, onSubmit, onCancel}: Readonly<SiloFormProps>) {
  const { t } = useTranslation('common');
  const { appId } = useParams();
  const [formData, setFormData] = useState<SiloFormData>({
    name: '',
    description: '',
    type: 'CUSTOM', // Always CUSTOM for this interface
    output_parser_id: undefined,
    embedding_service_id: undefined,
    vector_db_type: 'PGVECTOR'
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [outputParsers, setOutputParsers] = useState<any[]>([]);
  const [embeddingServices, setEmbeddingServices] = useState<(ServiceOptionLike & { provider?: string; is_system?: boolean })[]>([]);
  const [vectorDbOptions, setVectorDbOptions] = useState<VectorDbOption[]>([]);
  
  const isEditing = !!silo && silo.silo_id !== 0;
  let submitButtonLabel = isEditing ? t('siloFormPage.actions.update') : t('siloFormPage.actions.create');
  if (isSubmitting) {
    submitButtonLabel = t('siloFormPage.actions.saving');
  }

  // Load form data (output parsers and embedding services)
  useEffect(() => {
    void loadFormData();
  }, [appId]);

  // Initialize form with existing silo data
  useEffect(() => {
    const defaultVectorType = (silo?.vector_db_type || 'PGVECTOR').toUpperCase();
    const availableVectorDbOptions = silo?.vector_db_options ?? [];
    const matchedVectorDbOption = availableVectorDbOptions.find(
      (option) => option.code.toUpperCase() === defaultVectorType
    );
    const vectorDbTypeValue = matchedVectorDbOption?.code
      || availableVectorDbOptions[0]?.code
      || defaultVectorType
      || 'PGVECTOR';

    setVectorDbOptions(availableVectorDbOptions);

    setFormData(prev => ({
      ...prev,
      name: silo?.name || '',
      description: silo?.description || '',
      type: 'CUSTOM',
      output_parser_id: silo?.metadata_definition_id || undefined,
      embedding_service_id: silo?.embedding_service_id || undefined,
      vector_db_type: vectorDbTypeValue,
      transcription_service_id: silo?.transcription_service_id ?? null,
      video_ai_service_id: silo?.video_ai_service_id ?? null,
    }));
  }, [silo]);

  async function loadFormData() {
    if (!appId) return;
    
    try {
      setError(null);
      
      const appIdNumber = Number.parseInt(appId, 10);

      // Load output parsers and embedding services in parallel
      const [parsersResponse, servicesResponse] = await Promise.all([
        apiService.getOutputParsers(appIdNumber),
        apiService.getEmbeddingServices(appIdNumber)
      ]);

      setOutputParsers(parsersResponse);
      setEmbeddingServices(servicesResponse);

      // Fetch vector database options only when they have not been set
      if (vectorDbOptions.length === 0) {
        const siloOptions = await apiService.getSiloOptions(appIdNumber);
        const availableVectorDbOptions: VectorDbOption[] = siloOptions.vector_db_options ?? [];
        setVectorDbOptions(availableVectorDbOptions);
        // Do NOT set vector_db_type here — let the silo initialization effect handle it
      }

      // Default embedding service for new silo when only one available
      if (!isEditing && servicesResponse.length === 1) {
        setFormData(prev => ({
          ...prev,
          embedding_service_id: servicesResponse[0].service_id
        }));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t('siloFormPage.loadFormFailed'));
      console.error('Error loading form data:', err);
    } 
  }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;

    let parsedValue: string | number | undefined = value === '' ? undefined : value;

    if (name === 'embedding_service_id' || name === 'output_parser_id') {
      parsedValue = value === '' ? undefined : Number.parseInt(value, 10);
    } else if (name === 'vector_db_type' && typeof value === 'string') {
      parsedValue = value.toUpperCase();
    }

    setFormData(prev => ({
      ...prev,
      [name]: parsedValue
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    // Basic validation
    if (!formData.name.trim()) {
      setError(t('siloFormPage.validation.nameRequired'));
      return;
    }

    if (!isEditing && !formData.vector_db_type) {
      setError(t('siloFormPage.validation.vectorDbRequired'));
      return;
    }

    try {
      setIsSubmitting(true);
      setError(null);
      const payload = isEditing
        ? (({ vector_db_type: _vdb, embedding_service_id: _esi, ...rest }) => rest)(formData)
        : { ...formData, vector_db_type: formData.vector_db_type!.toUpperCase() };
      await onSubmit(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('siloFormPage.saveFailed'));
    } finally {
      setIsSubmitting(false);
    }
  };

  
  return (
    <div>
      {/* Form */}
      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="">
          <div className="grid grid-cols-1 gap-6">
            {/* Silo Name */}
            <FormField
              label={t('siloFormPage.fields.name')}
              id="name"
              value={formData.name}
              onChange={handleChange}
              required
              placeholder={t('siloFormPage.fields.namePlaceholder')}
              disabled={isSubmitting}
            />
            <FormField
              label={t('siloFormPage.fields.description')}
              id="description"
              value={formData.description || ''}
              onChange={handleChange}
              required
              placeholder={t('siloFormPage.fields.descriptionPlaceholder')}
              disabled={isSubmitting}
            />
            {/* Metadata Definition (Output Parser) */}
            <div>
              <FormSelect
                label={t('siloFormPage.fields.metadataDefinition')}
                id="output_parser_id"
                value={formData.output_parser_id?.toString() || ''}
                onChange={handleChange}
                options={[
                  { value: '', label: t('siloFormPage.fields.noMetadataDefinition') },
                  ...outputParsers.map((parser) => ({
                    value: parser.parser_id,
                    label: parser.name,
                  })),
                ]}
                disabled={isSubmitting}
                helpText={t('siloFormPage.help.metadataDefinition')}
              />
            </div>

            {/* Embedding Service */}
            <div>
              <FormSelect
                label={t('siloFormPage.fields.embeddingService')}
                id="embedding_service_id"
                value={formData.embedding_service_id?.toString() || ''}
                onChange={handleChange}
                required
                options={[
                  { value: '', label: t('siloFormPage.fields.selectEmbeddingService') },
                  ...selectableServiceOptions(embeddingServices, silo?.embedding_service_id).map((service) => ({
                    value: service.service_id,
                    label: serviceOptionLabel(service, [
                      service.is_system ? `[${t('siloFormPage.system')}]` : '',
                      service.name,
                      service.provider ? `(${service.provider})` : '',
                    ].filter(Boolean).join(' ')),
                  })),
                ]}
                disabled={isSubmitting || isEditing}
                ariaDescribedBy={serviceStatusId(embeddingServices, formData.embedding_service_id, 'embedding_service_id')}
              />
              <ServiceOptionStatus selectId="embedding_service_id" options={embeddingServices} selectedId={formData.embedding_service_id} />
              {isEditing ? (
                <p className="mt-1 text-xs text-accent dark:text-accent-dark">
                  {t('siloFormPage.help.embeddingServiceImmutable')}
                </p>
              ) : (
                <p className="mt-1 text-xs text-fg-tertiary dark:text-fg-tertiary-dark">
                  {t('siloFormPage.help.embeddingServiceRequired')}
                </p>
              )}
            </div>

            {/* Vector Database */}
            <div>
              <FormSelect
                label={t('siloFormPage.fields.vectorDatabase')}
                id="vector_db_type"
                value={vectorDbOptions.length === 0 ? '' : formData.vector_db_type ?? ''}
                onChange={handleChange}
                required={!isEditing}
                options={[
                  ...(vectorDbOptions.length === 0
                    ? [{ value: '', label: t('siloFormPage.fields.noVectorDatabases') }]
                    : []),
                  ...vectorDbOptions.map((option) => ({
                    value: option.code,
                    label: option.label,
                  })),
                ]}
                disabled={isSubmitting || vectorDbOptions.length === 0 || isEditing}
                helpText={isEditing ? (
                  <span className="flex items-center gap-1 ">
                    <Info className="w-3.5 h-3.5 shrink-0" />
                    {t('siloFormPage.help.vectorDatabaseImmutable')}
                  </span>
                ) : vectorDbOptions.length === 0 ? (
                  <span className="text-error dark:text-error-dark">
                    {t('siloFormPage.help.configureVectorDatabase')}
                  </span>
                ) : (
                  t('siloFormPage.help.vectorDatabaseRequired')
                )}
              />
            </div>
          </div>

          {/* Media (video/audio) indexing */}
          {(silo?.ai_services?.length ?? 0) > 0 && (
            <fieldset className="space-y-4 border-t border-gray-200 pt-6 mt-5">
              <legend className="block text-sm font-medium text-fg dark:text-fg-dark mb-1">{t('siloFormPage.media.title')}</legend>
              <MediaServicesFields
                scope="silo"
                aiServices={silo?.ai_services ?? []}
                transcriptionServiceId={formData.transcription_service_id}
                videoServiceId={formData.video_ai_service_id}
                savedTranscriptionServiceId={silo?.transcription_service_id}
                savedVideoServiceId={silo?.video_ai_service_id}
                disabled={isSubmitting}
                onChange={(field, value) => setFormData(prev => ({ ...prev, [field]: value }))}
              />
            </fieldset>
          )}

          {/* Error Message */}
          {error && (
            <Alert type="error" message={error} />
          )}

          {/* Action Buttons */}
          <FormActions
            onCancel={onCancel}
            isSubmitting={isSubmitting}
            submitLabel={submitButtonLabel}
            submittingLabel={t('siloFormPage.actions.saving')}
            cancelLabel={t('siloFormPage.actions.cancel')}
            containerClassName="mt-6"
          />
        </div>
      </form>

      {/* Info Section */}
      <Alert
        type="info"
        title={t('siloFormPage.about.title')}
        className="mt-8"
        message={(
          <>
            <p>
              {t('siloFormPage.about.description')}
            </p>
            <p className="mt-2">
              <span className="font-medium">{t('siloFormPage.fields.embeddingService')}:</span> {t('siloFormPage.about.embeddingService')}
              <br />
              <span className="font-medium">{t('siloFormPage.fields.metadataDefinition')}:</span> {t('siloFormPage.about.metadataDefinition')}
            </p>
          </>
        )}
      />
    </div>
  );
}

export default SiloForm; 