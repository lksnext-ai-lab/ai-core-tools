import { useEffect } from 'react';
import { useFormState } from '../../hooks/useFormState';
import { FormField } from '../ui/FormField';
import { FormCheckbox } from '../ui/FormField';
import { FormError } from '../ui/FormError';
import { FormActions } from '../ui/FormActions';

interface APIKeyFormData {
  name: string;
  is_active: boolean;
}

interface APIKey {
  key_id: number;
  name: string;
  is_active: boolean;
  created_at: string;
  last_used_at: string | null;
  key_preview: string;
}

interface APIKeyFormProps {
  readonly apiKey?: APIKey | null;
  readonly onSubmit: (data: APIKeyFormData) => Promise<void>;
  readonly onCancel: () => void;
  readonly loading?: boolean;
}

function APIKeyForm({ apiKey, onSubmit, onCancel }: APIKeyFormProps) {
  const isEditing = !!apiKey && apiKey.key_id !== 0;

  // Use shared form state hook
  const { formData, updateField, updateFields, isSubmitting, error, setError, handleSubmit } = useFormState<APIKeyFormData>({
    name: '',
    is_active: true
  });

  // Initialize form with existing key data
  useEffect(() => {
    if (apiKey) {
      updateFields({
        name: apiKey.name || '',
        is_active: apiKey.is_active !== undefined ? apiKey.is_active : true
      });
    }
  }, [apiKey]);

  // Validation
  const validate = () => {
    if (!formData.name.trim()) {
      setError('API key name is required');
      return false;
    }
    return true;
  };

  // Submit handler with validation
  const onFormSubmit = async (e: React.FormEvent) => {
    if (!validate()) return;
    
    await handleSubmit(e, async () => {
      await onSubmit(formData);
    }, 'Failed to save API key');
  };

  return (
    <form onSubmit={onFormSubmit} className="space-y-6">
      {/* Error Message */}
      <FormError error={error} />

      {/* API Key Name */}
      <FormField
        label="API Key Name"
        id="name"
        type="text"
        value={formData.name}
        onChange={(e) => updateField('name', e.target.value)}
        placeholder="e.g., Production API, Mobile App Key"
        disabled={isSubmitting}
        required
        helpText="Choose a descriptive name to help identify this key's purpose"
      />

      {/* Active Status */}
      <FormCheckbox
        label="Active"
        id="is_active"
        checked={formData.is_active}
        onChange={(e) => updateField('is_active', e.target.checked)}
        disabled={isSubmitting}
        helpText="Inactive keys cannot be used to access the API"
      />

      {/* Info Box */}
      {!isEditing && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
          <div className="flex">
            <div className="flex-shrink-0">
              <span className="text-blue-400 text-xl">🔑</span>
            </div>
            <div className="ml-3">
              <h3 className="text-sm font-medium text-blue-800">
                API Key Security
              </h3>
              <div className="mt-2 text-xs text-blue-700">
                <p>
                  Your API key will be generated automatically and shown only once. 
                  Make sure to copy and store it securely before closing this dialog.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Form Actions */}
      <FormActions
        onCancel={onCancel}
        isSubmitting={isSubmitting}
        submitLabel={isEditing ? 'Update API Key' : 'Create API Key'}
      />
    </form>
  );
}

export default APIKeyForm; 