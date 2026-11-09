import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useFormState } from '../../hooks/useFormState';
import { FormField, FormCheckbox } from '../ui/FormField';
import Alert from '../ui/Alert';
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
}

function APIKeyForm({ apiKey, onSubmit, onCancel }: APIKeyFormProps) {
  const { t } = useTranslation('common');
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
        is_active: apiKey.is_active ?? true
      });
    }
  }, [apiKey]);

  // Validation
  const validate = () => {
    if (!formData.name.trim()) {
      setError(t('apiKeyForm.nameRequired'));
      return false;
    }
    return true;
  };

  // Submit handler with validation
  const onFormSubmit = async (e: React.FormEvent) => {
    if (!validate()) return;
    
    await handleSubmit(e, async () => {
      await onSubmit(formData);
    }, t('apiKeyForm.saveFailed'));
  };

  return (
    <form onSubmit={onFormSubmit} className="space-y-6">
      {/* Error Message */}
      {error && <Alert type="error" message={error} />}

      {/* API Key Name */}
      <FormField
        label={t('apiKeyForm.name')}
        id="name"
        type="text"
        value={formData.name}
        onChange={(e) => updateField('name', e.target.value)}
        placeholder={t('apiKeyForm.namePlaceholder')}
        disabled={isSubmitting}
        required
        helpText={t('apiKeyForm.nameHelp')}
      />

      {/* Active Status */}
      <FormCheckbox
        label={t('apiKeyForm.active')}
        id="is_active"
        checked={formData.is_active}
        onChange={(e) => updateField('is_active', e.target.checked)}
        disabled={isSubmitting}
        helpText={t('apiKeyForm.activeHelp')}
      />

      {/* Info Box */}
      {!isEditing && (
        <Alert
          type="info"
          title={t('apiKeyForm.securityTitle')}
          message={t('apiKeyForm.securityMessage')}
        />
      )}

      {/* Form Actions */}
      <FormActions
        onCancel={onCancel}
        isSubmitting={isSubmitting}
        isEditing={isEditing}
      />
    </form>
  );
}

export default APIKeyForm; 