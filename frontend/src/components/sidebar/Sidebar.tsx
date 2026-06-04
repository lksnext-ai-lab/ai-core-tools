import React, { useState, useEffect, useCallback } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { ChevronDown, ChevronRight, ArrowLeft } from 'lucide-react';
import { useUser } from '../../contexts/UserContext';
import { useDeploymentMode } from '../../contexts/DeploymentModeContext';
import { useCapability } from '../../contexts/CapabilitiesContext';
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
  const { isSaasMode } = useDeploymentMode();
  const [appName, setAppName] = useState<string | null>(null);

  const isInSettings = appId
    ? location.pathname.startsWith(`/apps/${appId}/settings`)
    : false;

  const [settingsOpen, setSettingsOpen] = useState(isInSettings);

  // Track open state for each group item (keyed by item path)
  const [groupOpen, setGroupOpen] = useState<Record<string, boolean>>({});

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
    if (isInSettings) setSettingsOpen(true);
  }, [isInSettings]);

  // Auto-open any group whose child is currently active
  useEffect(() => {
    if (!appId || !navigationConfig?.appNavigation) return;
    const updates: Record<string, boolean> = {};
    for (const item of navigationConfig.appNavigation) {
      if (item.children) {
        const anyChildActive = item.children.some((child) =>
          location.pathname.startsWith(child.path.replace(':appId', appId))
        );
        if (anyChildActive) updates[item.path] = true;
      }
    }
    if (Object.keys(updates).length > 0) {
      setGroupOpen((prev) => ({ ...prev, ...updates }));
    }
  }, [location.pathname, appId, navigationConfig?.appNavigation]);

  const isItemActive = (path: string): boolean => {
    if (appId && path === `/apps/${appId}`) return location.pathname === path;
    return location.pathname.startsWith(path);
  };

  const globalItemClass = (active: boolean) =>
    `flex items-center px-3 py-2 rounded-md text-sm font-medium transition-colors ${
      active ? 'text-blue-600 bg-blue-50' : 'text-gray-700 hover:text-blue-600 hover:bg-gray-50'
    }`;

  const appItemClass = (active: boolean) =>
    `flex items-center px-3 py-2 rounded-md text-sm font-medium transition-colors ${
      active ? 'text-gray-900 bg-gray-100' : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
    }`;

  // Renders a leaf navigation item, with EE badge support
  const EnterpriseAwareLink: React.FC<{
    item: NavigationItem;
    resolvedPath: string;
    useAppStyle: boolean;
  }> = ({ item, resolvedPath, useAppStyle }) => {
    const isEnabled = useCapability(item.enterpriseFeature ?? '');
    const isEE = !!item.enterpriseFeature;
    const locked = isEE && !isEnabled;
    const cls = useAppStyle ? appItemClass : globalItemClass;
    const active = !locked && isItemActive(resolvedPath);
    const label = locked ? `${item.name} [EE]` : item.name;
    const dest = locked
      ? `/apps/${appId}/enterprise?feature=${encodeURIComponent(item.name)}`
      : resolvedPath;

    return (
      <Link
        to={dest}
        className={`${cls(active)} ${locked ? 'opacity-60' : ''}`}
        title={locked ? `${item.name} — Enterprise Edition` : undefined}
      >
        {item.icon && (
          <span className="mr-3 flex items-center w-4 h-4 shrink-0 text-current">
            {item.icon}
          </span>
        )}
        <span className="flex-1">{label}</span>
      </Link>
    );
  };

  const renderItems = (items: NavigationItem[], section: string, useAppStyle = false) =>
    items
      .filter(item => !(item.adminOnly && !user?.is_admin && user?.platform_role !== 'admin'))
      .filter(item => !(item.editorOnly && !user?.is_admin && user?.platform_role === 'viewer'))
      .filter(item => !(item.saasOnly && !isSaasMode))
      .map((item, index) => {
        const path = appId ? item.path.replace(':appId', appId) : item.path;

        // Group item with children — renders as collapsible
        if (item.children && item.children.length > 0) {
          const isOpen = groupOpen[item.path] ?? false;
          const anyChildActive = item.children.some((child) =>
            isItemActive(appId ? child.path.replace(':appId', appId) : child.path)
          );
          return (
            <li key={`${section}-${index}`}>
              <button
                type="button"
                onClick={() => setGroupOpen((prev) => ({ ...prev, [item.path]: !prev[item.path] }))}
                className={`w-full flex items-center justify-between px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  useAppStyle
                    ? anyChildActive ? 'text-gray-900 bg-gray-100' : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
                    : anyChildActive ? 'text-blue-600 bg-blue-50' : 'text-gray-700 hover:text-blue-600 hover:bg-gray-50'
                }`}
              >
                <span className="flex items-center">
                  {item.icon && (
                    <span className="mr-3 flex items-center w-4 h-4 shrink-0 text-current">
                      {item.icon}
                    </span>
                  )}
                  {item.name}
                </span>
                {isOpen
                  ? <ChevronDown size={14} className="flex-shrink-0 text-gray-400" />
                  : <ChevronRight size={14} className="flex-shrink-0 text-gray-400" />
                }
              </button>

              {isOpen && (
                <ul className="mt-1 ml-4 space-y-0.5 border-l border-gray-100 pl-3">
                  {item.children
                    .filter(child => !(child.adminOnly && !user?.is_admin && user?.platform_role !== 'admin'))
                    .filter(child => !(child.editorOnly && !user?.is_admin && user?.platform_role === 'viewer'))
                    .filter(child => !(child.saasOnly && !isSaasMode))
                    .map((child, ci) => {
                      const childPath = appId ? child.path.replace(':appId', appId) : child.path;
                      return (
                        <li key={`${section}-${index}-child-${ci}`}>
                          <EnterpriseAwareLink item={child} resolvedPath={childPath} useAppStyle={useAppStyle} />
                        </li>
                      );
                    })}
                </ul>
              )}
            </li>
          );
        }

        // Leaf item (may have enterpriseFeature)
        return (
          <li key={`${section}-${index}`}>
            {item.enterpriseFeature ? (
              <EnterpriseAwareLink item={item} resolvedPath={path} useAppStyle={useAppStyle} />
            ) : (
              <Link to={path} className={useAppStyle ? appItemClass(isItemActive(path)) : globalItemClass(isItemActive(path))}>
                {item.icon && (
                  <span className="mr-3 flex items-center w-4 h-4 shrink-0 text-current">
                    {item.icon}
                  </span>
                )}
                {item.name}
              </Link>
            )}
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
    <div className={`w-64 shrink-0 bg-white shadow-sm border-r border-gray-200 flex flex-col min-h-0 ${className}`}>
      <nav className="flex-1 min-h-0 p-4 overflow-y-auto overscroll-contain">
        {navigationConfig && (
          <div className="space-y-6">

            {/* Global: Home + Marketplace + custom */}
            <div>
              <ul className="space-y-1">
                {navigationConfig.mainFeatures && renderItems(navigationConfig.mainFeatures, 'mainFeatures')}
                {navigationConfig.custom && renderItems(navigationConfig.custom, 'custom')}
              </ul>

              {/* App context + navigation */}
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

                    {/* Collapsible App Settings */}
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

            {/* Administration — only show section header when there are visible items */}
            {navigationConfig.admin && navigationConfig.admin.some(item =>
              (!item.adminOnly || user?.is_admin || user?.platform_role === 'admin') &&
              !(item.saasOnly && !isSaasMode)
            ) && (
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
