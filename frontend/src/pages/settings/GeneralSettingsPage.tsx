import { useState } from 'react';
import { useParams } from 'react-router-dom';
import SettingsLayout from '../../components/layout/SettingsLayout';

function GeneralSettingsPage() {
  const { appId } = useParams();
  const [formData, setFormData] = useState({
    name: 'My App',
    langsmith_api_key: ''
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);

    // Simulate API call
    setTimeout(() => {
      setSaving(false);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    }, 1000);
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData(prev => ({
      ...prev,
      [e.target.name]: e.target.value
    }));
  };

  return (
    <SettingsLayout>
      <div className="p-6">
        <div className="max-w-2xl">
          {/* Header */}
          <div className="mb-6">
            <h2 className="text-xl font-semibold text-gray-900">General Settings</h2>
            <p className="text-gray-600">Configure basic app settings and integrations</p>
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
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
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
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    placeholder="Enter Langsmith API key"
                  />
                  <p className="mt-1 text-sm text-gray-500">
                    Your Langsmith API key for monitoring and tracing
                  </p>
                </div>
              </div>

              {/* Submit Button */}
              <div className="mt-6 flex items-center justify-between">
                <div className="flex items-center">
                  {saved && (
                    <div className="flex items-center text-green-600">
                      <span className="mr-2">✓</span>
                      Settings saved successfully
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
    </SettingsLayout>
  );
}

export default GeneralSettingsPage; 