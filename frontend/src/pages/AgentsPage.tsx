import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { apiService } from '../services/api';

// Define the Agent type
interface Agent {
  agent_id: number;
  name: string;
  type: string;
  is_tool: boolean;
  created_at: string;
  request_count: number;
}

function AgentsPage() {
  const { appId } = useParams();
  const navigate = useNavigate();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [agentToDelete, setAgentToDelete] = useState<Agent | null>(null);

  // Load agents from the API
  useEffect(() => {
    loadAgents();
  }, [appId]);

  async function loadAgents() {
    if (!appId) return;
    
    try {
      setLoading(true);
      setError(null);
      const response = await apiService.getAgents(parseInt(appId));
      setAgents(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load agents');
      console.error('Error loading agents:', err);
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
            <p className="text-gray-600">Manage your AI agents for app {appId}</p>
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
          <p className="text-gray-600">Manage your AI agents for app {appId}</p>
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

      {/* Agents Grid */}
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
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
          {agents.map((agent) => (
            <div key={agent.agent_id} className="bg-white rounded-lg shadow-md border p-6 hover:shadow-lg transition-shadow">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center">
                  <span className="text-2xl mr-3">{getAgentTypeIcon(agent.type)}</span>
                  <div>
                    <h3 className="font-semibold text-gray-900">{agent.name}</h3>
                    <span className="text-sm text-gray-500">{getAgentTypeLabel(agent.type)}</span>
                  </div>
                </div>
                {agent.is_tool && (
                  <span className="bg-yellow-100 text-yellow-800 text-xs font-medium px-2.5 py-0.5 rounded-full">
                    Tool
                  </span>
                )}
              </div>

              <div className="space-y-2 mb-4">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Created:</span>
                  <span className="text-gray-900">{formatDate(agent.created_at)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Requests:</span>
                  <span className="text-gray-900">{agent.request_count}</span>
                </div>
              </div>

              <div className="flex space-x-2">
                <button
                  onClick={() => handleEditAgent(agent.agent_id)}
                  className="flex-1 bg-blue-600 hover:bg-blue-700 text-white text-sm py-2 px-3 rounded-lg"
                >
                  Edit
                </button>
                <button
                  onClick={() => handleDeleteAgent(agent)}
                  className="bg-red-600 hover:bg-red-700 text-white text-sm py-2 px-3 rounded-lg"
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
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