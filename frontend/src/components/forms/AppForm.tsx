import { useEffect } from 'react';
import { useFormState } from '../../hooks/useFormState';
import { FormField } from '../ui/FormField';
import { FormError } from '../ui/FormError';
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
      setError('App name is required');
      return false;
    }
    return true;
  };

  // Submit handler with validation
  const onFormSubmit = async (e: React.FormEvent) => {
    if (!validate()) return;
    
    await handleSubmit(e, async () => {
      await onSubmit({ name: formData.name.trim() });
    }, 'Failed to save app');
  };

  return (
    <form onSubmit={onFormSubmit} className="space-y-4">
      {/* App Name Field */}
      <FormField
        label="App Name"
        id="app-name"
        type="text"
        value={formData.name}
        onChange={(e) => updateField('name', e.target.value)}
        placeholder="Enter app name"
        disabled={isSubmitting}
        required
      />

      {/* Error Message */}
      <FormError error={error} />

      {/* Action Buttons */}
      <FormActions
        onCancel={onCancel}
        isSubmitting={isSubmitting}
        submitLabel={isEditing ? 'Update App' : 'Create App'}
      />
    </form>
  );
}

export default AppForm; 