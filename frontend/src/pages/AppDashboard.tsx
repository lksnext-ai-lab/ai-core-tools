import { useParams, Link } from 'react-router-dom';

function AppDashboard() {
  const { appId } = useParams();

  // Mock data - will be replaced with real API calls
  const appStats = {
    agents: 6,
    repositories: 1,
    silos: 1,
    domains: 0,
    api_keys: 0
  };

  const appName = "My App"; // Will come from API

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{appName}</h1>
          <p className="text-gray-600">App Dashboard - Manage your AI components and data</p>
        </div>
        <Link 
          to="/apps" 
          className="flex items-center px-4 py-2 bg-gray-100 hover:bg-gray-200 rounded-lg text-gray-700"
        >
          <span className="mr-2">←</span>
          Back to Apps
        </Link>
      </div>

      {/* Main Feature Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
        {/* Agents Card */}
        <div className="bg-white rounded-lg shadow-md border p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center">
              <span className="text-2xl">🤖</span>
            </div>
            <span className="bg-blue-100 text-blue-800 text-sm font-medium px-2.5 py-0.5 rounded-full">
              {appStats.agents}
            </span>
          </div>
          <h3 className="text-lg font-semibold text-gray-900 mb-2">AI Agents</h3>
          <p className="text-gray-600 text-sm mb-4">Intelligent automation</p>
          <p className="text-gray-600 text-sm mb-4">
            Create and manage intelligent agents that can handle complex tasks and workflows.
          </p>
          <Link 
            to={`/apps/${appId}/agents`}
            className="block w-full bg-blue-600 hover:bg-blue-700 text-white text-center py-2 px-4 rounded-lg"
          >
            Manage Agents →
          </Link>
        </div>

        {/* Repositories Card */}
        <div className="bg-white rounded-lg shadow-md border p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="w-12 h-12 bg-green-100 rounded-lg flex items-center justify-center">
              <span className="text-2xl">📁</span>
            </div>
            <span className="bg-green-100 text-green-800 text-sm font-medium px-2.5 py-0.5 rounded-full">
              {appStats.repositories}
            </span>
          </div>
          <h3 className="text-lg font-semibold text-gray-900 mb-2">Repositories</h3>
          <p className="text-gray-600 text-sm mb-4">Document storage</p>
          <p className="text-gray-600 text-sm mb-4">
            Store and organize documents, files, and resources for your AI applications.
          </p>
          <Link 
            to={`/apps/${appId}/repositories`}
            className="block w-full bg-green-600 hover:bg-green-700 text-white text-center py-2 px-4 rounded-lg"
          >
            Manage Repositories →
          </Link>
        </div>

        {/* Silos Card */}
        <div className="bg-white rounded-lg shadow-md border p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="w-12 h-12 bg-yellow-100 rounded-lg flex items-center justify-center">
              <span className="text-2xl">🗄️</span>
            </div>
            <span className="bg-yellow-100 text-yellow-800 text-sm font-medium px-2.5 py-0.5 rounded-full">
              {appStats.silos}
            </span>
          </div>
          <h3 className="text-lg font-semibold text-gray-900 mb-2">Silos</h3>
          <p className="text-gray-600 text-sm mb-4">Vector databases</p>
          <p className="text-gray-600 text-sm mb-4">
            Vector storage and retrieval systems for semantic search and AI context.
          </p>
          <Link 
            to={`/apps/${appId}/silos`}
            className="block w-full bg-yellow-600 hover:bg-yellow-700 text-white text-center py-2 px-4 rounded-lg"
          >
            Manage Silos →
          </Link>
        </div>

        {/* Domains Card */}
        <div className="bg-white rounded-lg shadow-md border p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="w-12 h-12 bg-purple-100 rounded-lg flex items-center justify-center">
              <span className="text-2xl">🌐</span>
            </div>
            <span className="bg-purple-100 text-purple-800 text-sm font-medium px-2.5 py-0.5 rounded-full">
              {appStats.domains}
            </span>
          </div>
          <h3 className="text-lg font-semibold text-gray-900 mb-2">Domains</h3>
          <p className="text-gray-600 text-sm mb-4">Web scraping</p>
          <p className="text-gray-600 text-sm mb-4">
            Configure and manage web domains for automated content extraction.
          </p>
          <Link 
            to={`/apps/${appId}/domains`}
            className="block w-full bg-purple-600 hover:bg-purple-700 text-white text-center py-2 px-4 rounded-lg"
          >
            Manage Domains →
          </Link>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="bg-white rounded-lg shadow-md border p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">
          <span className="mr-2">⚡</span>
          Quick Actions
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <Link 
            to={`/apps/${appId}/agents/new`}
            className="flex items-center justify-center px-4 py-3 border-2 border-blue-200 text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
          >
            <span className="mr-2">➕</span>
            New Agent
          </Link>
          <Link 
            to={`/apps/${appId}/repositories/new`}
            className="flex items-center justify-center px-4 py-3 border-2 border-green-200 text-green-600 hover:bg-green-50 rounded-lg transition-colors"
          >
            <span className="mr-2">➕</span>
            New Repository
          </Link>
          <Link 
            to={`/apps/${appId}/silos/new`}
            className="flex items-center justify-center px-4 py-3 border-2 border-yellow-200 text-yellow-600 hover:bg-yellow-50 rounded-lg transition-colors"
          >
            <span className="mr-2">➕</span>
            New Silo
          </Link>
          <Link 
            to={`/apps/${appId}/settings/ai-services`}
            className="flex items-center justify-center px-4 py-3 border-2 border-gray-200 text-gray-600 hover:bg-gray-50 rounded-lg transition-colors"
          >
            <span className="mr-2">⚙️</span>
            Settings
          </Link>
        </div>
      </div>
    </div>
  );
}

export default AppDashboard; 