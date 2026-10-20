import Alert from '../ui/Alert';
import { FormActions } from '../ui/FormActions';
import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { Info } from 'lucide-react';
import { apiService } from '../../services/api';
import { FormField, FormSelect } from '../ui/FormField';
import { LoadingState } from '../ui/LoadingState';

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
  embedding_services?: { service_id: number; name: string; provider?: string; is_system?: boolean }[];
  vector_db_options?: VectorDbOption[];
}

// Define the form data type
interface SiloFormData {
  name: string;
  description?: string;
  type?: string;
  output_parser_id?: number;
  embedding_service_id?: number;
  vector_db_type?: string;
}

// Define the props for the component
interface SiloFormProps {
  silo?: Silo;
  onSubmit: (data: SiloFormData) => Promise<void>;
  onCancel: () => void;
}

function SiloForm({ silo, onSubmit, onCancel}: Readonly<SiloFormProps>) {
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
  const [embeddingServices, setEmbeddingServices] = useState<any[]>([]);
  const [vectorDbOptions, setVectorDbOptions] = useState<VectorDbOption[]>([]);
  const [loadingFormData, setLoadingFormData] = useState(true);

  const isEditing = !!silo && silo.silo_id !== 0;
  let submitButtonLabel = isEditing ? 'Update Silo' : 'Create Silo';
  if (isSubmitting) {
    submitButtonLabel = 'Saving...';
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
      vector_db_type: vectorDbTypeValue
    }));
  }, [silo]);

  async function loadFormData() {
    if (!appId) return;
    
    try {
      setLoadingFormData(true);
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
      setError(err instanceof Error ? err.message : 'Failed to load form data');
      console.error('Error loading form data:', err);
    } finally {
      setLoadingFormData(false);
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
      setError('Silo name is required');
      return;
    }

    if (!isEditing && !formData.vector_db_type) {
      setError('Vector database selection is required');
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
      setError(err instanceof Error ? err.message : 'Failed to save silo');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (loadingFormData) {
    return (
      <LoadingState variant="section" message="Loading form data..." />
    );
  }

  return (
    <div className="max-w-2xl">
      {/* Form */}
      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="">
          <div className="grid grid-cols-1 gap-6">
            {/* Silo Name */}
            <FormField
              label="Silo Name"
              id="name"
              value={formData.name}
              onChange={handleChange}
              required
              placeholder="Enter silo name"
              disabled={isSubmitting}
            />
            <FormField
              label="Silo Description"
              id="description"
              value={formData.description || ''}
              onChange={handleChange}
              required
              placeholder="Enter silo description"
              disabled={isSubmitting}
            />
            {/* Metadata Definition (Output Parser) */}
            <div>
              <FormSelect
                label="Metadata Definition"
                id="output_parser_id"
                value={formData.output_parser_id?.toString() || ''}
                onChange={handleChange}
                options={[
                  { value: '', label: 'No metadata definition' },
                  ...outputParsers.map((parser) => ({
                    value: parser.parser_id,
                    label: parser.name,
                  })),
                ]}
                disabled={isSubmitting}
                helpText="Optional: Define structured metadata for documents in this silo."
              />
            </div>

            {/* Embedding Service */}
            <div>
              <FormSelect
                label="Embedding Service"
                id="embedding_service_id"
                value={formData.embedding_service_id?.toString() || ''}
                onChange={handleChange}
                required
                options={[
                  { value: '', label: 'Select an embedding service' },
                  ...embeddingServices.map((service) => ({
                    value: service.service_id,
                    label: [
                      service.is_system ? '[System]' : '',
                      service.name,
                      service.provider ? `(${service.provider})` : '',
                    ].filter(Boolean).join(' '),
                  })),
                ]}
                disabled={isSubmitting || isEditing}
                className={isEditing ? '[&>p]:text-accent dark:text-accent-dark' : ''}
                helpText={
                  isEditing
                    ? 'The embedding service cannot be changed after a silo is created.'
                    : 'Required: Choose the embedding service for vector generation.'
                }
              />
            </div>

            {/* Vector Database */}
            <div>
              <FormSelect
                label="Vector Database"
                id="vector_db_type"
                value={vectorDbOptions.length === 0 ? '' : formData.vector_db_type ?? ''}
                onChange={handleChange}
                required={!isEditing}
                options={[
                  ...(vectorDbOptions.length === 0
                    ? [{ value: '', label: 'No vector databases available' }]
                    : []),
                  ...vectorDbOptions.map((option) => ({
                    value: option.code,
                    label: option.label,
                  })),
                ]}
                disabled={isSubmitting || vectorDbOptions.length === 0 || isEditing}
              />
              {isEditing ? (
                <p className="mt-1 text-sm text-fg-secondary dark:text-fg-secondary-dark flex items-center gap-1">
                  <Info className="w-3.5 h-3.5 shrink-0" />
                  The vector database cannot be changed after a silo is created.
                </p>
              ) : vectorDbOptions.length === 0 ? (
                <p className="mt-1 text-sm text-error dark:text-error-dark">
                  No vector databases available. Configure a silo backend before proceeding.
                </p>
              ) : (
                <p className="mt-1 text-sm text-fg-secondary dark:text-fg-secondary-dark">
                  Required: Select the storage engine that will persist vectors for this silo.
                </p>
              )}
            </div>
          </div>
          {/* Error Message */}
          {error && (
            <Alert type="error" message={error} />
          )}

          {/* Action Buttons */}
          <FormActions
            onCancel={onCancel}
            isSubmitting={isSubmitting}
            submitLabel={submitButtonLabel}
            containerClassName="mt-6"
          />
        </div>
      </form>

      {/* Info Section */}
      <Alert
        type="info"
        title="About Custom Silos"
        className="mt-8"
        message={(
          <>
            <p>
              Custom silos are vector storage containers that enable semantic search and retrieval. 
              They store document embeddings and allow AI agents to find relevant information quickly.
            </p>
            <p className="mt-2">
              <span className="font-medium">Embedding Service:</span> Required for converting text to vectors.
              <br />
              <span className="font-medium">Metadata Definition:</span> Optional structured data for filtering and organization.
            </p>
          </>
        )}
      />
    </div>
  );
}

export default SiloForm; 