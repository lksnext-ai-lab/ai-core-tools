import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { apiService } from '../../services/api';
import Alert from '../../components/ui/Alert';
import { useAppRole } from '../../hooks/useAppRole';
import { AppRole } from '../../types/roles';
import ReadOnlyBanner from '../../components/ui/ReadOnlyBanner';

function GeneralSettingsPage() {
  const { appId } = useParams();
  const { hasMinRole, userRole } = useAppRole(appId);
  const canEdit = hasMinRole(AppRole.ADMINISTRATOR);
  
  const [formData, setFormData] = useState({
    name: '',
    langsmith_api_key: '',
    agent_rate_limit: 0,
    max_file_size_mb: 0,
    agent_cors_origins: ''
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load app data on mount
  useEffect(() => {
    if (appId) {
      loadAppData();
    }
  }, [appId]);

  async function loadAppData() {
    if (!appId) return;
    
    try {
      setLoading(true);
      setError(null);
      const app = await apiService.getApp(parseInt(appId));
      setFormData({
        name: app.name || '',
        langsmith_api_key: app.langsmith_api_key || '',
        agent_rate_limit: app.agent_rate_limit || 0,
        max_file_size_mb: app.max_file_size_mb || 0,
        agent_cors_origins: app.agent_cors_origins || ''
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load app data');
      console.error('Error loading app data:', err);
    } finally {
      setLoading(false);
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!appId) return;
    
    setSaving(true);
    setError(null);

    try {
      await apiService.updateApp(parseInt(appId), {
        name: formData.name,
        langsmith_api_key: formData.langsmith_api_key,
        agent_rate_limit: formData.agent_rate_limit,
        max_file_size_mb: formData.max_file_size_mb,
        agent_cors_origins: formData.agent_cors_origins
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save settings');
      console.error('Error saving app settings:', err);
    } finally {
      setSaving(false);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = (e.target.name === 'agent_rate_limit' || e.target.name === 'max_file_size_mb') 
      ? parseInt(e.target.value) || 0 
      : e.target.value;
    
    setFormData(prev => ({
      ...prev,
      [e.target.name]: newValue
    }));
  };

  if (loading) {
    return (
      
        <div className="p-6 text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-2 text-gray-600">Loading app settings...</p>
        </div>
      
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <Alert 
          type="error" 
          title="Error Loading Settings" 
          message={error}
          onDismiss={loadAppData}
        />
      </div>
    );
  }

  return (
    
      <div className="p-6">
        <div className="max-w-2xl">
          {/* Header */}
          <div className="mb-6">
            <h2 className="text-xl font-semibold text-gray-900">General Settings</h2>
            <p className="text-gray-600">Configure basic app settings and integrations</p>
            {!canEdit && <ReadOnlyBanner userRole={userRole} minRole={AppRole.ADMINISTRATOR} />}
          </div>

          {/* Settings Form */}
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="bg-white shadow rounded-lg p-6">
              <div className="grid grid-cols-1 gap-6">
                {/* App Name */}
                <div>
                  <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-2">
                    App Name
                  </label>
                  <input
                    type="text"
                    id="name"
                    name="name"
                    value={formData.name}
                    onChange={handleChange}
                    required
                    disabled={!canEdit}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-100 disabled:cursor-not-allowed"
                    placeholder="Enter app name"
                  />
                </div>

                {/* Langsmith API Key */}
                <div>
                  <label htmlFor="langsmith_api_key" className="block text-sm font-medium text-gray-700 mb-2">
                    Langsmith API Key
                  </label>
                  <input
                    type="password"
                    id="langsmith_api_key"
                    name="langsmith_api_key"
                    value={formData.langsmith_api_key}
                    onChange={handleChange}
                    disabled={!canEdit}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-100 disabled:cursor-not-allowed"
                    placeholder="Enter Langsmith API key"
                  />
                  <p className="mt-1 text-sm text-gray-500">
                    Your Langsmith API key for monitoring and tracing
                  </p>
                </div>

                {/* Agent rate limit */}
                <div>
                    <label htmlFor="agent_rate_limit" className="block text-sm font-medium text-gray-700 mb-2">
                    Agent Rate Limit
                    </label>
                    <input
                    type="number"
                    id="agent_rate_limit"
                    name="agent_rate_limit"
                    value={formData.agent_rate_limit}
                    onChange={handleChange}
                    min="0"
                    disabled={!canEdit}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-100 disabled:cursor-not-allowed"
                    placeholder="Enter agent rate limit"
                    />
                  <p className="mt-1 text-sm text-gray-500">
                    This will limit the number of calls your agents can make per minute in your application.
                  </p>
                </div>

                {/* Maximum File Size */}
                <div>
                    <label htmlFor="max_file_size_mb" className="block text-sm font-medium text-gray-700 mb-2">
                    Maximum File Size (MB)
                    </label>
                    <input
                    type="number"
                    id="max_file_size_mb"
                    name="max_file_size_mb"
                    value={formData.max_file_size_mb}
                    onChange={handleChange}
                    min="0"
                    disabled={!canEdit}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-100 disabled:cursor-not-allowed"
                    placeholder="Enter maximum file size in MB (0 = no limit)"
                    />
                  <p className="mt-1 text-sm text-gray-500">
                    Maximum size in megabytes for files uploaded to repositories. Set to 0 for no limit.
                  </p>
                </div>

                {/* Agent CORS Origins */}
                <div>
                    <label htmlFor="agent_cors_origins" className="block text-sm font-medium text-gray-700 mb-2">
                    Agent CORS Origins
                    </label>
                    <input
                    type="text"
                    id="agent_cors_origins"
                    name="agent_cors_origins"
                    value={formData.agent_cors_origins}
                    onChange={handleChange}
                    disabled={!canEdit}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-100 disabled:cursor-not-allowed"
                    placeholder="Enter allowed CORS origins (e.g., https://example.com, https://app.example.com)"
                    />
                  <p className="mt-1 text-sm text-gray-500">
                    Comma-separated list of allowed origins for CORS requests to your agents.
                  </p>
                </div>
              </div>

              {/* Error Display */}
              {error && (
                <div className="mt-4 bg-red-50 border border-red-200 rounded-lg p-4">
                  <div className="flex">
                    <div className="flex-shrink-0">
                      <span className="text-red-400 text-xl">⚠️</span>
                    </div>
                    <div className="ml-3">
                      <h3 className="text-sm font-medium text-red-800">
                        Error Saving Settings
                      </h3>
                      <div className="mt-2 text-sm text-red-700">
                        <p>{error}</p>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Submit Button - Only show for admins */}
              {canEdit && (
                <div className="mt-6 flex items-center justify-between">
                  <div className="flex items-center">
                    {saved && (
                      <div className="flex items-center text-green-600">
                        <span className="mr-2">✓</span>
                        {' '}Settings saved successfully
                      </div>
                    )}
                  </div>
                  <button
                    type="submit"
                    disabled={saving}
                    className="bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white px-6 py-2 rounded-lg flex items-center"
                  >
                    {saving && (
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                    )}
                    {saving ? 'Saving...' : 'Save Changes'}
                  </button>
                </div>
              )}
            </div>
          </form>

          {/* Info Sections */}
          <div className="mt-8 space-y-6">
            {/* Langsmith Info */}
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
              <div className="flex">
                <div className="flex-shrink-0">
                  <span className="text-blue-400 text-xl">📊</span>
                </div>
                <div className="ml-3">
                  <h3 className="text-sm font-medium text-blue-800">
                    About Langsmith Integration
                  </h3>
                  <div className="mt-2 text-sm text-blue-700">
                    <p>
                      Langsmith provides monitoring, tracing, and debugging capabilities for your AI agents. 
                      Connect your Langsmith account to track agent performance and troubleshoot issues.
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* App Settings Info */}
            <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
              <div className="flex">
                <div className="flex-shrink-0">
                  <span className="text-gray-400 text-xl">ℹ️</span>
                </div>
                <div className="ml-3">
                  <h3 className="text-sm font-medium text-gray-800">
                    App Configuration
                  </h3>
                  <div className="mt-2 text-sm text-gray-700">
                    <p>
                      These settings affect the overall behavior of your app. 
                      The app name is used in navigation and API responses. 
                      Changes to these settings are applied immediately.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    
  );
}

export default GeneralSettingsPage; 