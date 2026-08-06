import { useEffect, useState } from 'react';
import FormActions from './FormActions';

interface EnumOption {
  name: string;
  description: string;
  _key?: string;
}

export interface EnumFormData {
  name: string;
  description: string;
  fields: Array<{ name: string; type: 'str'; description: string }>;
  is_enum: true;
}

interface EnumDefinition {
  parser_id: number;
  name: string;
  description: string;
  fields: EnumOption[];
}

interface EnumFormProps {
  enumDefinition?: EnumDefinition | null;
  onSubmit: (data: EnumFormData) => Promise<void>;
  onCancel: () => void;
}

function EnumForm({ enumDefinition, onSubmit, onCancel }: Readonly<EnumFormProps>) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [fields, setFields] = useState<EnumOption[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setName(enumDefinition?.name || '');
    setDescription(enumDefinition?.description || '');
    setFields((enumDefinition?.fields || []).map((field) => ({ ...field, _key: crypto.randomUUID() })));
  }, [enumDefinition]);

  const updateField = (index: number, update: Partial<EnumOption>) => {
    setFields((current) => current.map((field, fieldIndex) => fieldIndex === index ? { ...field, ...update } : field));
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const namePattern = /^\w+$/;
    if (!name.trim() || !namePattern.test(name)) {
      setError('Enum name is required and may only contain letters, numbers, and underscores');
      return;
    }
    const options = fields.filter((field) => field.name.trim());
    if (new Set(options.map((field) => field.name)).size !== options.length) {
      setError('Enum values must be unique');
      return;
    }
    try {
      setIsSubmitting(true);
      setError(null);
      await onSubmit({
        name,
        description,
        fields: options.map(({ name: optionName, description: optionDescription }) => ({ name: optionName, type: 'str', description: optionDescription })),
        is_enum: true,
      });
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Failed to save enum');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {error && <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-red-600">{error}</div>}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div>
          <label htmlFor="enum-name" className="block text-sm font-medium text-gray-700 mb-2">Enum Name *</label>
          <input id="enum-name" value={name} onChange={(event) => setName(event.target.value)} className="w-full px-4 py-3 border border-gray-300 rounded-lg" placeholder="e.g., Status" required />
        </div>
        <div>
          <label htmlFor="enum-description" className="block text-sm font-medium text-gray-700 mb-2">Description</label>
          <textarea id="enum-description" value={description} onChange={(event) => setDescription(event.target.value)} rows={3} className="w-full px-4 py-3 border border-gray-300 rounded-lg resize-none" placeholder="Describe the allowed values..." />
        </div>
      </div>
      <div className="space-y-3">
        <div className="flex justify-between items-center">
          <h3 className="text-lg font-medium text-gray-900">Values ({fields.length}/20)</h3>
          <button type="button" onClick={() => fields.length < 20 && setFields([...fields, { name: '', description: '', _key: crypto.randomUUID() }])} disabled={fields.length >= 20} className="px-3 py-1 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white text-sm rounded">Add Value</button>
        </div>
        <div className="rounded-lg overflow-hidden">
          {fields.length === 0 
            ? 
            <div className="text-center py-8 border-2 border-dashed border-gray-300 rounded-lg">
                <p className="text-gray-500 mb-4">No enum values defined yet</p>
                <button
                    type="button"
                    onClick={() => setFields([...fields, { name: '', description: '', _key: crypto.randomUUID() }])}
                    className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
                >
                    Add First Value
                </button>
            </div>
            : (
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50"><tr><th className="px-4 py-3 text-left text-xs text-gray-500 uppercase">Value</th><th className="px-4 py-3 text-left text-xs text-gray-500 uppercase">Description</th><th className="w-16" /></tr></thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {fields.map((field, index) => <tr key={field._key}>
                  <td className="px-4 py-3"><input value={field.name} onChange={(event) => updateField(index, { name: event.target.value })} className="w-full px-3 py-2 border border-gray-300 rounded-md" placeholder="value_name" /></td>
                  <td className="px-4 py-3"><input value={field.description} onChange={(event) => updateField(index, { description: event.target.value })} className="w-full px-3 py-2 border border-gray-300 rounded-md" placeholder="Optional description" /></td>
                  <td className="px-4 py-3">
                    <button
                        type="button"
                        onClick={() => setFields(fields.filter((_, fieldIndex) => fieldIndex !== index))}
                        className="text-red-600 hover:text-red-900 transition-colors p-2"
                        title="Remove field"
                    >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                        </svg>
                    </button>
                  </td>
                </tr>)}
              </tbody>
            </table>
          )}
        </div>
      </div>
      <FormActions onCancel={onCancel} isSubmitting={isSubmitting} isEditing={Boolean(enumDefinition && enumDefinition.parser_id !== 0)} submitLabel={enumDefinition?.parser_id ? 'Update Enum' : 'Create Enum'} submitButtonColor="purple" />
    </form>
  );
}

export default EnumForm;
