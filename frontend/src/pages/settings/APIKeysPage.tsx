import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { KeyRound, Pencil, PauseCircle, PlayCircle, Plus, Trash2 } from 'lucide-react';
import Modal from '../../components/ui/Modal';
import APIKeyForm from '../../components/forms/APIKeyForm';
import APIKeyDisplayModal from '../../components/ui/APIKeyDisplayModal';
import { apiService } from '../../services/api';
import ActionDropdown from '../../components/ui/ActionDropdown';
import { useSettingsCache } from '../../contexts/SettingsCacheContext';
import { useAppRole } from '../../hooks/useAppRole';
import { AppRole } from '../../types/roles';
import ReadOnlyBanner from '../../components/ui/ReadOnlyBanner';
import Alert from '../../components/ui/Alert';
import Table from '../../components/ui/Table';
import ButtonApp from '../../components/ui/ButtonApp';
import { Badge } from '../../components/ui/Badge';
import { useConfirm } from '../../contexts/ConfirmContext';
import { useApiMutation } from '../../hooks/useApiMutation';
import { errorMessage } from '../../constants/messages';
import { LoadingState } from '../../components/ui/LoadingState';
import Title from '../../components/ui/Title';
import BackgroundImage from '../../components/ui/BackgroundImage';

interface APIKey {
  key_id: number;
  name: string;
  key_preview: string;
  created_at: string;
  last_used_at: string | null;
  is_active: boolean;
}

