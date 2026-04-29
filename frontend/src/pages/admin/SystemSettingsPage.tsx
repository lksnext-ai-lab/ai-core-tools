import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { apiService } from '../../services/api';
import { LoadingState } from '../../components/ui/LoadingState';
import { ErrorState } from '../../components/ui/ErrorState';
import { useConfirm } from '../../contexts/ConfirmContext';
import { useApiMutation } from '../../hooks/useApiMutation';
import { errorMessage, MESSAGES } from '../../constants/messages';

interface SystemSetting {
  readonly key: string;
  readonly value: string | null;
  readonly type: string;
  readonly category: string;
  readonly description: string | null;
  readonly updated_at: string | null;
  readonly resolved_value: any;
  readonly source: 'env' | 'db' | 'default';
}

function validateValue(value: string, type: string): boolean {
  if (type === 'integer') {
    return /^-?\d+$/.test(value);
  }
  if (type === 'boolean') {
    return ['true', 'false'].includes(value.toLowerCase());
  }
  return true;
}

function getSourceBadgeColor(source: SystemSetting['source']): string {
  switch (source) {
    case 'env':
      return 'bg-blue-100 text-blue-800';
    case 'db':
      return 'bg-green-100 text-green-800';
    default:
      return 'bg-gray-100 text-gray-800';
  }
}

function SystemSettingsPage() {
  const confirm = useConfirm();
  const mutate = useApiMutation();

  const [settings, setSettings] = useState<SystemSetting[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<string>('marketplace');
  const [editingValues, setEditingValues] = useState<Record<string, string>>({});
  const [savingKeys, setSavingKeys] = useState<Set<string>>(new Set());

  const loadSettings = useCallback(async () => {
    try {
      setLoading(true);
      setLoadError(null);
      const data = (await apiService.fetchSystemSettings()) as SystemSetting[];
      setSettings(data);

      const categoriesSet = new Set<string>(data.map((s) => s.category));
      setActiveTab((prev) => {
        if (categoriesSet.size === 0) return 'marketplace';
        if (categoriesSet.has(prev)) return prev;
        return Array.from(categoriesSet)[0] ?? 'marketplace';
      });
    } catch (err) {
      setLoadError(errorMessage(err, 'Failed to load system settings'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

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

  const categories = useMemo(
    () => Object.keys(settingsByCategory).sort((a, b) => a.localeCompare(b)),
    [settingsByCategory],
  );
  const currentCategorySettings = settingsByCategory[activeTab] || [];

  useEffect(() => {
    const initialValues: Record<string, string> = {};
    settings.forEach((setting) => {
      initialValues[setting.key] = setting.value ?? String(setting.resolved_value ?? '');
    });
    setEditingValues(initialValues);
  }, [settings]);

  const updateSavingKeys = useCallback((key: string, op: 'add' | 'remove') => {
    setSavingKeys((prev) => {
      const next = new Set(prev);
      if (op === 'add') next.add(key);
      else next.delete(key);
      return next;
    });
  }, []);

  async function handleSaveSetting(setting: SystemSetting) {
    const newValue = editingValues[setting.key];
    if (!validateValue(newValue, setting.type)) {
      toast.error(`Invalid ${setting.type} value for ${setting.key}`);
      return;
    }

    updateSavingKeys(setting.key, 'add');
    const result = await mutate(
      () => apiService.updateSystemSetting(setting.key, newValue),
      {
        loading: MESSAGES.SAVING(`"${setting.key}"`),
        success: MESSAGES.UPDATED(`Setting "${setting.key}"`),
        error: (err) => errorMessage(err, MESSAGES.SAVE_FAILED(`"${setting.key}"`)),
      },
    );
    updateSavingKeys(setting.key, 'remove');
    if (result === undefined) return;
    await loadSettings();
  }

  async function handleResetSetting(setting: SystemSetting) {
    const ok = await confirm({
      title: 'Reset setting?',
      message: `Reset "${setting.key}" to its default value?`,
      variant: 'warning',
      confirmLabel: 'Reset',
    });
    if (!ok) return;

    updateSavingKeys(setting.key, 'add');
    const result = await mutate(
      () => apiService.resetSystemSetting(setting.key),
      {
        loading: `Resetting "${setting.key}"…`,
        success: `Setting "${setting.key}" reset to default`,
        error: (err) => errorMessage(err, `Failed to reset setting "${setting.key}"`),
      },
    );
    updateSavingKeys(setting.key, 'remove');
    if (result === undefined) return;
    await loadSettings();
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
    return <LoadingState message="Loading system settings..." />;
  }

  if (loadError) {
    return <ErrorState error={loadError} onRetry={loadSettings} />;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">System Settings</h1>
        <p className="text-gray-600">Manage global system configuration</p>
      </div>

      <div className="bg-white rounded-lg shadow">
        <div className="border-b border-gray-200">
          <div className="flex overflow-x-auto">
            {categories.map((category) => (
              <button
                key={category}
                type="button"
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

        <div className="divide-y divide-gray-200">
          {currentCategorySettings.length === 0 ? (
            <div className="px-6 py-8 text-center text-gray-500">
              No settings found in this category.
            </div>
          ) : (
            currentCategorySettings.map((setting) => {
              const currentValue = editingValues[setting.key] ?? '';
              const isUnchanged = currentValue === (setting.value ?? String(setting.resolved_value ?? ''));
              const isSaving = savingKeys.has(setting.key);

              return (
                <div key={setting.key} className="px-6 py-4 hover:bg-gray-50">
                  <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
                    <div className="lg:col-span-1">
                      <p className="font-medium text-gray-900">
                        {setting.description || setting.key}
                      </p>
                      <p className="text-xs text-gray-500 mt-1">Key: {setting.key}</p>
                      <div className="flex items-center gap-2 mt-2">
                        <span
                          className={`inline-block px-2 py-1 text-xs font-medium rounded ${getSourceBadgeColor(
                            setting.source,
                          )}`}
                        >
                          {setting.source === 'env' ? 'Environment Variable' : setting.source}
                        </span>
                        <span className="text-xs text-gray-500">{setting.type}</span>
                      </div>
                    </div>

                    <div className="lg:col-span-1">
                      <p className="text-xs text-gray-600 mb-1">Current Value</p>
                      <p className="font-mono text-sm text-gray-900 break-words">
                        {String(setting.resolved_value ?? 'N/A')}
                      </p>
                    </div>

                    <div className="lg:col-span-1">
                      <div className="space-y-2">
                        <div>{renderInputField(setting)}</div>
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={() => handleSaveSetting(setting)}
                            disabled={setting.source === 'env' || isSaving || isUnchanged}
                            className="flex-1 px-3 py-2 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
                          >
                            {isSaving ? 'Saving…' : 'Save'}
                          </button>
                          {setting.source === 'db' && (
                            <button
                              type="button"
                              onClick={() => handleResetSetting(setting)}
                              disabled={isSaving}
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
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}

export default SystemSettingsPage;
