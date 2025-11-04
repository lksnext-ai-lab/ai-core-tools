import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { apiService } from '../services/api';
import ActionDropdown from '../components/ui/ActionDropdown';

// Define the Agent type
interface Agent {
  agent_id: number;
  name: string;
  type: string;
  is_tool: boolean;
  created_at: string;
  request_count: number;
  description?: string;
  service_id?: number;
  ai_service?: {
    name: string;
    model_name: string;
    provider: string;
  };
}

// Define the App type
interface App {
  app_id: number;
  name: string;
}

function AgentsPage() {
  const { appId } = useParams();
  const navigate = useNavigate();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [app, setApp] = useState<App | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [agentToDelete, setAgentToDelete] = useState<Agent | null>(null);

  useEffect(() => {
    loadData();
  }, [appId]);

  async function loadData() {
    if (!appId) return;
    
    try {
      setLoading(true);
      setError(null);
      
      const [agentsResponse, appResponse] = await Promise.all([
        apiService.getAgents(parseInt(appId)),
        apiService.getApp(parseInt(appId))
      ]);
      
      setAgents(agentsResponse);
      setApp(appResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data');
      console.error('Error loading data:', err);
    } finally {
      setLoading(false);
    }
  }

  const handleCreateAgent = () => {
    navigate(`/apps/${appId}/agents/0`);
  };

  const handleEditAgent = (agentId: number) => {
    navigate(`/apps/${appId}/agents/${agentId}`);
  };

  const handlePlayground = (agentId: number) => {
    navigate(`/apps/${appId}/agents/${agentId}/playground`);
  };

  const handleDeleteAgent = (agent: Agent) => {
    setAgentToDelete(agent);
    setShowDeleteModal(true);
  };

  const confirmDeleteAgent = async () => {
    if (!agentToDelete || !appId) return;

    try {
      await apiService.deleteAgent(parseInt(appId), agentToDelete.agent_id);
      setAgents(agents.filter(a => a.agent_id !== agentToDelete.agent_id));
      setShowDeleteModal(false);
      setAgentToDelete(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete agent');
      console.error('Error deleting agent:', err);
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString();
  };

  const getAgentTypeIcon = (type: string) => {
    switch (type) {
      case 'ocr_agent':
        return '📷';
      case 'agent':
      default:
        return '🤖';
    }
  };

  const getAgentTypeLabel = (type: string) => {
    switch (type) {
      case 'ocr_agent':
        return 'OCR Agent';
      case 'agent':
      default:
        return 'AI Agent';
    }
  };

  if (loading) {
    return (
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Agents</h1>
            <p className="text-gray-600">Manage your AI agents for app {app?.name || appId}</p>
          </div>
        </div>

        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          <span className="ml-2">Loading agents...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Agents</h1>
          <p className="text-gray-600">Manage your AI agents for app {app?.name || appId}</p>
        </div>
        <button 
          onClick={handleCreateAgent}
          className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg flex items-center"
        >
          <span className="mr-2">+</span>
          Create Agent
        </button>
      </div>

      {/* Error Message */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <div className="flex">
            <span className="text-red-400 text-xl mr-3">⚠️</span>
            <div>
              <h3 className="text-sm font-medium text-red-800">Error</h3>
              <p className="text-sm text-red-600 mt-1">{error}</p>
            </div>
          </div>
        </div>
      )}

      {agents.length === 0 ? (
        <div className="bg-white rounded-lg shadow-md border p-8 text-center">
          <div className="text-6xl mb-4">🤖</div>
          <h3 className="text-lg font-semibold text-gray-900 mb-2">No Agents Yet</h3>
          <p className="text-gray-600 mb-4">
            Create your first AI agent to get started with intelligent automation.
          </p>
          <button 
            onClick={handleCreateAgent}
            className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg"
          >
            Create Your First Agent
          </button>
        </div>
      ) : (
        <div className="bg-white rounded-lg shadow-md border overflow-visible">
          <div className="overflow-x-auto overflow-visible">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Agent
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Description
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Type
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    AI Service
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Usage
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Created
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {agents.map((agent) => (
                  <tr key={agent.agent_id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center">
                        <div className="flex-shrink-0 h-10 w-10">
                          <div className="h-10 w-10 rounded-lg bg-blue-100 flex items-center justify-center">
                            <span className="text-blue-600 text-lg">{getAgentTypeIcon(agent.type)}</span>
                          </div>
                        </div>
                        <div className="ml-4">
                          <div className="text-sm font-medium text-gray-900">
                            <Link 
                              to={`/apps/${appId}/agents/${agent.agent_id}`} 
                              className="text-sm font-medium text-gray-900 hover:text-blue-600 transition-colors"
                              >
                                {agent.name}
                            </Link>
                          </div>
                          {agent.is_tool && (
                            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
                              Tool 
                            </span>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="text-sm text-gray-900 max-w-xs">
                        {agent.description ? (
                          <div className="truncate" title={agent.description}>
                            {agent.description}
                          </div>
                        ) : (
                          <span className="text-gray-400 italic">No description</span>
                        )}
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className="inline-flex px-2 py-1 text-xs font-semibold rounded-full bg-gray-100 text-gray-800">
                        {getAgentTypeLabel(agent.type)}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      {agent.ai_service ? (
                        <div className="text-sm">
                          <div className="font-medium text-gray-900">
                            {agent.ai_service.name}
                          </div>
                          <div className="text-xs text-gray-500">
                            {agent.ai_service.model_name} • {agent.ai_service.provider}
                          </div>
                        </div>
                      ) : (
                        <span className="text-gray-400 italic text-sm">No AI Service</span>
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className="inline-flex items-center px-2 py-1 text-xs font-semibold rounded-full bg-green-100 text-green-800">
                        <span className="w-2 h-2 bg-green-400 rounded-full mr-2"></span>
                        Active
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="text-sm text-gray-900">
                        <div className="flex items-center">
                          <span className="font-medium">{agent.request_count}</span>
                          <span className="text-gray-500 ml-1">requests</span>
                        </div>
                        {agent.request_count > 0 && (
                          <div className="text-xs text-gray-500">
                            Last used: {formatDate(agent.created_at)}
                          </div>
                        )}
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {formatDate(agent.created_at)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                      <ActionDropdown
                        actions={[
                          {
                            label: 'Playground',
                            onClick: () => handlePlayground(agent.agent_id),
                            icon: '🎮',
                            variant: 'warning'
                          },
                          {
                            label: 'Edit',
                            onClick: () => handleEditAgent(agent.agent_id),
                            icon: '✏️',
                            variant: 'primary'
                          },
                          {
                            label: 'Delete',
                            onClick: () => handleDeleteAgent(agent),
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
      )}

      {/* Delete Confirmation Modal */}
      {showDeleteModal && agentToDelete && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-md w-full mx-4">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Delete Agent</h3>
            <p className="text-gray-600 mb-6">
              Are you sure you want to delete "{agentToDelete.name}"? This action cannot be undone.
            </p>
            <div className="flex space-x-3">
              <button
                onClick={() => {
                  setShowDeleteModal(false);
                  setAgentToDelete(null);
                }}
                className="flex-1 bg-gray-300 hover:bg-gray-400 text-gray-800 py-2 px-4 rounded-lg"
              >
                Cancel
              </button>
              <button
                onClick={confirmDeleteAgent}
                className="flex-1 bg-red-600 hover:bg-red-700 text-white py-2 px-4 rounded-lg"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default AgentsPage; 