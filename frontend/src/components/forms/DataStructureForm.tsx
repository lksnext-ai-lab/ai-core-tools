import { useState, useEffect } from 'react';
import FieldManager from './FieldManager';
import { FormActions } from '../ui/FormActions';
import Alert from '../ui/Alert';
import { randomId } from '../../utils/randomId';
import FormField, { FormTextArea } from '../ui/FormField';

interface FieldDefinition {
  name: string;
  type: string;
  description: string;
  optional?: boolean;
  parser_id?: number;
  list_item_type?: string;
  list_item_parser_id?: number;
  _key?: string;
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
        fields: (dataStructure.fields || []).map(f => ({ ...f, _key: randomId() }))
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

    const namePattern = /^\w+$/;
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

    // Filter out empty fields and strip internal _key
    const cleanedFields = formData.fields
      .filter(field => field.name.trim())
      .map(({ _key: _k, ...rest }) => rest);

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
      {error && <Alert type="error" message={error} />}

      {/* Basic Information */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Name */}
        <FormField
          label="Data Structure Name"
          id="name"
          value={formData.name}
          onChange={handleBasicFieldChange}
          required
          placeholder="e.g., User, Product, Address"
          helpText="Use PascalCase for structure names (e.g., UserProfile, ProductInfo)"
        />

        {/* Description */}
        <FormTextArea
          label="Description"
          id="description"
          value={formData.description}
          onChange={handleBasicFieldChange}
          rows={4}
          placeholder="Describe what this data structure represents..."
        />
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
      <Alert
        type="info"
        title="About Data Structures"
        message={
          <>
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
          </>
        }
      />

      {/* Form Actions */}
      <FormActions
        onCancel={onCancel}
        isSubmitting={isSubmitting}
        isEditing={isEditing}
        submitLabel={isEditing ? 'Update Structure' : 'Create Structure'}
      />
    </form>
  );
}

export default DataStructureForm; 