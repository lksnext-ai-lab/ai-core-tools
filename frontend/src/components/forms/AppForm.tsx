import { useState } from 'react';

interface App {
  app_id: number;
  name: string;
  created_at: string;
  owner_id: number;
}

interface AppFormProps {
  app?: App | null; // null for create, App object for edit
  onSubmit: (data: { name: string }) => Promise<void>;
  onCancel: () => void;
}

function AppForm({ app, onSubmit, onCancel }: AppFormProps) {
  const [name, setName] = useState(app?.name || '');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isEditing = !!app;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    
    // Basic validation
    if (!name.trim()) {
      setError('App name is required');
      return;
    }

    try {
      setIsSubmitting(true);
      setError(null);
      
      await onSubmit({ name: name.trim() });
      
      // Success - parent component will handle closing modal
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save app');
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {/* App Name Field */}
      <div>
        <label 
          htmlFor="app-name" 
          className="block text-sm font-medium text-gray-700 mb-2"
        >
          App Name
        </label>
        <input
          id="app-name"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Enter app name"
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          disabled={isSubmitting}
        />
      </div>

      {/* Error Message */}
      {error && (
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
          {error}
        </div>
      )}

      {/* Action Buttons */}
      <div className="flex justify-end space-x-3 pt-4">
        <button
          type="button"
          onClick={onCancel}
          disabled={isSubmitting}
          className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-md disabled:opacity-50"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={isSubmitting || !name.trim()}
          className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-md disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isSubmitting 
            ? (isEditing ? 'Updating...' : 'Creating...') 
            : (isEditing ? 'Update App' : 'Create App')
          }
        </button>
      </div>
    </form>
  );
}

export default AppForm; 