import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useUser } from '../../contexts/UserContext';
import { useTheme } from '../../themes/ThemeContext';
import type { NavigationConfig, NavigationItem } from '../../core/types';

interface SidebarProps {
  navigationConfig?: NavigationConfig;
  className?: string;
  children?: React.ReactNode;
}

export const Sidebar: React.FC<SidebarProps> = ({ 
  navigationConfig, 
  className = "",
  children 
}) => {
  const location = useLocation();
  const { user } = useUser();
  const { theme } = useTheme();

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
      {/* Logo/Brand */}
      <div className="p-6 border-b border-gray-200">
        <Link to="/apps" className="flex items-center">
          <img 
            src={theme.logo || "/mattin-small.png"} 
            alt={theme.name || "Mattin AI"} 
            className="w-8 h-8 mr-3"
          />
          <span className="text-xl font-bold text-gray-900">
            {theme.name || "Mattin AI"}
          </span>
        </Link>
      </div>

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
    </div>
  );
};
