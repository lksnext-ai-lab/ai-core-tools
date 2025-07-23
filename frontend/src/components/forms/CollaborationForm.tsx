import { useState } from 'react';

interface CollaborationFormProps {
  onSubmit: (email: string, role: string) => Promise<void>;
  loading?: boolean;
}

function CollaborationForm({ onSubmit, loading = false }: CollaborationFormProps) {
  const [email, setEmail] = useState('');
  const [role, setRole] = useState('editor');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!email.trim()) {
      setError('Email is required');
      return;
    }

    const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailPattern.test(email)) {
      setError('Please enter a valid email address');
      return;
    }

    try {
      setIsSubmitting(true);
      setError(null);
      await onSubmit(email.trim(), role);
      
      // Reset form on success
      setEmail('');
      setRole('editor');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send invitation');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3">
          <p className="text-red-600 text-sm">{error}</p>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Email Input */}
        <div className="md:col-span-2">
          <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-2">
            Email Address *
          </label>
          <input
            type="email"
            id="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
            placeholder="user@example.com"
            required
            disabled={isSubmitting}
          />
        </div>

        {/* Role Selector */}
        <div>
          <label htmlFor="role" className="block text-sm font-medium text-gray-700 mb-2">
            Role *
          </label>
          <select
            id="role"
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
            disabled={isSubmitting}
          >
            <option value="editor">Editor</option>
            <option value="owner">Owner</option>
          </select>
        </div>
      </div>

      {/* Role Descriptions */}
      <div className="bg-gray-50 rounded-lg p-4">
        <h4 className="text-sm font-medium text-gray-900 mb-2">Role Permissions</h4>
        <div className="space-y-2 text-sm text-gray-600">
          <div>
            <strong className="text-indigo-600">Editor:</strong> Can view and edit app content, agents, and settings. Cannot invite other users or transfer ownership.
          </div>
          <div>
            <strong className="text-indigo-600">Owner:</strong> Full access including inviting users, managing permissions, and transferring ownership. Can delete the app.
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