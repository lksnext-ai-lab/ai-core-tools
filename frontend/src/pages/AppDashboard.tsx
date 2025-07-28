import { useParams, Link } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { apiService } from '../services/api';

interface App {
  app_id: number;
  name: string;
  created_at: string;
  owner_id: number;
  owner_name?: string;
  owner_email?: string;
  role: string;
  langsmith_configured: boolean;
  
  // Entity counts for display
  agent_count: number;
  repository_count: number;
  domain_count: number;
  silo_count: number;
  collaborator_count: number;
}

function AppDashboard() {
  const { appId } = useParams();
  const [currentApp, setCurrentApp] = useState<App | null>(null);
  const [loading, setLoading] = useState(true);

  // Fetch app data when component mounts
  useEffect(() => {
    if (appId) {
      loadAppData();
    }
  }, [appId]);

  async function loadAppData() {
    if (!appId) return;
    
    try {
      setLoading(true);
      const apps = await apiService.getApps();
      const app = apps.find((a: App) => a.app_id === parseInt(appId));
      setCurrentApp(app || null);
    } catch (error) {
      console.error('Failed to load app data:', error);
      setCurrentApp(null);
    } finally {
      setLoading(false);
    }
  }

  // Get real entity counts from loaded app data
  const appStats = {
    agents: currentApp?.agent_count || 0,
    repositories: currentApp?.repository_count || 0,
    silos: currentApp?.silo_count || 0,
    domains: currentApp?.domain_count || 0,
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        <span className="ml-2">Loading app...</span>
      </div>
    );
  }

  if (!currentApp) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <div className="flex">
          <span className="text-red-400 text-xl mr-3">⚠️</span>
          <div>
            <h3 className="text-sm font-medium text-red-800">App Not Found</h3>
            <p className="text-sm text-red-600 mt-1">The requested app could not be found.</p>
            <Link 
              to="/apps"
              className="mt-2 text-sm text-red-600 hover:text-red-800 underline"
            >
              Back to Apps
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{currentApp.name}</h1>
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
            <span className={`text-sm font-medium px-2.5 py-0.5 rounded-full ${
              appStats.agents > 0 
                ? 'bg-blue-100 text-blue-800' 
                : 'bg-gray-100 text-gray-500'
            }`}>
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
            <span className={`text-sm font-medium px-2.5 py-0.5 rounded-full ${
              appStats.repositories > 0 
                ? 'bg-green-100 text-green-800' 
                : 'bg-gray-100 text-gray-500'
            }`}>
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
            <span className={`text-sm font-medium px-2.5 py-0.5 rounded-full ${
              appStats.silos > 0 
                ? 'bg-yellow-100 text-yellow-800' 
                : 'bg-gray-100 text-gray-500'
            }`}>
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
            <span className={`text-sm font-medium px-2.5 py-0.5 rounded-full ${
              appStats.domains > 0 
                ? 'bg-purple-100 text-purple-800' 
                : 'bg-gray-100 text-gray-500'
            }`}>
              {appStats.domains}
            </span>
          </div>
          <h3 className="text-lg font-semibold text-gray-900 mb-2">Domains</h3>
          <p className="text-gray-600 text-sm mb-4">Web scraping</p>
          <p className="text-gray-600 text-sm mb-4">
            Configure web domains for data extraction and content monitoring.
          </p>
          <Link 
            to={`/apps/${appId}/domains`}
            className="block w-full bg-purple-600 hover:bg-purple-700 text-white text-center py-2 px-4 rounded-lg"
          >
            Manage Domains →
          </Link>
        </div>

        {/* Settings Card */}
        <div className="bg-white rounded-lg shadow-md border p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="w-12 h-12 bg-gray-100 rounded-lg flex items-center justify-center">
              <span className="text-2xl">⚙️</span>
            </div>
            <span className="bg-gray-100 text-gray-800 text-sm font-medium px-2.5 py-0.5 rounded-full">
              Settings
            </span>
          </div>
          <h3 className="text-lg font-semibold text-gray-900 mb-2">App Settings</h3>
          <p className="text-gray-600 text-sm mb-4">Configuration</p>
          <p className="text-gray-600 text-sm mb-4">
            Configure AI services, embedding models, and application preferences.
          </p>
          <Link 
            to={`/apps/${appId}/settings`}
            className="block w-full bg-gray-600 hover:bg-gray-700 text-white text-center py-2 px-4 rounded-lg"
          >
            Open Settings →
          </Link>
        </div>
      </div>
    </div>
  );
}

export default AppDashboard; 