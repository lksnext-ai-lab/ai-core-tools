import { randomId } from '../../utils/randomId';
import { useTranslation } from 'react-i18next';
import Alert from '../ui/Alert';
import { ButtonApp } from '../ui/ButtonApp';
import FormField, { FormSelect, FormTextArea } from '../ui/FormField';
import Table, { type TableColumn } from '../ui/Table';

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

interface FieldManagerProps {
  fields: FieldDefinition[];
  onChange: (fields: FieldDefinition[]) => void;
  availableParsers: Array<{value: number, name: string}>;
  maxFields?: number;
}

function FieldManager({ fields, onChange, availableParsers, maxFields = 20 }: Readonly<FieldManagerProps>) {
  const { t } = useTranslation('common');
  const fieldTypes = [
    { value: 'str', name: t('dataStructuresPage.fields.types.string') },
    { value: 'int', name: t('dataStructuresPage.fields.types.integer') },
    { value: 'float', name: t('dataStructuresPage.fields.types.float') },
    { value: 'bool', name: t('dataStructuresPage.fields.types.boolean') },
    { value: 'date', name: t('dataStructuresPage.fields.types.date') },
    { value: 'dict', name: t('dataStructuresPage.fields.types.dictionary') },
    { value: 'list', name: t('dataStructuresPage.fields.types.list') },
    { value: 'parser', name: t('dataStructuresPage.fields.types.parser') }
  ];

  const addField = () => {
    if (fields.length >= maxFields) return;
    
    const newField: FieldDefinition = {
      _key: randomId(),
      name: '',
      type: 'str',
      description: ''
    };
    
    onChange([...fields, newField]);
  };

  const removeField = (index: number) => {
    const newFields = fields.filter((_, i) => i !== index);
    onChange(newFields);
  };

  const updateField = (index: number, updates: Partial<FieldDefinition>) => {
    const newFields = fields.map((field, i) => {
      if (i === index) {
        const updatedField = { ...field, ...updates };
        
        // Clear type-specific fields when type changes
        if (updates.type && updates.type !== field.type) {
          if (updates.type !== 'parser') {
            updatedField.parser_id = undefined;
          }
          if (updates.type !== 'list') {
            updatedField.list_item_type = undefined;
            updatedField.list_item_parser_id = undefined;
          }
        }
        
        return updatedField;
      }
      return field;
    });
    
    onChange(newFields);
  };

  const validateFieldName = (name: string): boolean => {
    const pattern = /^\w+$/;
    return pattern.test(name);
  };

  const parserOptions = [
    { value: '', label: t('dataStructuresPage.fields.selectParser') },
    ...availableParsers.map((parser) => ({ value: parser.value, label: parser.name }))
  ];

  const getListItemTypes = () => [
    { value: 'str', name: t('dataStructuresPage.fields.types.string') },
    { value: 'int', name: t('dataStructuresPage.fields.types.integer') },
    { value: 'float', name: t('dataStructuresPage.fields.types.float') },
    { value: 'bool', name: t('dataStructuresPage.fields.types.boolean') },
    { value: 'date', name: t('dataStructuresPage.fields.types.date') },
    { value: 'dict', name: t('dataStructuresPage.fields.types.dictionary') },
    { value: 'parser', name: t('dataStructuresPage.fields.types.parser') }
  ];

  const rows = fields.map((field, index) => ({ field, index }));
  type FieldRow = (typeof rows)[number];

  const cellClassName = 'px-6 py-4 align-top';

  const columns: TableColumn<FieldRow>[] = [
    {
      header: t('dataStructuresPage.fields.columns.name'),
      headerClassName: 'w-1/4',
      className: cellClassName,
      render: ({ field, index }) => (
        <FormField
          id={`field_name_${index}`}
          ariaLabel={t('dataStructuresPage.fields.fieldNameAria')}
          value={field.name}
          onChange={(e) => updateField(index, { name: e.target.value })}
          error={field.name && !validateFieldName(field.name) ? t('dataStructuresPage.fields.invalidFieldName') : undefined}
          placeholder="field_name"
        />
      ),
    },
    {
      header: t('dataStructuresPage.fields.columns.typeConfiguration'),
      headerClassName: 'w-1/3',
      className: cellClassName,
      render: ({ field, index }) => (
        <div className="space-y-3">
          {/* Main Type Selector */}
          <FormSelect
            id={`field_type_${index}`}
            label={t('dataStructuresPage.fields.fieldType')}
            labelClassName="sr-only"
            value={field.type}
            onChange={(e) => updateField(index, { type: e.target.value })}
            options={fieldTypes.map((type) => ({ value: type.value, label: type.name }))}
          />

          {/* Parser Reference Selector */}
          {field.type === 'parser' && (
            <FormSelect
              id={`parser_ref_${index}`}
              label={t('dataStructuresPage.fields.referenceParser')}
              labelClassName="block text-xs font-medium text-gray-700 mb-1"
              value={field.parser_id || ''}
              onChange={(e) => updateField(index, { parser_id: Number.parseInt(e.target.value) || undefined })}
              options={parserOptions}
            />
          )}

          {/* List Type Selectors */}
          {field.type === 'list' && (
            <div className="space-y-2">
              <FormSelect
                id={`list_item_type_${index}`}
                label={t('dataStructuresPage.fields.listItemType')}
                labelClassName="block text-xs font-medium text-gray-700 mb-1"
                value={field.list_item_type || 'str'}
                onChange={(e) => updateField(index, { list_item_type: e.target.value })}
                options={getListItemTypes().map((type) => ({ value: type.value, label: type.name }))}
              />

              {field.list_item_type === 'parser' && (
                <FormSelect
                  id={`list_item_parser_${index}`}
                  label={t('dataStructuresPage.fields.listItemParser')}
                  labelClassName="block text-xs font-medium text-gray-700 mb-1"
                  value={field.list_item_parser_id || ''}
                  onChange={(e) => updateField(index, { list_item_parser_id: Number.parseInt(e.target.value) || undefined })}
                  options={parserOptions}
                />
              )}
            </div>
          )}
        </div>
      ),
    },
    {
      header: t('dataStructuresPage.fields.columns.description'),
      headerClassName: 'w-1/3',
      className: cellClassName,
      render: ({ field, index }) => (
        <FormTextArea
          id={`field_description_${index}`}
          label={t('dataStructuresPage.fields.descriptionLabel')}
          labelClassName="sr-only"
          value={field.description}
          onChange={(e) => updateField(index, { description: e.target.value })}
          rows={3}
          textareaClassName="resize-none"
          placeholder={t('dataStructuresPage.fields.descriptionPlaceholder')}
        />
      ),
    },
    {
      header: t('dataStructuresPage.fields.columns.optional'),
      headerClassName: 'text-center w-20',
      className: `${cellClassName} text-center`,
      render: ({ field, index }) => (
        <FormField
          type="checkbox"
          id={`optional_${index}`}
          ariaLabel={t('dataStructuresPage.fields.optionalAria')}
          checked={field.optional ?? false}
          onChange={(e) => updateField(index, { optional: e.target.checked })}
        />
      ),
    },
    {
      header: t('dataStructuresPage.fields.columns.actions'),
      headerClassName: 'w-16',
      className: cellClassName,
      render: ({ index }) => (
        <button
          type="button"
          onClick={() => removeField(index)}
          className="text-red-600 hover:text-red-900 transition-colors p-2"
          title={t('dataStructuresPage.fields.removeField')}
          aria-label={t('dataStructuresPage.fields.removeField')}
        >
          <svg aria-hidden="true" className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
          </svg>
        </button>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-medium text-fg dark:text-fg-dark">{t('dataStructuresPage.fields.heading', { count: fields.length, max: maxFields })}</h3>
        <ButtonApp
          label={t('dataStructuresPage.fields.addField')}
          variant="primary"
          size="medium"
          onClick={addField}
          disabled={fields.length >= maxFields}
        />
      </div>

      {/* Fields Table */}
      {fields.length > 0 ? (
        <Table
          columns={columns}
          data={rows}
          keyExtractor={({ field, index }) => field._key ?? index}
        />
      ) : (
        <div className="text-center py-8 border-2 border-dashed border-gray-300 rounded-lg">
          <p className="text-gray-500 mb-4">{t('dataStructuresPage.fields.empty')}</p>
          <ButtonApp
            label={t('dataStructuresPage.fields.addFirstField')}
            variant="primary"
            size="medium"
            onClick={addField}
          />
        </div>
      )}

      {/* Field Types Help */}
      <Alert
        type="info"
        title={t('dataStructuresPage.fields.referenceTitle')}
        message={(
          <div className="text-xs space-y-1">
            <p><strong>{t('dataStructuresPage.fields.types.string')}:</strong> {t('dataStructuresPage.fields.typeHelp.string')}</p>
            <p><strong>{t('dataStructuresPage.fields.types.integer')}:</strong> {t('dataStructuresPage.fields.typeHelp.integer')}</p>
            <p><strong>{t('dataStructuresPage.fields.types.float')}:</strong> {t('dataStructuresPage.fields.typeHelp.float')}</p>
            <p><strong>{t('dataStructuresPage.fields.types.boolean')}:</strong> {t('dataStructuresPage.fields.typeHelp.boolean')}</p>
            <p><strong>{t('dataStructuresPage.fields.types.date')}:</strong> {t('dataStructuresPage.fields.typeHelp.date')}</p>
            <p><strong>{t('dataStructuresPage.fields.types.list')}:</strong> {t('dataStructuresPage.fields.typeHelp.list')}</p>
            <p><strong>{t('dataStructuresPage.fields.types.parser')}:</strong> {t('dataStructuresPage.fields.typeHelp.parser')}</p>
          </div>
        )}
      />
    </div>
  );
}

export default FieldManager; 