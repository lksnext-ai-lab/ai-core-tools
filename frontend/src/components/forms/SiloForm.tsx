import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { apiService } from '../../services/api';

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
  embedding_services?: { service_id: number; name: string; provider?: string }[];
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
  loading?: boolean;
}

function SiloForm({ silo, onSubmit, onCancel}: SiloFormProps) {
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
    loadFormData();
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
      
      const appIdNumber = parseInt(appId, 10);

      // Load output parsers and embedding services in parallel
      const [parsersResponse, servicesResponse] = await Promise.all([
        apiService.getOutputParsers(appIdNumber),
        apiService.getEmbeddingServices(appIdNumber)
      ]);

      setOutputParsers(parsersResponse);
      setEmbeddingServices(servicesResponse);

      // Fetch vector database options only when they are not provided by the silo payload
      if (vectorDbOptions.length === 0) {
        const siloOptions = await apiService.getSiloOptions(appIdNumber);
        const availableVectorDbOptions: VectorDbOption[] = siloOptions.vector_db_options ?? [];
        setVectorDbOptions(availableVectorDbOptions);

        setFormData(prev => ({
          ...prev,
          vector_db_type: availableVectorDbOptions[0]?.code || prev.vector_db_type || 'PGVECTOR'
        }));
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
      parsedValue = value === '' ? undefined : parseInt(value, 10);
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

    if (!formData.vector_db_type) {
      setError('Vector database selection is required');
      return;
    }

    try {
      setIsSubmitting(true);
      setError(null);
      await onSubmit({
        ...formData,
        vector_db_type: formData.vector_db_type.toUpperCase(),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save silo');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (loadingFormData) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-yellow-600"></div>
        <span className="ml-2">Loading form data...</span>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <h2 className="text-xl font-semibold text-gray-900">
          {isEditing ? `Edit Silo: ${silo?.name}` : 'Create New Silo'}
        </h2>
        <p className="text-gray-600">
          {isEditing 
            ? 'Update your silo configuration and settings.'
            : 'Create a new silo for vector storage and semantic search.'
          }
        </p>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="bg-white shadow rounded-lg p-6">
          <div className="grid grid-cols-1 gap-6">
            {/* Silo Name */}
            <div>
              <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-2">
                Silo Name <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                id="name"
                name="name"
                value={formData.name}
                onChange={handleChange}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-yellow-500 focus:border-transparent"
                placeholder="Enter silo name"
                disabled={isSubmitting}
              />
            </div>
            <div>
              <label htmlFor="description" className="block text-sm font-medium text-gray-700 mb-2">
                Silo Description
              </label>
              <input
                type="text"
                id="description"
                name="description"
                value={formData.description || ''}
                onChange={handleChange}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-yellow-500 focus:border-transparent"
                placeholder="Enter silo description"
                disabled={isSubmitting}
              />
            </div>
            {/* Metadata Definition (Output Parser) */}
            <div>
              <label htmlFor="output_parser_id" className="block text-sm font-medium text-gray-700 mb-2">
                Metadata Definition
              </label>
              <select
                id="output_parser_id"
                name="output_parser_id"
                value={formData.output_parser_id?.toString() || ''}
                onChange={handleChange}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-yellow-500 focus:border-transparent"
                disabled={isSubmitting}
              >
                <option value="">No metadata definition</option>
                {outputParsers.map((parser) => (
                  <option key={parser.parser_id} value={parser.parser_id}>
                    {parser.name}
                  </option>
                ))}
              </select>
              <p className="mt-1 text-sm text-gray-500">
                Optional: Define structured metadata for documents in this silo.
              </p>
            </div>

            {/* Embedding Service */}
            <div>
              <label htmlFor="embedding_service_id" className="block text-sm font-medium text-gray-700 mb-2">
                Embedding Service <span className="text-red-500">*</span>
              </label>
              <select
                id="embedding_service_id"
                name="embedding_service_id"
                value={formData.embedding_service_id?.toString() || ''}
                onChange={handleChange}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-yellow-500 focus:border-transparent"
                disabled={isSubmitting}
              >
                <option value="">Select an embedding service</option>
                {embeddingServices.map((service) => (
                  <option key={service.service_id} value={service.service_id}>
                    {service.name} ({service.provider})
                  </option>
                ))}
              </select>
              <p className="mt-1 text-sm text-gray-500">
                Required: Choose the embedding service for vector generation.
              </p>
            </div>

            {/* Vector Database */}
            <div>
              <label htmlFor="vector_db_type" className="block text-sm font-medium text-gray-700 mb-2">
                Vector Database <span className="text-red-500">*</span>
              </label>
              <select
                id="vector_db_type"
                name="vector_db_type"
                value={vectorDbOptions.length === 0 ? '' : formData.vector_db_type ?? ''}
                onChange={handleChange}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-yellow-500 focus:border-transparent"
                disabled={isSubmitting || vectorDbOptions.length === 0}
              >
                {vectorDbOptions.length === 0 && <option value="">No vector databases available</option>}
                {vectorDbOptions.map((option) => (
                  <option key={option.code} value={option.code}>
                    {option.label}
                  </option>
                ))}
              </select>
              {vectorDbOptions.length === 0 ? (
                <p className="mt-1 text-sm text-red-600">
                  No vector databases available. Configure a silo backend before proceeding.
                </p>
              ) : (
                <p className="mt-1 text-sm text-gray-500">
                  Required: Select the storage engine that will persist vectors for this silo.
                </p>
              )}
            </div>
          </div>

          {/* Error Message */}
          {error && (
            <div className="mt-4 bg-red-50 border border-red-200 rounded-lg p-4">
              <div className="flex">
                <span className="text-red-400 text-xl mr-3">⚠️</span>
                <div>
                  <h3 className="text-sm font-medium text-red-800">Error</h3>
                  <p className="text-sm text-red-600 mt-1">{error}</p>
                </div>
              </div>
            </div>
          )}

          {/* Action Buttons */}
          <div className="mt-6 flex items-center justify-between">
            <button
              type="button"
              onClick={onCancel}
              disabled={isSubmitting}
              className="px-4 py-2 text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-6 py-2 bg-yellow-600 hover:bg-yellow-700 disabled:bg-yellow-400 text-white rounded-lg flex items-center"
            >
              {isSubmitting && (
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
              )}
              {submitButtonLabel}
            </button>
          </div>
        </div>
      </form>

      {/* Info Section */}
      <div className="mt-8 bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div className="flex">
          <div className="flex-shrink-0">
            <span className="text-blue-400 text-xl">ℹ️</span>
          </div>
          <div className="ml-3">
            <h3 className="text-sm font-medium text-blue-800">
              About Custom Silos
            </h3>
            <div className="mt-2 text-sm text-blue-700">
              <p>
                Custom silos are vector storage containers that enable semantic search and retrieval. 
                They store document embeddings and allow AI agents to find relevant information quickly.
              </p>
              <p className="mt-2">
                <strong>Embedding Service:</strong> Required for converting text to vectors.
                <br />
                <strong>Metadata Definition:</strong> Optional structured data for filtering and organization.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default SiloForm; 