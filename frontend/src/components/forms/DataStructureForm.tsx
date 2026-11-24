import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
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
  const { t } = useTranslation('common');
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
      return t('dataStructuresPage.form.nameRequired');
    }

    const namePattern = /^\w+$/;
    if (!namePattern.test(formData.name)) {
      return t('dataStructuresPage.form.invalidName');
    }

    // Validate fields
    const fieldNames = formData.fields.map(f => f.name).filter(name => name.trim());
    const uniqueNames = new Set(fieldNames);
    if (fieldNames.length !== uniqueNames.size) {
      return t('dataStructuresPage.form.duplicateFieldNames');
    }

    for (const field of formData.fields) {
      if (field.name && !namePattern.test(field.name)) {
        return t('dataStructuresPage.form.invalidFieldName', { name: field.name });
      }
      
      if (field.type === 'parser' && !field.parser_id) {
        return t('dataStructuresPage.form.parserRequired', { name: field.name });
      }
      
      if (field.type === 'list' && field.list_item_type === 'parser' && !field.list_item_parser_id) {
        return t('dataStructuresPage.form.listParserRequired', { name: field.name });
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
      setError(err instanceof Error ? err.message : t('dataStructuresPage.form.saveFailed'));
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
          label={t('dataStructuresPage.form.name')}
          id="name"
          value={formData.name}
          onChange={handleBasicFieldChange}
          required
          placeholder={t('dataStructuresPage.form.namePlaceholder')}
          helpText={t('dataStructuresPage.form.nameHelp')}
        />

        {/* Description */}
        <FormTextArea
          label={t('dataStructuresPage.form.description')}
          id="description"
          value={formData.description}
          onChange={handleBasicFieldChange}
          rows={4}
          placeholder={t('dataStructuresPage.form.descriptionPlaceholder')}
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
        title={t('dataStructuresPage.form.aboutTitle')}
        message={
          <>
            <p className="mb-2">
              {t('dataStructuresPage.form.aboutMessage')}
            </p>
            <div>
              <strong>{t('dataStructuresPage.form.useCases')}</strong>
              <ul className="list-disc list-inside mt-1 space-y-1">
                <li>{t('dataStructuresPage.form.agentSchemas')}</li>
                <li>{t('dataStructuresPage.form.documentMetadata')}</li>
                <li>{t('dataStructuresPage.form.nestedModels')}</li>
                <li>{t('dataStructuresPage.form.validateData')}</li>
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
      />
    </form>
  );
}

export default DataStructureForm; 