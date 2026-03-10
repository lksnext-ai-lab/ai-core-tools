import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useUser } from '../../contexts/UserContext';
import type { NavigationConfig, NavigationItem } from '../../core/types';

interface SidebarProps {
  navigationConfig?: NavigationConfig;
  className?: string;
  children?: React.ReactNode;
  title?: string;
  logoUrl?: string;
}

export const Sidebar: React.FC<SidebarProps> = ({ 
  navigationConfig, 
  className = "",
  children,
  title,
  logoUrl
}) => {
  const location = useLocation();
  const { user } = useUser();

  const isActive = (path: string) => {
    return location.pathname.startsWith(path) ? 'text-blue-600 bg-blue-50' : 'text-gray-700 hover:text-blue-600 hover:bg-gray-50';
  };

  // Render navigation items
  const renderNavigationItems = (items: NavigationItem[], section: string) => {
    return items.map((item, index) => {
      // Skip admin items if user is not admin
      if (item.adminOnly && !user?.is_admin) {
        return null;
      }

      return (
        <li key={`${section}-${index}`}>
          <Link
            to={item.path}
            className={`flex items-center px-3 py-2 rounded-md text-sm font-medium transition-colors ${isActive(item.path)}`}
          >
            {item.icon && <span className="mr-3">{item.icon}</span>}
            {item.name}
          </Link>
        </li>
      );
    }).filter(Boolean);
  };

  return (
    <div className={`w-64 bg-white shadow-sm border-r border-gray-200 flex flex-col ${className}`}>
      {/* Sidebar Navigation */}
      <nav className="flex-1 p-6">
        {navigationConfig && (
          <div className="space-y-6">
            {/* Main Features - Home + Custom items */}
            <div>
              <ul className="space-y-2">
                {/* Home */}
                {navigationConfig.mainFeatures && navigationConfig.mainFeatures.length > 0 && 
                  renderNavigationItems(navigationConfig.mainFeatures, 'mainFeatures')
                }
                {/* Custom items (extensions) */}
                {navigationConfig.custom && navigationConfig.custom.length > 0 && 
                  renderNavigationItems(navigationConfig.custom, 'custom')
                }
              </ul>
            </div>

            {/* Administration */}
            {navigationConfig.admin && navigationConfig.admin.length > 0 && (
              <div>
                <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
                  Administration
                </h4>
                <ul className="space-y-2">
                  {renderNavigationItems(navigationConfig.admin, 'admin')}
                </ul>
              </div>
            )}
          </div>
        )}

        {/* Custom children */}
        {children}
      </nav>

      {/* User identity at bottom */}
      {user && (
        <div className="p-4 border-t border-gray-200">
          <Link to="/profile" className="flex items-center space-x-3 hover:bg-gray-50 rounded-md p-2 transition-colors">
            {user.avatar_url ? (
              <img
                src={user.avatar_url}
                alt="User avatar"
                className="w-8 h-8 rounded-full object-cover flex-shrink-0"
              />
            ) : (
              <div className="w-8 h-8 bg-blue-500 rounded-full flex items-center justify-center flex-shrink-0">
                <span className="text-white text-xs font-medium">
                  {user.name
                    ? user.name.split(' ').map((n: string) => n[0]).join('').toUpperCase().slice(0, 2)
                    : user.email?.[0]?.toUpperCase() ?? '?'}
                </span>
              </div>
            )}
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-gray-900 truncate">{user.name || 'Profile'}</p>
              <p className="text-xs text-gray-500 truncate">{user.email}</p>
            </div>
          </Link>
        </div>
      )}
    </div>
  );
};
