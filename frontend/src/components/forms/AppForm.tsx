import React, { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useFormState } from '../../hooks/useFormState';
import { FormField } from '../ui/FormField';
import Alert from '../ui/Alert';
import { FormActions } from '../ui/FormActions';

interface App {
  app_id: number;
  name: string;
  created_at: string;
  owner_id: number;
  agent_rate_limit: number;
}

interface AppFormProps {
  readonly app?: App | null; // null for create, App object for edit
  readonly onSubmit: (data: { name: string }) => Promise<void>;
  readonly onCancel: () => void;
}

function AppForm({ app, onSubmit, onCancel }: AppFormProps) {
  const { t } = useTranslation('common');
  const isEditing = !!app;
  
  // Use shared form state hook
  const { formData, updateField, isSubmitting, error, setError, handleSubmit } = useFormState({
    name: app?.name || ''
  });

  // Update form when app prop changes
  useEffect(() => {
    if (app) {
      updateField('name', app.name);
    }
  }, [app]);

  // Validation
  const validate = () => {
    if (!formData.name.trim()) {
      setError(t('appForm.nameRequired'));
      return false;
    }
    return true;
  };

  // Submit handler with validation
  const onFormSubmit = async (e: React.FormEvent) => {
    if (!validate()) return;
    
    await handleSubmit(e, async () => {
      await onSubmit({ 
        name: formData.name.trim()
      });
    }, t('appForm.saveFailed'));
  };

  return (
    <form onSubmit={onFormSubmit} className="space-y-4">
      {/* App Name Field */}
      <FormField
        label={t('appForm.name')}
        id="app-name"
        type="text"
        value={formData.name}
        onChange={(e) => updateField('name', e.target.value)}
        placeholder={t('appForm.namePlaceholder')}
        disabled={isSubmitting}
        required
      />

      {/* Error Message */}
      {error && <Alert type="error" message={error} />}

      {/* Action Buttons */}
      <FormActions
        onCancel={onCancel}
        isSubmitting={isSubmitting}
        submitLabel={isEditing ? t('appForm.update') : t('appsPage.createApp')}
      />
    </form>
  );
}

export default AppForm; 