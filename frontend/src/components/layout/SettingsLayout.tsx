import { type ReactNode } from 'react';
import { Link, useParams, useLocation } from 'react-router-dom';

interface SettingsLayoutProps {
  readonly children: ReactNode;
}

function SettingsLayout({ children }: SettingsLayoutProps) {
  const { appId } = useParams();
  const location = useLocation();

  const isActive = (path: string) => {
    return location.pathname.includes(path) ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300';
  };

  return (
    <div className="space-y-6">
      {/* Settings Navigation Tabs */}
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex space-x-8" aria-label="Settings">
          <Link
            to={`/apps/${appId}/settings/ai-services`}
            className={`whitespace-nowrap py-2 px-1 border-b-2 font-medium text-sm transition-colors ${isActive('ai-services')}`}
          >
            <span className="mr-2">🤖</span>AI Services
          </Link>
          
          <Link
            to={`/apps/${appId}/settings/embedding-services`}
            className={`whitespace-nowrap py-2 px-1 border-b-2 font-medium text-sm transition-colors ${isActive('embedding-services')}`}
          >
            <span className="mr-2">🧠</span>Embedding Services
          </Link>
          
          <Link
            to={`/apps/${appId}/settings/mcp-configs`}
            className={`whitespace-nowrap py-2 px-1 border-b-2 font-medium text-sm transition-colors ${isActive('mcp-configs')}`}
          >
            <span className="mr-2">🔌</span>MCP Configs
          </Link>

          <Link
            to={`/apps/${appId}/settings/api-keys`}
            className={`whitespace-nowrap py-2 px-1 border-b-2 font-medium text-sm transition-colors ${isActive('api-keys')}`}
          >
            <span className="mr-2">🔑</span>API Keys
          </Link>
          
          <Link
            to={`/apps/${appId}/settings/data-structures`}
            className={`whitespace-nowrap py-2 px-1 border-b-2 font-medium text-sm transition-colors ${isActive('data-structures')}`}
          >
            <span className="mr-2">📄</span>Data Structures
          </Link>
          
          <Link
            to={`/apps/${appId}/settings/collaboration`}
            className={`whitespace-nowrap py-2 px-1 border-b-2 font-medium text-sm transition-colors ${isActive('collaboration')}`}
          >
            <span className="mr-2">👥</span>Collaboration
          </Link>
          
          <Link
            to={`/apps/${appId}/settings/general`}
            className={`whitespace-nowrap py-2 px-1 border-b-2 font-medium text-sm transition-colors ${isActive('general')}`}
          >
            <span className="mr-2">⚙️</span>General
          </Link>
        </nav>
      </div>

      {/* Settings Content */}
      <div className="bg-white rounded-lg">
        {children}
      </div>
    </div>
  );
}

export default SettingsLayout;