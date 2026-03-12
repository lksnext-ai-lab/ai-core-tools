import React, { useState, useEffect, useCallback } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { ChevronDown, ChevronRight, ArrowLeft } from 'lucide-react';
import { useUser } from '../../contexts/UserContext';
import { apiService } from '../../services/api';
import type { NavigationConfig, NavigationItem } from '../../core/types';

interface SidebarProps {
  navigationConfig?: NavigationConfig;
  className?: string;
  children?: React.ReactNode;
}

export const Sidebar: React.FC<SidebarProps> = ({
  navigationConfig,
  className = "",
  children,
}) => {
  const location = useLocation();
  const { appId } = useParams();
  const { user } = useUser();
  const [appName, setAppName] = useState<string | null>(null);

  const isInSettings = appId
    ? location.pathname.startsWith(`/apps/${appId}/settings`)
    : false;

  const [settingsOpen, setSettingsOpen] = useState(isInSettings);

  const loadAppData = useCallback(async () => {
    if (!appId) { setAppName(null); return; }
    try {
      const apps = await apiService.getApps();
      const app = apps.find((a: { app_id: number }) => a.app_id === Number.parseInt(appId));
      setAppName(app?.name ?? null);
    } catch {
      setAppName(null);
    }
  }, [appId]);

  useEffect(() => { loadAppData(); }, [loadAppData]);

  // Auto-open settings group when navigating into a settings page
  useEffect(() => {
    if (isInSettings) {
      setSettingsOpen(true);
    }
  }, [isInSettings]);

  const isItemActive = (path: string): boolean => {
    // Dashboard exact match — avoid matching all /apps/:appId/* routes
    if (appId && path === `/apps/${appId}`) {
      return location.pathname === path;
    }
    return location.pathname.startsWith(path);
  };

  const globalItemClass = (active: boolean) =>
    `flex items-center px-3 py-2 rounded-md text-sm font-medium transition-colors ${
      active
        ? 'text-blue-600 bg-blue-50'
        : 'text-gray-700 hover:text-blue-600 hover:bg-gray-50'
    }`;

  const appItemClass = (active: boolean) =>
    `flex items-center px-3 py-2 rounded-md text-sm font-medium transition-colors ${
      active
        ? 'text-gray-900 bg-gray-100'
        : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
    }`;

  const renderItems = (items: NavigationItem[], section: string, useAppStyle = false) =>
    items
      .filter(item => !(item.adminOnly && !user?.is_admin))
      .map((item, index) => {
        const path = appId ? item.path.replace(':appId', appId) : item.path;
        const cls = useAppStyle ? appItemClass : globalItemClass;
        return (
          <li key={`${section}-${index}`}>
            <Link to={path} className={cls(isItemActive(path))}>
              {item.icon && (
                <span className="mr-3 flex items-center w-4 h-4 shrink-0 text-current">
                  {item.icon}
                </span>
              )}
              {item.name}
            </Link>
          </li>
        );
      });

  // App nav items without the Settings trigger
  const appNavItems = (navigationConfig?.appNavigation ?? []).filter(
    item => !item.path.endsWith('/settings')
  );

  // The "App Settings" item used as collapsible trigger
  const settingsTrigger = navigationConfig?.appNavigation?.find(
    item => item.path.endsWith('/settings')
  );

  // Settings sub-items
  const settingsItems = navigationConfig?.settingsNavigation ?? [];

  return (
    <div className={`w-64 bg-white shadow-sm border-r border-gray-200 flex flex-col ${className}`}>
      <nav className="flex-1 p-4 overflow-y-auto">
        {navigationConfig && (
          <div className="space-y-6">

            {/* Global: Home + Marketplace + custom */}
            <div>
              <ul className="space-y-1">
                {navigationConfig.mainFeatures && renderItems(navigationConfig.mainFeatures, 'mainFeatures')}
                {navigationConfig.custom && renderItems(navigationConfig.custom, 'custom')}
              </ul>

              {/* App context + navigation — flows directly under My Apps */}
              {appId && (appNavItems.length > 0 || settingsTrigger) && (
                <div className="mt-4">
                  <Link
                    to="/apps"
                    className="flex items-center gap-2 mb-3 group"
                    title="Back to My Apps"
                  >
                    <ArrowLeft size={12} className="text-gray-400 group-hover:text-gray-600 flex-shrink-0 transition-colors" />
                    <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider group-hover:text-gray-600 truncate transition-colors" title={appName ?? undefined}>
                      {appName ?? '...'}
                    </h4>
                  </Link>

                  <ul className="space-y-0.5 ml-2 border-l border-gray-200 pl-2">
                    {renderItems(appNavItems, 'appNavigation', true)}

                    {/* Collapsible Settings */}
                    {settingsTrigger && (
                      <li>
                        <button
                          type="button"
                          onClick={() => setSettingsOpen(prev => !prev)}
                          className={`w-full flex items-center justify-between px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                            isInSettings
                              ? 'text-gray-900 bg-gray-100'
                              : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
                          }`}
                        >
                          <span className="flex items-center">
                            {settingsTrigger.icon && (
                              <span className="mr-3 flex items-center w-4 h-4 shrink-0 text-current">
                                {settingsTrigger.icon}
                              </span>
                            )}
                            {settingsTrigger.name}
                          </span>
                          {settingsOpen
                            ? <ChevronDown size={14} className="flex-shrink-0 text-gray-400" />
                            : <ChevronRight size={14} className="flex-shrink-0 text-gray-400" />
                          }
                        </button>

                        {settingsOpen && settingsItems.length > 0 && (
                          <ul className="mt-1 ml-4 space-y-0.5 border-l border-gray-100 pl-3">
                            {settingsItems.map((item) => {
                              const path = item.path.replace(':appId', appId);
                              return (
                                <li key={item.path}>
                                  <Link to={path} className={appItemClass(isItemActive(path))}>
                                    {item.icon && (
                                      <span className="mr-3 flex items-center w-4 h-4 shrink-0 text-current">
                                        {item.icon}
                                      </span>
                                    )}
                                    {item.name}
                                  </Link>
                                </li>
                              );
                            })}
                          </ul>
                        )}
                      </li>
                    )}
                  </ul>
                </div>
              )}
            </div>

            {/* Administration */}
            {navigationConfig.admin && navigationConfig.admin.length > 0 && (
              <div>
                <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
                  Administration
                </h4>
                <ul className="space-y-1">
                  {renderItems(navigationConfig.admin, 'admin')}
                </ul>
              </div>
            )}

          </div>
        )}

        {children}
      </nav>
    </div>
  );
};
