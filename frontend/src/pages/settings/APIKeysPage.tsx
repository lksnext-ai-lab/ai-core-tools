import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import SettingsLayout from '../../components/layout/SettingsLayout';
import Modal from '../../components/ui/Modal';
import APIKeyForm from '../../components/forms/APIKeyForm';
import APIKeyDisplayModal from '../../components/ui/APIKeyDisplayModal';
import { apiService } from '../../services/api';
import ActionDropdown from '../../components/ui/ActionDropdown';
import type { ActionItem } from '../../components/ui/ActionDropdown';

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
  const [apiKeys, setApiKeys] = useState<APIKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingKey, setEditingKey] = useState<any>(null);
  const [showKeyModal, setShowKeyModal] = useState(false);
  const [createdKey, setCreatedKey] = useState<any>(null);

  // Load API keys from the API
  useEffect(() => {
    loadAPIKeys();
  }, [appId]);

  async function loadAPIKeys() {
    if (!appId) return;
    
    try {
      setLoading(true);
      setError(null);
      const response = await apiService.getAPIKeys(parseInt(appId));
      setApiKeys(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load API keys');
      console.error('Error loading API keys:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(keyId: number) {
    if (!confirm('Are you sure you want to delete this API key? This action cannot be undone.')) {
      return;
    }

    if (!appId) return;

    try {
      await apiService.deleteAPIKey(parseInt(appId), keyId);
      // Remove from local state
      setApiKeys(apiKeys.filter(k => k.key_id !== keyId));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete API key');
      console.error('Error deleting API key:', err);
    }
  }

  async function handleToggle(keyId: number) {
    if (!appId) return;

    try {
      const response = await apiService.toggleAPIKey(parseInt(appId), keyId);
      // Update local state
      setApiKeys(apiKeys.map(key => 
        key.key_id === keyId 
          ? { ...key, is_active: response.is_active }
          : key
      ));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to toggle API key');
      console.error('Error toggling API key:', err);
    }
  }

  function handleCreateKey() {
    setEditingKey(null);
    setIsModalOpen(true);
  }

  async function handleEditKey(keyId: number) {
    if (!appId) return;
    
    try {
      const key = await apiService.getAPIKey(parseInt(appId), keyId);
      setEditingKey(key);
      setIsModalOpen(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load API key details');
      console.error('Error loading API key:', err);
    }
  }

  async function handleSaveKey(data: any) {
    if (!appId) return;

    try {
      if (editingKey && editingKey.key_id !== 0) {
        // Update existing key
        await apiService.updateAPIKey(parseInt(appId), editingKey.key_id, data);
        await loadAPIKeys(); // Reload the list
        setIsModalOpen(false);
        setEditingKey(null);
      } else {
        // Create new key
        const response = await apiService.createAPIKey(parseInt(appId), data);
        
        // Show the API key value in a special modal
        setCreatedKey(response);
        setShowKeyModal(true);
        setIsModalOpen(false);
        setEditingKey(null);
        
        // Reload the list to include the new key
        await loadAPIKeys();
      }
    } catch (err) {
      throw new Error(err instanceof Error ? err.message : 'Failed to save API key');
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
      <SettingsLayout>
        <div className="p-6 text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-2 text-gray-600">Loading API keys...</p>
        </div>
      </SettingsLayout>
    );
  }

  if (error) {
    return (
      <SettingsLayout>
        <div className="p-6">
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <p className="text-red-600">Error: {error}</p>
            <button 
              onClick={() => loadAPIKeys()}
              className="mt-2 text-red-800 hover:text-red-900 underline"
            >
              Try again
            </button>
          </div>
        </div>
      </SettingsLayout>
    );
  }

  return (
    <SettingsLayout>
      <div className="p-6">
        {/* Header */}
        <div className="flex justify-between items-center mb-6">
          <div>
            <h2 className="text-xl font-semibold text-gray-900">API Keys</h2>
            <p className="text-gray-600">Manage API keys for external application access</p>
          </div>
          <button 
            onClick={handleCreateKey}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg flex items-center"
          >
            <span className="mr-2">+</span>
            Create New API Key
          </button>
        </div>

        {/* API Keys Table */}
        {apiKeys.length > 0 ? (
          <div className="bg-white shadow rounded-lg overflow-visible">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Name
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Key
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Created
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Last Used
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Status
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {apiKeys.map((apiKey) => (
                    <tr key={apiKey.key_id} className="hover:bg-gray-50">
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="flex items-center">
                          <span className="text-blue-400 text-xl mr-3">🔑</span>
                          <div className="text-sm font-medium text-gray-900">{apiKey.name}</div>
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <code className="text-sm bg-gray-100 px-2 py-1 rounded">
                          {maskApiKey(apiKey.key_preview)}
                        </code>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {apiKey.created_at ? new Date(apiKey.created_at).toLocaleDateString() : 'N/A'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {apiKey.last_used_at 
                          ? new Date(apiKey.last_used_at).toLocaleDateString()
                          : 'Never'
                        }
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                          apiKey.is_active 
                            ? 'bg-green-100 text-green-800' 
                            : 'bg-red-100 text-red-800'
                        }`}>
                          {apiKey.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-medium relative">
                        <ActionDropdown
                          actions={[
                            {
                              label: 'Edit',
                              onClick: () => handleEditKey(apiKey.key_id),
                              icon: '✏️',
                              variant: 'primary'
                            },
                            {
                              label: apiKey.is_active ? 'Deactivate' : 'Activate',
                              onClick: () => handleToggle(apiKey.key_id),
                              icon: apiKey.is_active ? '⏸️' : '▶️',
                              variant: apiKey.is_active ? 'warning' : 'success'
                            },
                            {
                              label: 'Delete',
                              onClick: () => handleDelete(apiKey.key_id),
                              icon: '🗑️',
                              variant: 'danger'
                            }
                          ]}
                          size="sm"
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          <div className="text-center py-12">
            <div className="text-6xl mb-4">🔑</div>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">No API Keys</h3>
            <p className="text-gray-600 mb-6">
              Create your first API key to allow external applications to access your agents.
            </p>
            <button 
              onClick={handleCreateKey}
              className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg"
            >
              Create First API Key
            </button>
          </div>
        )}

        {/* Security Notice */}
        <div className="mt-6 bg-yellow-50 border border-yellow-200 rounded-lg p-4">
          <div className="flex">
            <div className="flex-shrink-0">
              <span className="text-yellow-400 text-xl">⚠️</span>
            </div>
            <div className="ml-3">
              <h3 className="text-sm font-medium text-yellow-800">
                Security Notice
              </h3>
              <div className="mt-2 text-sm text-yellow-700">
                <p>
                  Keep your API keys secure and never share them publicly. 
                  Deactivate or delete keys that are no longer needed. 
                  Monitor usage regularly to detect any unauthorized access.
                </p>
              </div>
            </div>
          </div>
        </div>

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
    </SettingsLayout>
  );
}

export default APIKeysPage; 