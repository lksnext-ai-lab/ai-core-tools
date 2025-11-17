import React, { useState, useEffect } from 'react';

export interface HelloWorldAdminPageProps {
  welcomeMessage?: string;
}

interface PluginStats {
  totalVisits: number;
  lastVisit: Date;
  averageSessionTime: string;
  activeUsers: number;
}

/**
 * Hello World Admin Page Component
 * 
 * This is a sample admin page component that demonstrates:
 * - Admin-specific functionality
 * - Data visualization
 * - Settings management
 * - Plugin administration features
 */
export const HelloWorldAdminPage: React.FC<HelloWorldAdminPageProps> = ({ 
  welcomeMessage = 'Welcome to the Hello World Plugin Admin!' 
}) => {
  const [stats, setStats] = useState<PluginStats>({
    totalVisits: 0,
    lastVisit: new Date(),
    averageSessionTime: '0m 0s',
    activeUsers: 0
  });
  
  const [settings, setSettings] = useState({
    enableNotifications: true,
    autoRefresh: false,
    theme: 'light',
    language: 'en'
  });

  const [isLoading, setIsLoading] = useState(true);

  // Simulate loading data
  useEffect(() => {
    const timer = setTimeout(() => {
      setStats({
        totalVisits: Math.floor(Math.random() * 1000) + 100,
        lastVisit: new Date(),
        averageSessionTime: `${Math.floor(Math.random() * 10) + 1}m ${Math.floor(Math.random() * 60)}s`,
        activeUsers: Math.floor(Math.random() * 50) + 5
      });
      setIsLoading(false);
    }, 1000);

    return () => clearTimeout(timer);
  }, []);

  const handleSettingChange = (key: string, value: any) => {
    setSettings(prev => ({
      ...prev,
      [key]: value
    }));
  };

  const handleResetStats = () => {
    setStats({
      totalVisits: 0,
      lastVisit: new Date(),
      averageSessionTime: '0m 0s',
      activeUsers: 0
    });
  };

  const handleExportData = () => {
    const data = {
      stats,
      settings,
      exportDate: new Date().toISOString()
    };
    
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'hello-world-plugin-data.json';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Loading admin data...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-6xl mx-auto">
        {/* Header Section */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">
            {welcomeMessage}
          </h1>
          <p className="text-gray-600">
            Manage and monitor your Hello World plugin
          </p>
        </div>

        {/* Stats Overview */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
          <div className="bg-white rounded-lg shadow p-6">
            <div className="flex items-center">
              <div className="p-2 bg-blue-100 rounded-lg">
                <span className="text-2xl">👥</span>
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-600">Total Visits</p>
                <p className="text-2xl font-semibold text-gray-900">{stats.totalVisits}</p>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-lg shadow p-6">
            <div className="flex items-center">
              <div className="p-2 bg-green-100 rounded-lg">
                <span className="text-2xl">🕐</span>
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-600">Avg. Session</p>
                <p className="text-2xl font-semibold text-gray-900">{stats.averageSessionTime}</p>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-lg shadow p-6">
            <div className="flex items-center">
              <div className="p-2 bg-yellow-100 rounded-lg">
                <span className="text-2xl">👤</span>
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-600">Active Users</p>
                <p className="text-2xl font-semibold text-gray-900">{stats.activeUsers}</p>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-lg shadow p-6">
            <div className="flex items-center">
              <div className="p-2 bg-purple-100 rounded-lg">
                <span className="text-2xl">📅</span>
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-600">Last Visit</p>
                <p className="text-sm font-semibold text-gray-900">
                  {stats.lastVisit.toLocaleTimeString()}
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Main Content Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Settings Panel */}
          <div className="bg-white rounded-lg shadow">
            <div className="px-6 py-4 border-b border-gray-200">
              <h2 className="text-xl font-semibold text-gray-900">Plugin Settings</h2>
            </div>
            <div className="p-6 space-y-6">
              <div>
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={settings.enableNotifications}
                    onChange={(e) => handleSettingChange('enableNotifications', e.target.checked)}
                    className="rounded border-gray-300 text-blue-600 shadow-sm focus:border-blue-300 focus:ring focus:ring-blue-200 focus:ring-opacity-50"
                  />
                  <span className="ml-3 text-sm font-medium text-gray-700">
                    Enable Notifications
                  </span>
                </label>
              </div>

              <div>
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={settings.autoRefresh}
                    onChange={(e) => handleSettingChange('autoRefresh', e.target.checked)}
                    className="rounded border-gray-300 text-blue-600 shadow-sm focus:border-blue-300 focus:ring focus:ring-blue-200 focus:ring-opacity-50"
                  />
                  <span className="ml-3 text-sm font-medium text-gray-700">
                    Auto Refresh Data
                  </span>
                </label>
              </div>

              <div>
                <label htmlFor="theme-select" className="block text-sm font-medium text-gray-700 mb-2">
                  Theme
                </label>
                <select
                  id="theme-select"
                  value={settings.theme}
                  onChange={(e) => handleSettingChange('theme', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="light">Light</option>
                  <option value="dark">Dark</option>
                  <option value="auto">Auto</option>
                </select>
              </div>

              <div>
                <label htmlFor="language-select" className="block text-sm font-medium text-gray-700 mb-2">
                  Language
                </label>
                <select
                  id="language-select"
                  value={settings.language}
                  onChange={(e) => handleSettingChange('language', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="en">English</option>
                  <option value="es">Spanish</option>
                  <option value="fr">French</option>
                  <option value="de">German</option>
                </select>
              </div>
            </div>
          </div>

          {/* Actions Panel */}
          <div className="bg-white rounded-lg shadow">
            <div className="px-6 py-4 border-b border-gray-200">
              <h2 className="text-xl font-semibold text-gray-900">Admin Actions</h2>
            </div>
            <div className="p-6 space-y-4">
              <button
                onClick={handleResetStats}
                className="w-full bg-red-600 hover:bg-red-700 text-white font-semibold py-2 px-4 rounded-lg transition-colors"
              >
                Reset Statistics
              </button>
              
              <button
                onClick={handleExportData}
                className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2 px-4 rounded-lg transition-colors"
              >
                Export Data
              </button>
              
              <button
                onClick={() => window.location.reload()}
                className="w-full bg-gray-600 hover:bg-gray-700 text-white font-semibold py-2 px-4 rounded-lg transition-colors"
              >
                Refresh Page
              </button>
            </div>
          </div>
        </div>

        {/* Plugin Information */}
        <div className="mt-8 bg-gradient-to-r from-indigo-500 to-purple-600 rounded-lg shadow-lg p-6 text-white">
          <h2 className="text-2xl font-semibold mb-4">Plugin Administration</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div>
              <h3 className="font-semibold mb-2">Plugin Status</h3>
              <div className="flex items-center">
                <div className="w-3 h-3 bg-green-400 rounded-full mr-2"></div>
                <span>Active & Running</span>
              </div>
            </div>
            <div>
              <h3 className="font-semibold mb-2">Last Updated</h3>
              <p>{new Date().toLocaleDateString()}</p>
            </div>
            <div>
              <h3 className="font-semibold mb-2">Version</h3>
              <p>1.0.0</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
