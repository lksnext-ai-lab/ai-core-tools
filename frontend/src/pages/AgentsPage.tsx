import { useParams } from 'react-router-dom';

function AgentsPage() {
  const { appId } = useParams();

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Agents</h1>
          <p className="text-gray-600">Manage your AI agents for app {appId}</p>
        </div>
        <button className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg">
          Create Agent
        </button>
      </div>

      {/* Placeholder Content */}
      <div className="bg-white rounded-lg shadow-md border p-8 text-center">
        <div className="text-6xl mb-4">🤖</div>
        <h3 className="text-lg font-semibold text-gray-900 mb-2">Agents Management</h3>
        <p className="text-gray-600 mb-4">
          This page will show the list of agents and allow you to manage them.
        </p>
        <p className="text-sm text-gray-500">
          Coming soon! This will include the full agents CRUD interface.
        </p>
      </div>
    </div>
  );
}

export default AgentsPage; 