import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import SettingsLayout from '../../components/layout/SettingsLayout';

interface APIKey {
  key_id: number;
  name: string;
  key: string;
  app_name: string;
  created_at: string;
  last_used_at: string | null;
  is_active: boolean;
}

function APIKeysPage() {
  const { appId } = useParams();
  const [apiKeys, setApiKeys] = useState<APIKey[]>([]);
  const [loading, setLoading] = useState(true);

  // Mock data for now
  useEffect(() => {
    const mockKeys: APIKey[] = [
      {
        key_id: 1,
        name: 'Production API',
        key: 'ak_1234567890abcdef1234567890abcdef',
        app_name: 'My App',
        created_at: '2024-01-15 10:30:00',
        last_used_at: '2024-01-20 14:22:00',
        is_active: true
      },
      {
        key_id: 2,
        name: 'Development Key',
        key: 'ak_abcdef1234567890abcdef1234567890',
        app_name: 'My App',
        created_at: '2024-01-10 09:15:00',
        last_used_at: null,
        is_active: false
      }
    ];

    setTimeout(() => {
      setApiKeys(mockKeys);
      setLoading(false);
    }, 500);
  }, []);

  const toggleKeyStatus = (keyId: number) => {
    setApiKeys(keys => 
      keys.map(key => 
        key.key_id === keyId 
          ? { ...key, is_active: !key.is_active }
          : key
      )
    );
  };

  const deleteKey = (keyId: number) => {
    if (!confirm('Are you sure you want to delete this API key? This action cannot be undone.')) {
      return;
    }
    setApiKeys(keys => keys.filter(key => key.key_id !== keyId));
  };

  const maskApiKey = (key: string) => {
    return key.slice(0, 8) + '...' + key.slice(-8);
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

  return (
    <SettingsLayout>
      <div className="p-6">
        {/* Header */}
        <div className="flex justify-between items-center mb-6">
          <div>
            <h2 className="text-xl font-semibold text-gray-900">API Keys</h2>
            <p className="text-gray-600">Manage API keys for external application access</p>
          </div>
          <button className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg flex items-center">
            <span className="mr-2">+</span>
            Create New API Key
          </button>
        </div>

        {/* API Keys Table */}
        {apiKeys.length > 0 ? (
          <div className="bg-white shadow rounded-lg overflow-hidden">
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
                      <div className="text-sm font-medium text-gray-900">{apiKey.name}</div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <code className="text-sm bg-gray-100 px-2 py-1 rounded">
                        {maskApiKey(apiKey.key)}
                      </code>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {new Date(apiKey.created_at).toLocaleDateString()}
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
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                      <div className="flex space-x-2">
                        <button 
                          onClick={() => toggleKeyStatus(apiKey.key_id)}
                          className="text-yellow-600 hover:text-yellow-900"
                        >
                          {apiKey.is_active ? 'Deactivate' : 'Activate'}
                        </button>
                        <button 
                          onClick={() => deleteKey(apiKey.key_id)}
                          className="text-red-600 hover:text-red-900"
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center py-12">
            <div className="text-6xl mb-4">🔑</div>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">No API Keys</h3>
            <p className="text-gray-600 mb-6">
              Create your first API key to allow external applications to access your agents.
            </p>
            <button className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg">
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
      </div>
    </SettingsLayout>
  );
}

export default APIKeysPage; 