import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { apiService } from '../../services/api';
import { LoadingState } from '../../components/ui/LoadingState';
import { ErrorState } from '../../components/ui/ErrorState';
import { useConfirm } from '../../contexts/ConfirmContext';
import { useApiMutation } from '../../hooks/useApiMutation';
import { errorMessage, MESSAGES } from '../../constants/messages';
import { Title } from '../../components/ui/Title';
import { Tabs } from '../../components/ui/Tabs';
import { ButtonApp } from '../../components/ui/ButtonApp';
import { FormField } from '../../components/ui/FormField';
import CardApp from '../../components/ui/CardApp';

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
    void loadSettings();
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
        <FormField
          id={setting.key}
          type="checkbox"
          ariaLabel='{setting.description || setting.key}'
          checked={boolValue}
          onChange={(e) =>
            setEditingValues((prev) => ({
              ...prev,
              [setting.key]: e.target.checked ? 'true' : 'false',
            }))
          }
          disabled={isReadOnly}
        />
      );
    }

    if (setting.type === 'integer') {
      return (
        <FormField
          id={setting.key}
          type="number"
          ariaLabel={setting.description || setting.key}
          value={currentValue}
          onChange={(e) =>
            setEditingValues((prev) => ({
              ...prev,
              [setting.key]: e.target.value,
            }))
          }
          disabled={isReadOnly}
          placeholder={String(setting.resolved_value ?? '')}
        />
      );
    }

    return (
      <FormField
        id={setting.key}
        type="text"
        ariaLabel={setting.description || setting.key}
        value={currentValue}
        onChange={(e) =>
          setEditingValues((prev) => ({
            ...prev,
            [setting.key]: e.target.value,
          }))
        }
        disabled={isReadOnly}
        placeholder={String(setting.resolved_value ?? '')}
      />
    );
  }

  if (loading) {
    return(
      <div className="space-y-6">
              <div className="flex items-center justify-between">
                <Title variant='titPrincipal' titulo='System Settings' subtitulo='Manage global system configuration'></Title>
              </div>
              <LoadingState variant="page" message="Loading system settings..." />
            </div>
    );
  }

  if (loadError) {
    return <ErrorState error={loadError} onRetry={loadSettings} />;
  }

  return (
    <div className="">
      <Title variant='titPrincipal' titulo='System Settings' subtitulo='Manage global system configuration'></Title>

      <div>
        <Tabs
          tabs={categories.map((category) => ({
            id: category,
            label: category.charAt(0).toUpperCase() + category.slice(1),
          }))}
          activeTab={activeTab}
          onChange={setActiveTab}
        />

        <CardApp variant="white" className="divide-y divide-btCard-border dark:divide-btCard-border-dark mt-2">
          {currentCategorySettings.length === 0 ? (
            <div className="rounded-md border border-dashed border-line px-6 py-9 text-center text-sm text-fg-tertiary dark:border-line-dark dark:text-fg-tertiary-dark">
              No settings found in this category.
            </div>
          ) : (
            currentCategorySettings.map((setting) => {
              const currentValue = editingValues[setting.key] ?? '';
              const isUnchanged = currentValue === (setting.value ?? String(setting.resolved_value ?? ''));
              const isSaving = savingKeys.has(setting.key);

              return (
                <div key={setting.key} className="px-6 py-4">
                  <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_320px] lg:gap-8">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="break-all font-mono text-[13px] font-medium text-fg dark:text-fg-dark">
                          {setting.key}
                        </p>
                        <span
                          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-medium ${getSourceBadgeColor(
                            setting.source,
                          )}`}
                        >
                          {setting.source === 'env' ? 'Environment Variable' : setting.source}
                        </span>
                        <span className="text-[11px] text-fg-faint dark:text-fg-faint-dark">{setting.type}</span>
                      </div>
                      <p className="mt-1.5 text-[13px] leading-relaxed text-fg-secondary dark:text-fg-secondary-dark">
                        {setting.description || setting.key}
                      </p>
                    </div>

                    <div className="space-y-2">
                      <div>{renderInputField(setting)}</div>
                      <div id={`${setting.key}-help`} className="space-y-1 text-xs text-fg-tertiary dark:text-fg-tertiary-dark">
                        <p>
                          Current Value:{' '}
                          <span className="break-words font-mono text-fg dark:text-fg-dark">
                            {String(setting.resolved_value ?? 'N/A')}
                          </span>
                        </p>
                      </div>
                      {setting.source !== 'env' && (
                        <div className="flex justify-end gap-2 pt-1">
                          {setting.source === 'db' && (
                            <ButtonApp
                              label="Reset"
                              onClick={() => handleResetSetting(setting)}
                              disabled={isSaving}
                              variant="muted"
                              size="small"
                            />
                          )}
                          <ButtonApp
                            label={isSaving ? 'Saving…' : 'Save'}
                            onClick={() => handleSaveSetting(setting)}
                            disabled={isSaving || isUnchanged}
                            variant="primary"
                            size="small"
                          />
                        </div>
                      )}
                    </div>

                    
                  </div>
                </div>
              );
            })
          )}
        </CardApp>
      </div>
    </div>
  );
}

export default SystemSettingsPage;
