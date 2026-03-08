import { useState, useEffect, useMemo } from 'react';
import { apiService } from '../../services/api';
import Alert from '../../components/ui/Alert';

interface SystemSetting {
  key: string;
  value: string | null;
  type: string;
  category: string;
  description: string | null;
  updated_at: string | null;
  resolved_value: any;
  source: 'env' | 'db' | 'default';
}

function SystemSettingsPage() {
  const [settings, setSettings] = useState<SystemSetting[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<string>('marketplace');
  const [editingValues, setEditingValues] = useState<Record<string, string>>({});
  const [savingKeys, setSavingKeys] = useState<Set<string>>(new Set());

  useEffect(() => {
    loadSettings();
  }, []);

  async function loadSettings() {
    try {
      setLoading(true);
      setError(null);
      const data = await apiService.fetchSystemSettings();
      setSettings(data);
      
      // Determine available categories from the data
      const categoriesSet = new Set<string>(data.map((s: SystemSetting) => s.category));
      if (categoriesSet.size === 0) {
        setActiveTab('marketplace');
      } else if (!categoriesSet.has(activeTab)) {
        const firstCategory = Array.from(categoriesSet)[0] ?? 'marketplace';
        setActiveTab(firstCategory);
      }
    } catch (error) {
      console.error('Failed to load settings:', error);
      setError(`Failed to load system settings: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setLoading(false);
    }
  }

  // Group settings by category
  const settingsByCategory = useMemo(() => {
    const grouped: Record<string, SystemSetting[]> = {};
    settings.forEach((setting) => {
      if (!grouped[setting.category]) {
        grouped[setting.category] = [];
      }
      grouped[setting.category].push(setting);
    });
    return grouped;
  }, [settings]);

  const categories = useMemo(() => Object.keys(settingsByCategory).sort((a, b) => a.localeCompare(b)), [settingsByCategory]);
  const currentCategorySettings = settingsByCategory[activeTab] || [];

  // Initialize editing values from current settings
  useEffect(() => {
    const initialValues: Record<string, string> = {};
    settings.forEach((setting) => {
      initialValues[setting.key] = setting.value ?? String(setting.resolved_value ?? '');
    });
    setEditingValues(initialValues);
  }, [settings]);

  async function handleSaveSetting(setting: SystemSetting) {
    const newValue = editingValues[setting.key];
    
    // Client-side validation
    if (!validateValue(newValue, setting.type)) {
      setError(`Invalid ${setting.type} value for ${setting.key}`);
      return;
    }

    try {
      setSavingKeys((prev) => new Set(prev).add(setting.key));
      setError(null);
      setSuccess(null);
      
      await apiService.updateSystemSetting(setting.key, newValue);
      setSuccess(`Setting "${setting.key}" updated successfully`);
      
      // Reload settings to get the updated resolved values
      await loadSettings();
    } catch (err) {
      console.error('Failed to save setting:', err);
      setError(`Failed to save setting: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setSavingKeys((prev) => {
        const newSet = new Set(prev);
        newSet.delete(setting.key);
        return newSet;
      });
    }
  }

  async function handleResetSetting(setting: SystemSetting) {
    if (!confirm(`Reset "${setting.key}" to its default value?`)) {
      return;
    }

    try {
      setSavingKeys((prev) => new Set(prev).add(setting.key));
      setError(null);
      setSuccess(null);
      
      await apiService.resetSystemSetting(setting.key);
      setSuccess(`Setting "${setting.key}" reset to default`);
      
      // Reload settings to get the updated values
      await loadSettings();
    } catch (err) {
      console.error('Failed to reset setting:', err);
      setError(`Failed to reset setting: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setSavingKeys((prev) => {
        const newSet = new Set(prev);
        newSet.delete(setting.key);
        return newSet;
      });
    }
  }

  function validateValue(value: string, type: string): boolean {
    if (type === 'integer') {
      return /^-?\d+$/.test(value);
    }
    if (type === 'boolean') {
      return ['true', 'false'].includes(value.toLowerCase());
    }
    if (type === 'string') {
      return true;
    }
    return true;
  }

  function getSourceBadgeColor(source: 'env' | 'db' | 'default'): string {
    switch (source) {
      case 'env':
        return 'bg-blue-100 text-blue-800';
      case 'db':
        return 'bg-green-100 text-green-800';
      case 'default':
        return 'bg-gray-100 text-gray-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  }

  function renderInputField(setting: SystemSetting) {
    const currentValue = editingValues[setting.key] ?? '';
    const isReadOnly = setting.source === 'env';

    if (setting.type === 'boolean') {
      const boolValue = currentValue.toLowerCase() === 'true';
      return (
        <input
          type="checkbox"
          checked={boolValue}
          onChange={(e) =>
            setEditingValues((prev) => ({
              ...prev,
              [setting.key]: e.target.checked ? 'true' : 'false',
            }))
          }
          disabled={isReadOnly}
          className="h-4 w-4 rounded border-gray-300 text-blue-600 cursor-pointer disabled:cursor-not-allowed disabled:opacity-50"
        />
      );
    }

    if (setting.type === 'integer') {
      return (
        <input
          type="number"
          value={currentValue}
          onChange={(e) =>
            setEditingValues((prev) => ({
              ...prev,
              [setting.key]: e.target.value,
            }))
          }
          disabled={isReadOnly}
          className="px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-100 disabled:cursor-not-allowed"
          placeholder={String(setting.resolved_value ?? '')}
        />
      );
    }

    // String or unknown type - render as text input
    return (
      <input
        type="text"
        value={currentValue}
        onChange={(e) =>
          setEditingValues((prev) => ({
            ...prev,
            [setting.key]: e.target.value,
          }))
        }
        disabled={isReadOnly}
        className="px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-100 disabled:cursor-not-allowed w-full"
        placeholder={String(setting.resolved_value ?? '')}
      />
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        <span className="ml-2">Loading system settings...</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {success && <Alert type="success" message={success} onDismiss={() => setSuccess(null)} />}
      {error && <Alert type="error" message={error} onDismiss={() => setError(null)} />}

      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">System Settings</h1>
        <p className="text-gray-600">Manage global system configuration</p>
      </div>

      {/* Tabs */}
      <div className="bg-white rounded-lg shadow">
        <div className="border-b border-gray-200">
          <div className="flex overflow-x-auto">
            {categories.map((category) => (
              <button
                key={category}
                onClick={() => setActiveTab(category)}
                className={`px-4 py-3 font-medium text-sm whitespace-nowrap ${
                  activeTab === category
                    ? 'text-blue-600 border-b-2 border-blue-600'
                    : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                {category.charAt(0).toUpperCase() + category.slice(1)}
              </button>
            ))}
          </div>
        </div>

        {/* Settings List */}
        <div className="divide-y divide-gray-200">
          {currentCategorySettings.length === 0 ? (
            <div className="px-6 py-8 text-center text-gray-500">
              <p>No settings found in this category.</p>
            </div>
          ) : (
            currentCategorySettings.map((setting) => (
              <div key={setting.key} className="px-6 py-4 hover:bg-gray-50">
                <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
                  {/* Left: Label and Description */}
                  <div className="lg:col-span-1">
                    <div className="flex items-start gap-2">
                      <div className="flex-1">
                        <p className="font-medium text-gray-900">{setting.description || setting.key}</p>
                        <p className="text-xs text-gray-500 mt-1">Key: {setting.key}</p>
                        <div className="flex items-center gap-2 mt-2">
                          <span
                            className={`inline-block px-2 py-1 text-xs font-medium rounded ${getSourceBadgeColor(
                              setting.source
                            )}`}
                          >
                            {setting.source === 'env' ? 'Environment Variable' : setting.source}
                          </span>
                          <span className="text-xs text-gray-500">{setting.type}</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Center: Value Display */}
                  <div className="lg:col-span-1">
                    <p className="text-xs text-gray-600 mb-1">Current Value</p>
                    <p className="font-mono text-sm text-gray-900 break-words">
                      {String(setting.resolved_value ?? 'N/A')}
                    </p>
                  </div>

                  {/* Right: Input and Actions */}
                  <div className="lg:col-span-1">
                    <div className="space-y-2">
                      <div>
                        {renderInputField(setting)}
                      </div>
                      <div className="flex gap-2">
                        <button
                          onClick={() => handleSaveSetting(setting)}
                          disabled={
                            setting.source === 'env' ||
                            savingKeys.has(setting.key) ||
                            editingValues[setting.key] === (setting.value ?? String(setting.resolved_value ?? ''))
                          }
                          className="flex-1 px-3 py-2 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
                        >
                          {savingKeys.has(setting.key) ? 'Saving...' : 'Save'}
                        </button>
                        {setting.source === 'db' && (
                          <button
                            onClick={() => handleResetSetting(setting)}
                            disabled={savingKeys.has(setting.key)}
                            className="flex-1 px-3 py-2 text-xs bg-gray-200 text-gray-800 rounded hover:bg-gray-300 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
                          >
                            Reset
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

export default SystemSettingsPage;
