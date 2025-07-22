import { type ReactNode } from 'react';
import { Link, useParams, useLocation } from 'react-router-dom';

interface AppLayoutProps {
  children: ReactNode;
}

function AppLayout({ children }: AppLayoutProps) {
  const { appId } = useParams();
  const location = useLocation();

  // Mock app data for now - will be replaced with real API call
  const currentApp = {
    app_id: parseInt(appId || '0'),
    name: 'My App'
  };

  const isActive = (path: string) => {
    return location.pathname.startsWith(path) ? 'text-blue-600 bg-blue-50' : 'text-gray-700 hover:text-blue-600 hover:bg-gray-50';
  };

  return (
    <div className="min-h-screen bg-gray-50 flex">
      {/* Sidebar */}
      <div className="w-64 bg-white shadow-sm border-r border-gray-200 flex flex-col">
        {/* Logo/Brand */}
        <div className="p-6 border-b border-gray-200">
          <Link to="/apps" className="flex items-center">
            <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center mr-3">
              <span className="text-white font-bold text-sm">M</span>
            </div>
            <span className="text-xl font-bold text-gray-900">Mattin AI</span>
          </Link>
        </div>

        {/* App Context Section */}
        {appId && (
          <div className="px-6 py-4 border-b border-gray-200 bg-gray-50">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-medium text-gray-900">{currentApp.name}</h3>
                <p className="text-xs text-gray-600">App Dashboard</p>
              </div>
              <Link 
                to="/apps" 
                className="text-xs text-blue-600 hover:text-blue-800"
              >
                Change
              </Link>
            </div>
          </div>
        )}

        {/* Navigation */}
        <nav className="flex-1 p-6">
          {appId ? (
            // App-specific navigation (when inside an app)
            <div className="space-y-6">
              {/* Main Features */}
              <div>
                <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
                  Main Features
                </h4>
                <ul className="space-y-2">
                  <li>
                    <Link
                      to={`/apps/${appId}`}
                      className={`flex items-center px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                        location.pathname === `/apps/${appId}` ? 'text-blue-600 bg-blue-50' : 'text-gray-700 hover:text-blue-600 hover:bg-gray-50'
                      }`}
                    >
                      <span className="mr-3">🏠</span>
                      Dashboard
                    </Link>
                  </li>
                  <li>
                    <Link
                      to={`/apps/${appId}/agents`}
                      className={`flex items-center px-3 py-2 rounded-md text-sm font-medium transition-colors ${isActive(`/apps/${appId}/agents`)}`}
                    >
                      <span className="mr-3">🤖</span>
                      Agents
                    </Link>
                  </li>
                  <li>
                    <Link
                      to={`/apps/${appId}/repositories`}
                      className={`flex items-center px-3 py-2 rounded-md text-sm font-medium transition-colors ${isActive(`/apps/${appId}/repositories`)}`}
                    >
                      <span className="mr-3">📁</span>
                      Repositories
                    </Link>
                  </li>
                  <li>
                    <Link
                      to={`/apps/${appId}/silos`}
                      className={`flex items-center px-3 py-2 rounded-md text-sm font-medium transition-colors ${isActive(`/apps/${appId}/silos`)}`}
                    >
                      <span className="mr-3">🗄️</span>
                      Silos
                    </Link>
                  </li>
                  <li>
                    <Link
                      to={`/apps/${appId}/domains`}
                      className={`flex items-center px-3 py-2 rounded-md text-sm font-medium transition-colors ${isActive(`/apps/${appId}/domains`)}`}
                    >
                      <span className="mr-3">🌐</span>
                      Domains
                    </Link>
                  </li>
                </ul>
              </div>

              {/* Settings */}
              <div>
                <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
                  Settings
                </h4>
                <ul className="space-y-2">
                  <li>
                    <Link
                      to={`/apps/${appId}/settings/ai-services`}
                      className={`flex items-center px-3 py-2 rounded-md text-sm font-medium transition-colors ${isActive(`/apps/${appId}/settings`)}`}
                    >
                      <span className="mr-3">⚙️</span>
                      App Settings
                    </Link>
                  </li>
                </ul>
              </div>
            </div>
          ) : (
            // Global navigation (when not in an app)
            <ul className="space-y-2">
              <li>
                <Link
                  to="/apps"
                  className={`flex items-center px-3 py-2 rounded-md text-sm font-medium transition-colors ${isActive('/apps')}`}
                >
                  <span className="mr-3">📱</span>
                  My Apps
                </Link>
              </li>
              <li>
                <Link
                  to="/about"
                  className={`flex items-center px-3 py-2 rounded-md text-sm font-medium transition-colors ${isActive('/about')}`}
                >
                  <span className="mr-3">ℹ️</span>
                  About
                </Link>
              </li>
            </ul>
          )}
        </nav>

        {/* Footer */}
        <div className="p-6 border-t border-gray-200">
          <div className="flex items-center">
            <div className="w-8 h-8 bg-gray-300 rounded-full flex items-center justify-center mr-3">
              <span className="text-gray-600 text-sm font-medium">U</span>
            </div>
            <div className="flex-1">
              <p className="text-sm font-medium text-gray-900">User</p>
              <p className="text-xs text-gray-600">user@example.com</p>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Top Bar */}
        <header className="bg-white shadow-sm border-b border-gray-200 px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              {/* Breadcrumbs can go here */}
            </div>
            <div className="flex items-center space-x-4">
              {/* User menu, notifications, etc. can go here */}
            </div>
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 overflow-auto p-6">
          {children}
        </main>
      </div>
    </div>
  );
}

export default AppLayout; 