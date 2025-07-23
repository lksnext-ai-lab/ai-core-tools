import { useState, useEffect } from 'react';

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
  apiKey?: APIKey | null;
  onSubmit: (data: APIKeyFormData) => Promise<void>;
  onCancel: () => void;
  loading?: boolean;
}

function APIKeyForm({ apiKey, onSubmit, onCancel, loading = false }: APIKeyFormProps) {
  const [formData, setFormData] = useState<APIKeyFormData>({
    name: '',
    is_active: true
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isEditing = !!apiKey && apiKey.key_id !== 0;

  // Initialize form with existing key data
  useEffect(() => {
    if (apiKey) {
      setFormData({
        name: apiKey.name || '',
        is_active: apiKey.is_active !== undefined ? apiKey.is_active : true
      });
    }
  }, [apiKey]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    // Basic validation
    if (!formData.name.trim()) {
      setError('API key name is required');
      return;
    }

    try {
      setIsSubmitting(true);
      setError(null);
      await onSubmit(formData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save API key');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3">
          <p className="text-red-600 text-sm">{error}</p>
        </div>
      )}

      {/* API Key Name */}
      <div>
        <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-2">
          API Key Name *
        </label>
        <input
          type="text"
          id="name"
          name="name"
          value={formData.name}
          onChange={handleChange}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          placeholder="e.g., Production API, Mobile App Key"
          required
        />
        <p className="mt-1 text-xs text-gray-500">
          Choose a descriptive name to help identify this key's purpose
        </p>
      </div>

      {/* Active Status */}
      <div>
        <div className="flex items-center">
          <input
            type="checkbox"
            id="is_active"
            name="is_active"
            checked={formData.is_active}
            onChange={handleChange}
            className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
          />
          <label htmlFor="is_active" className="ml-2 block text-sm text-gray-700">
            Active
          </label>
        </div>
        <p className="mt-1 text-xs text-gray-500">
          Inactive keys cannot be used to access the API
        </p>
      </div>

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
      <div className="flex items-center justify-end space-x-3 pt-4 border-t border-gray-200">
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
          disabled={isSubmitting}
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={isSubmitting}
          className="px-6 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white rounded-lg flex items-center transition-colors"
        >
          {isSubmitting && (
            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
          )}
          {isSubmitting ? 'Saving...' : (isEditing ? 'Update API Key' : 'Create API Key')}
        </button>
      </div>
    </form>
  );
}

export default APIKeyForm; 