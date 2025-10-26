import { useFormState } from '../../hooks/useFormState';
import { FormField } from '../ui/FormField';
import { FormError } from '../ui/FormError';

interface CollaborationFormProps {
  readonly onSubmit: (email: string, role: string) => Promise<void>;
  readonly loading?: boolean;
}

function CollaborationForm({ onSubmit, loading = false }: CollaborationFormProps) {
  // Use shared form state hook
  const { formData, updateField, isSubmitting, error, setError, handleSubmit, reset } = useFormState({
    email: ''
  });

  // Email validation
  const validate = () => {
    if (!formData.email.trim()) {
      setError('Email is required');
      return false;
    }

    const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailPattern.test(formData.email)) {
      setError('Please enter a valid email address');
      return false;
    }

    return true;
  };

  // Submit handler with validation
  const onFormSubmit = async (e: React.FormEvent) => {
    if (!validate()) return;
    
    await handleSubmit(e, async () => {
      // Always invite as editor (as per requirements)
      await onSubmit(formData.email.trim(), 'editor');
      // Reset form on success
      reset();
    }, 'Failed to send invitation');
  };

  return (
    <form onSubmit={onFormSubmit} className="space-y-4">
      {/* Error Message */}
      <FormError error={error} />

      <div className="space-y-4">
        {/* Email Input */}
        <FormField
          label="Email Address"
          id="email"
          type="email"
          value={formData.email}
          onChange={(e) => updateField('email', e.target.value)}
          placeholder="user@example.com"
          disabled={isSubmitting || loading}
          required
        />

        {/* Role Info (Read-only) */}
        <div className="bg-gray-50 rounded-lg p-4">
          <h4 className="text-sm font-medium text-gray-900 mb-2">
            Invitation Role: <span className="text-indigo-600">Editor</span>
          </h4>
          <div className="text-sm text-gray-600">
            <p>
              <strong>Editors</strong> can view and edit app content, agents, and settings. 
              They cannot invite other users or manage collaborations.
            </p>
          </div>
        </div>
      </div>

      {/* Submit Button */}
      <div className="flex justify-end">
        <button
          type="submit"
          disabled={isSubmitting || loading}
          className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white rounded-lg flex items-center transition-colors"
        >
          {isSubmitting && (
            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
          )}
          {isSubmitting ? 'Sending...' : 'Send Invitation'}
        </button>
      </div>
    </form>
  );
}

export default CollaborationForm; 