function APIKeysPage() {
  const { appId } = useParams();
  const { t, i18n } = useTranslation('common');
  const settingsCache = useSettingsCache();
  const { hasMinRole, userRole } = useAppRole(appId);
  const canEdit = hasMinRole(AppRole.ADMINISTRATOR);
  const confirm = useConfirm();
  const mutate = useApiMutation();
  const [apiKeys, setApiKeys] = useState<APIKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingKey, setEditingKey] = useState<any>(null);
  const [showKeyModal, setShowKeyModal] = useState(false);
  const [createdKey, setCreatedKey] = useState<any>(null);

  // Load API keys from cache or API
  useEffect(() => {
    void loadAPIKeys();
  }, [appId]);

  async function loadAPIKeys() {
    if (!appId) return;
    
    // Check if we have cached data first
    const cachedData = settingsCache.getAPIKeys(appId);
    if (cachedData) {
      setApiKeys(cachedData);
      setLoading(false);
      return;
    }
    
    // If no cache, load from API
    try {
      setLoading(true);
      setError(null);
      const response = await apiService.getAPIKeys(Number.parseInt(appId));
      setApiKeys(response);
      // Cache the response
      settingsCache.setAPIKeys(appId, response);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('apiKeysPage.loadFailed'));
      console.error('Error loading API keys:', err);
    } finally {
      setLoading(false);
    }
  }

  async function forceReloadAPIKeys() {
    if (!appId) return;
    
    try {
      setLoading(true);
      setError(null);
      const response = await apiService.getAPIKeys(Number.parseInt(appId));
      setApiKeys(response);
      // Cache the response
      settingsCache.setAPIKeys(appId, response);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('apiKeysPage.loadFailed'));
      console.error('Error loading API keys:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(keyId: number) {
    if (!appId) return;

    const target = apiKeys.find((k) => k.key_id === keyId);
    const ok = await confirm({
      title: t('servicesManager.confirmDeleteTitle', { entity: t('apiKeysPage.entity') }),
      message: target
        ? t('apiKeysPage.confirmDeleteNamed', { name: target.name })
        : t('servicesManager.confirmDeleteMessage', { entity: t('apiKeysPage.entity') }),
      variant: 'danger',
      confirmLabel: t('apiKeysPage.actions.delete'),
      cancelLabel: t('cancel'),
    });
    if (!ok) return;

    const result = await mutate(
      () => apiService.deleteAPIKey(Number.parseInt(appId), keyId),
      {
        loading: t('apiKeysPage.deleting'),
        success: t('apiKeysPage.deleted'),
        error: (err) => errorMessage(err, t('apiKeysPage.deleteFailed')),
      },
    );
    if (result === undefined) return;

    const newApiKeys = apiKeys.filter((k) => k.key_id !== keyId);
    setApiKeys(newApiKeys);
    settingsCache.setAPIKeys(appId, newApiKeys);
  }

  async function handleToggle(keyId: number) {
    if (!appId) return;

    const target = apiKeys.find((k) => k.key_id === keyId);
    const willActivate = !target?.is_active;
    const result = await mutate(
      () => apiService.toggleAPIKey(Number.parseInt(appId), keyId),
      {
        loading: willActivate ? t('apiKeysPage.activating') : t('apiKeysPage.deactivating'),
        success: willActivate ? t('apiKeysPage.activated') : t('apiKeysPage.deactivated'),
        error: (err) => errorMessage(err, t('apiKeysPage.toggleFailed')),
      },
    );
    if (result === undefined) return;

    const updatedApiKeys = apiKeys.map((key) =>
      key.key_id === keyId ? { ...key, is_active: result.is_active } : key,
    );
    setApiKeys(updatedApiKeys);
    settingsCache.setAPIKeys(appId, updatedApiKeys);
  }

  function handleCreateKey() {
    setEditingKey(null);
    setIsModalOpen(true);
  }

  async function handleEditKey(keyId: number) {
    if (!appId) return;
    
    try {
      const key = await apiService.getAPIKey(Number.parseInt(appId), keyId);
      setEditingKey(key);
      setIsModalOpen(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('apiKeysPage.loadDetailsFailed'));
      console.error('Error loading API key:', err);
    }
  }

  async function handleSaveKey(data: any) {
    if (!appId) return;

    const isUpdate = Boolean(editingKey && editingKey.key_id !== 0);

    const result = await mutate(
      () =>
        isUpdate
          ? apiService.updateAPIKey(Number.parseInt(appId), editingKey.key_id, data)
          : apiService.createAPIKey(Number.parseInt(appId), data),
      {
        loading: isUpdate ? t('apiKeysPage.updating') : t('apiKeysPage.creating'),
        success: isUpdate ? t('apiKeysPage.updated') : t('apiKeysPage.created'),
        error: (err) => errorMessage(err, t('apiKeysPage.saveFailed')),
      },
    );
    if (result === undefined) return;

    setIsModalOpen(false);
    setEditingKey(null);

    if (isUpdate) {
      try {
        await loadAPIKeys();
      } catch (err) {
        console.error('Refetch after update failed:', err);
      }
    } else {
      // New key — surface the secret once via APIKeyDisplayModal, then refresh list.
      setCreatedKey(result);
      setShowKeyModal(true);
      settingsCache.invalidateAPIKeys(appId);
      try {
        await forceReloadAPIKeys();
      } catch (err) {
        console.error('Refetch after create failed:', err);
      }
    }
  }

  function handleCloseModal() {
    setIsModalOpen(false);
    setEditingKey(null);
  }

  function handleCloseKeyModal() {
    setShowKeyModal(false);
    setCreatedKey(null);
  }

  const maskApiKey = (key: string) => {
    return key || '***...***';
  };

  if (loading) {
    return (
      
     <div className="space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <Title variant="titSecundario" titulo={t('apiKeysPage.title')} subtitulo={t('apiKeysPage.subtitle')} />
        </div>

        <LoadingState variant="page" message={t('apiKeysPage.loading')} />
      </div>

      
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <Title variant="titSecundario" titulo={t('apiKeysPage.title')} subtitulo={t('apiKeysPage.subtitle')} />
        </div>

        <Alert type="error" message={error} onDismiss={() => loadAPIKeys()} />
      </div>

    );
  }

  return (
    
      <div className="p-6">
        {/* Header */}
        <div className="flex justify-between items-center mb-6">
          <Title variant="titSecundario" titulo={t('apiKeysPage.title')} subtitulo={t('apiKeysPage.subtitle')} />
          {canEdit && (
            <ButtonApp
              label={t('apiKeysPage.createKey')}
              onClick={handleCreateKey}
              variant="primary"
              size="medium"
              icon={<Plus className="h-4 w-4" aria-hidden="true" />}
            />
          )}
        </div>
        
        {/* Read-only banner for non-admins */}
        {!canEdit && <ReadOnlyBanner userRole={userRole} minRole={AppRole.ADMINISTRATOR} />}

        {/* API Keys Table */}
        <Table
          data={apiKeys}
          stickyEdgeColumns
          keyExtractor={(apiKey) => apiKey.key_id.toString()}
          columns={[
            {
              header: t('apiKeysPage.columns.name'),
              render: (apiKey) => (
                <div className="flex items-center">
                  <BackgroundImage icon={KeyRound} size={34} iconSize={17} variant="marron" className="mr-2" />
                  {canEdit ? (
                    <button
                      type="button"
                      className="text-sm font-medium text-fg dark:text-fg-dark transition-colors text-left"
                      onClick={() => void handleEditKey(apiKey.key_id)}
                    >
                      {apiKey.name}
                    </button>
                  ) : (
                    <span className="text-sm font-medium text-fg dark:text-fg-dark">
                      {apiKey.name}
                    </span>
                  )}
                </div>
              )
            },
            {
              header: t('apiKeysPage.columns.key'),
              render: (apiKey) => <Badge label={maskApiKey(apiKey.key_preview)} variant="default" />
            },
            {
              header: t('apiKeysPage.columns.created'),
              render: (apiKey) => apiKey.created_at ? new Date(apiKey.created_at).toLocaleDateString(i18n.resolvedLanguage) : t('apiKeysPage.notAvailable'),
              className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark'
            },
            {
              header: t('apiKeysPage.columns.lastUsed'),
              render: (apiKey) => apiKey.last_used_at ? new Date(apiKey.last_used_at).toLocaleDateString(i18n.resolvedLanguage) : t('apiKeysPage.never'),
              className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark'
            },
            {
              header: t('apiKeysPage.columns.status'),
              render: (apiKey) => (
                <Badge label={apiKey.is_active ? t('apiKeysPage.status.active') : t('apiKeysPage.status.inactive')} variant={apiKey.is_active ? 'success' : 'error'} />
              )
            },
            {
              header: t('apiKeysPage.columns.actions'),
              sticky: 'right',
              className: 'relative',
              render: (apiKey) => (
                canEdit ? (
                  <ActionDropdown
                    actions={[
                      {
                        label: t('apiKeysPage.actions.edit'),
                        onClick: () => { void handleEditKey(apiKey.key_id); },
                        icon: <Pencil className="w-4 h-4" />,
                        variant: 'primary'
                      },
                      {
                        label: apiKey.is_active ? t('apiKeysPage.actions.deactivate') : t('apiKeysPage.actions.activate'),
                        onClick: () => { void handleToggle(apiKey.key_id); },
                        icon: apiKey.is_active ? <PauseCircle className="w-4 h-4" /> : <PlayCircle className="w-4 h-4" />,
                        variant: apiKey.is_active ? 'warning' : 'success'
                      },
                      {
                        label: t('apiKeysPage.actions.delete'),
                        onClick: () => { void handleDelete(apiKey.key_id); },
                        icon: <Trash2 className="w-4 h-4" />,
                        variant: 'danger'
                      }
                    ]}
                    size="sm"
                    triggerAriaLabel={t('apiKeysPage.actions.menuForKey', { name: apiKey.name })}
                  />
                ) : (
                  <span className="text-gray-400 text-sm">{t('apiKeysPage.viewOnly')}</span>
                )
              )
            }
          ]}
          emptyIcon={<BackgroundImage icon={KeyRound} size={64} iconSize={32} />}
          emptyMessage={t('apiKeysPage.empty.title')}
          emptySubMessage={t('apiKeysPage.empty.subtitle')}
          loading={loading}
        />

        {!loading && apiKeys.length === 0 && (
          <div className="text-center py-6">
            <ButtonApp
              label={t('apiKeysPage.createFirstKey')}
              onClick={handleCreateKey}
              variant="primary"
              size="medium"
              icon={<Plus className="h-4 w-4" aria-hidden="true" />}
            />
          </div>
        )}

        {/* Security Notice */}
        <Alert
          type="warning"
          title={t('apiKeysPage.security.title')}
          className="mt-6"
          message={t('apiKeysPage.security.message')}
        />

        {/* Create/Edit Modal */}
        <Modal
          isOpen={isModalOpen}
          onClose={handleCloseModal}
          title={editingKey ? t('apiKeysPage.editTitle') : t('apiKeysPage.createTitle')}
        >
          <APIKeyForm
            apiKey={editingKey}
            onSubmit={handleSaveKey}
            onCancel={handleCloseModal}
          />
        </Modal>

        {/* API Key Display Modal */}
        <APIKeyDisplayModal
          isOpen={showKeyModal}
          onClose={handleCloseKeyModal}
          apiKey={createdKey}
        />
      </div>
    
  );
}

export default APIKeysPage; 