import { useState, useEffect } from 'react';
import FieldManager from './FieldManager';
import FormActions from './FormActions';

interface FieldDefinition {
  name: string;
  type: string;
  description: string;
  parser_id?: number;
  list_item_type?: string;
  list_item_parser_id?: number;
}

interface DataStructureFormData {
  name: string;
  description: string;
  fields: FieldDefinition[];
}

interface DataStructure {
  parser_id: number;
  name: string;
  description: string;
  fields: FieldDefinition[];
  created_at: string;
  available_parsers: Array<{value: number, name: string}>;
}

interface DataStructureFormProps {
  dataStructure?: DataStructure | null;
  onSubmit: (data: DataStructureFormData) => Promise<void>;
  onCancel: () => void;
}

function DataStructureForm({ dataStructure, onSubmit, onCancel }: Readonly<DataStructureFormProps>) {
  const [formData, setFormData] = useState<DataStructureFormData>({
    name: '',
    description: '',
    fields: []
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isEditing = !!dataStructure && dataStructure.parser_id !== 0;

  // Initialize form with existing data structure data
  useEffect(() => {
    if (dataStructure) {
      setFormData({
        name: dataStructure.name || '',
        description: dataStructure.description || '',
        fields: dataStructure.fields || []
      });
    }
  }, [dataStructure]);

  const handleBasicFieldChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));
  };

  const handleFieldsChange = (fields: FieldDefinition[]) => {
    setFormData(prev => ({
      ...prev,
      fields
    }));
  };

  const validateForm = (): string | null => {
    if (!formData.name.trim()) {
      return 'Data structure name is required';
    }

    const namePattern = /^[a-zA-Z0-9_]+$/;
    if (!namePattern.test(formData.name)) {
      return 'Name can only contain letters, numbers, and underscores';
    }

    // Validate fields
    const fieldNames = formData.fields.map(f => f.name).filter(name => name.trim());
    const uniqueNames = new Set(fieldNames);
    if (fieldNames.length !== uniqueNames.size) {
      return 'Field names must be unique';
    }

    for (const field of formData.fields) {
      if (field.name && !namePattern.test(field.name)) {
        return `Field name '${field.name}' can only contain letters, numbers, and underscores`;
      }
      
      if (field.type === 'parser' && !field.parser_id) {
        return `Field '${field.name}' with parser type must have a parser selected`;
      }
      
      if (field.type === 'list' && field.list_item_type === 'parser' && !field.list_item_parser_id) {
        return `Field '${field.name}' with list of parsers must have a parser selected`;
      }
    }

    return null;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    const validationError = validateForm();
    if (validationError) {
      setError(validationError);
      return;
    }

    // Filter out empty fields
    const cleanedFields = formData.fields.filter(field => field.name.trim());

    try {
      setIsSubmitting(true);
      setError(null);
      await onSubmit({
        ...formData,
        fields: cleanedFields
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save data structure');
    } finally {
      setIsSubmitting(false);
    }
  };

  const availableParsers = dataStructure?.available_parsers || [];

  return (
    <form onSubmit={handleSubmit} className="space-y-8">
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-red-600 text-sm">{error}</p>
        </div>
      )}

      {/* Basic Information */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Name */}
        <div>
          <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-2">
            Data Structure Name *
          </label>
          <input
            type="text"
            id="name"
            name="name"
            value={formData.name}
            onChange={handleBasicFieldChange}
            className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent text-base"
            placeholder="e.g., User, Product, Address"
            required
          />
          <p className="mt-2 text-sm text-gray-500">
            Use PascalCase for structure names (e.g., UserProfile, ProductInfo)
          </p>
        </div>

        {/* Description */}
        <div>
          <label htmlFor="description" className="block text-sm font-medium text-gray-700 mb-2">
            Description
          </label>
          <textarea
            id="description"
            name="description"
            value={formData.description}
            onChange={handleBasicFieldChange}
            rows={4}
            className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent text-base resize-none"
            placeholder="Describe what this data structure represents..."
          />
        </div>
      </div>

      {/* Fields Management */}
      <div>
        <FieldManager
          fields={formData.fields}
          onChange={handleFieldsChange}
          availableParsers={availableParsers}
          maxFields={20}
        />
      </div>

      {/* Info Box */}
      <div className="bg-purple-50 border border-purple-200 rounded-lg p-4">
        <div className="flex">
          <div className="flex-shrink-0">
            <span className="text-purple-400 text-xl">📊</span>
          </div>
          <div className="ml-3">
            <h3 className="text-sm font-medium text-purple-800">
              About Data Structures
            </h3>
            <div className="mt-2 text-sm text-purple-700">
              <p className="mb-2">
                Data structures define the schema for structured data extraction and processing. 
                They generate Pydantic models that validate and parse AI agent outputs.
              </p>
              <div>
                <strong>Use cases:</strong>
                <ul className="list-disc list-inside mt-1 space-y-1">
                  <li>Define agent output schemas for consistent responses</li>
                  <li>Create metadata structures for document processing</li>
                  <li>Build complex nested data models with references</li>
                  <li>Validate and type-check extracted information</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Form Actions */}
      <FormActions
        onCancel={onCancel}
        isSubmitting={isSubmitting}
        isEditing={isEditing}
        submitLabel={isEditing ? 'Update Structure' : 'Create Structure'}
        submitButtonColor="purple"
      />
    </form>
  );
}

export default DataStructureForm; 