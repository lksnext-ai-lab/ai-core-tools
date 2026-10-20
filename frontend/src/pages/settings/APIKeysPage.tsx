import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
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
import { MESSAGES, errorMessage } from '../../constants/messages';
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
      setError(err instanceof Error ? err.message : 'Failed to load API keys');
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
      setError(err instanceof Error ? err.message : 'Failed to load API keys');
      console.error('Error loading API keys:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(keyId: number) {
    if (!appId) return;

    const target = apiKeys.find((k) => k.key_id === keyId);
    const ok = await confirm({
      title: MESSAGES.CONFIRM_DELETE_TITLE('API key'),
      message: target
        ? `Are you sure you want to delete "${target.name}"? Any application using it will lose access immediately.`
        : MESSAGES.CONFIRM_DELETE_MESSAGE('API key'),
      variant: 'danger',
      confirmLabel: 'Delete',
    });
    if (!ok) return;

    const result = await mutate(
      () => apiService.deleteAPIKey(Number.parseInt(appId), keyId),
      {
        loading: MESSAGES.DELETING('API key'),
        success: MESSAGES.DELETED('API key'),
        error: (err) => errorMessage(err, MESSAGES.DELETE_FAILED('API key')),
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
    const verb = willActivate ? 'Activating' : 'Deactivating';

    const result = await mutate(
      () => apiService.toggleAPIKey(Number.parseInt(appId), keyId),
      {
        loading: `${verb} API key…`,
        success: willActivate ? 'API key activated' : 'API key deactivated',
        error: (err) => errorMessage(err, 'Failed to toggle API key'),
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
      setError(err instanceof Error ? err.message : 'Failed to load API key details');
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
        loading: isUpdate ? MESSAGES.UPDATING('API key') : MESSAGES.CREATING('API key'),
        success: isUpdate ? MESSAGES.UPDATED('API key') : MESSAGES.CREATED('API key'),
        error: (err) => errorMessage(err, MESSAGES.SAVE_FAILED('API key')),
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
          <Title variant="titSecundario" titulo="API Keys" subtitulo="Manage API keys for external application access" />
        </div>

        <LoadingState variant="page" message="Loading API keys..." />
      </div>

      
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <Title variant="titSecundario" titulo="API Keys" subtitulo="Manage API keys for external application access" />
        </div>

        <Alert type="error" message={error} onDismiss={() => loadAPIKeys()} />
      </div>

    );
  }

  return (
    
      <div className="p-6">
        {/* Header */}
        <div className="flex justify-between items-center mb-6">
          <Title variant="titSecundario" titulo="API Keys" subtitulo="Manage API keys for external application access" />
          {canEdit && (
            <ButtonApp
              label="Create New API Key"
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
          keyExtractor={(apiKey) => apiKey.key_id.toString()}
          columns={[
            {
              header: 'Name',
              render: (apiKey) => (
                <div className="flex items-center">
                  <BackgroundImage icon={KeyRound} size={28} iconSize={14} variant="marron" className="mr-2" />
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
              header: 'Key',
              render: (apiKey) => <Badge label={maskApiKey(apiKey.key_preview)} variant="default" />
            },
            {
              header: 'Created',
              render: (apiKey) => apiKey.created_at ? new Date(apiKey.created_at).toLocaleDateString() : 'N/A',
              className: 'px-6 py-4 whitespace-nowrap text-sm text-fg-secondary dark:text-fg-secondary-dark'
            },
            {
              header: 'Last Used',
              render: (apiKey) => apiKey.last_used_at ? new Date(apiKey.last_used_at).toLocaleDateString() : 'Never',
              className: 'px-6 py-4 whitespace-nowrap text-sm text-fg-secondary dark:text-fg-secondary-dark'
            },
            {
              header: 'Status',
              render: (apiKey) => (
                <Badge label={apiKey.is_active ? 'Active' : 'Inactive'} variant={apiKey.is_active ? 'success' : 'error'} />
              )
            },
            {
              header: 'Actions',
              className: 'relative',
              render: (apiKey) => (
                canEdit ? (
                  <ActionDropdown
                    actions={[
                      {
                        label: 'Edit',
                        onClick: () => { void handleEditKey(apiKey.key_id); },
                        icon: <Pencil className="w-4 h-4" />,
                        variant: 'primary'
                      },
                      {
                        label: apiKey.is_active ? 'Deactivate' : 'Activate',
                        onClick: () => { void handleToggle(apiKey.key_id); },
                        icon: apiKey.is_active ? <PauseCircle className="w-4 h-4" /> : <PlayCircle className="w-4 h-4" />,
                        variant: apiKey.is_active ? 'warning' : 'success'
                      },
                      {
                        label: 'Delete',
                        onClick: () => { void handleDelete(apiKey.key_id); },
                        icon: <Trash2 className="w-4 h-4" />,
                        variant: 'danger'
                      }
                    ]}
                    size="sm"
                  />
                ) : (
                  <span className="text-gray-400 text-sm">View only</span>
                )
              )
            }
          ]}
          emptyIcon={<KeyRound className="w-10 h-10 text-gray-300" />}
          emptyMessage="No API Keys"
          emptySubMessage="Create your first API key to enable programmatic access to your application."
          loading={loading}
        />

        {!loading && apiKeys.length === 0 && (
          <div className="text-center py-6">
            <p className="text-fg-secondary dark:text-fg-secondary-dark mb-6">
              Create your first API key to allow external applications to access your agents.
            </p>
            <ButtonApp
              label="Create First API Key"
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
          title="Security Notice"
          className="mt-6"
          message="Keep your API keys secure and never share them publicly. Deactivate or delete keys that are no longer needed. Monitor usage regularly to detect any unauthorized access."
        />

        {/* Create/Edit Modal */}
        <Modal
          isOpen={isModalOpen}
          onClose={handleCloseModal}
          title={editingKey ? 'Edit API Key' : 'Create New API Key'}
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