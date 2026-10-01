import React, { useState, useEffect, useCallback } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { useUser } from '../../contexts/UserContext';
import { useDeploymentMode } from '../../contexts/DeploymentModeContext';
import { apiService, type App } from '../../services/api';
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
  // App switcher (design v3): every app the user can open, for quick switching
  const [apps, setApps] = useState<App[]>([]);
  const [switcherOpen, setSwitcherOpen] = useState(false);

  const isInSettings = appId
    ? location.pathname.startsWith(`/apps/${appId}/settings`)
    : false;

  // Global administration (design v3): one rail entry; its options live in the contextual panel on /admin routes
  const isAdminRoute = location.pathname.startsWith('/admin');
  const firstAdminItem = navigationConfig?.admin?.find(item =>
    (!item.adminOnly || user?.is_admin || user?.platform_role === 'admin') &&
    !(item.saasOnly && !isSaasMode)
  );

  const [settingsOpen, setSettingsOpen] = useState(isInSettings);

  // Track open state for each group item (keyed by item path)
  const [groupOpen, setGroupOpen] = useState<Record<string, boolean>>({});

  const loadAppData = useCallback(async () => {
    if (!appId) { setAppName(null); return; }
    try {
      const apps = await apiService.getApps();
      const app = apps.find((a: { app_id: number }) => a.app_id === Number.parseInt(appId));
      setAppName(app?.name ?? null);
      setApps(apps);
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

  // Design v3 — global rail item: icon over a tiny label, ember bar on the left when active
  const globalItemClass = (active: boolean) =>
    `relative flex flex-col items-center gap-1 py-3 text-[9.5px] leading-tight text-center transition-colors before:absolute before:left-0 before:top-[9px] before:bottom-[9px] before:w-[2.5px] before:rounded-[3px] focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus dark:focus-visible:ring-focus-dark ${
      active
        ? 'bg-surface-hover text-fg before:bg-accent [&>span:first-child]:text-accent dark:bg-surface-hover-dark dark:text-fg-dark dark:before:bg-accent-dark dark:[&>span:first-child]:text-accent-dark'
        : 'text-fg-tertiary hover:text-fg hover:bg-surface-hover before:bg-transparent dark:text-fg-tertiary-dark dark:hover:text-fg-dark dark:hover:bg-surface-hover-dark'
    }`;

  // Design v3 — contextual (App) panel item
  const appItemClass = (active: boolean) =>
    `relative flex items-center gap-[11px] px-3 py-[9px] rounded-[7px] text-[13px] transition-colors before:absolute before:left-0 before:top-[7px] before:bottom-[7px] before:w-[2.5px] before:rounded-[3px] focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus dark:focus-visible:ring-focus-dark ${
      active
        ? 'bg-surface-hover text-fg font-medium before:bg-accent dark:bg-surface-hover-dark dark:text-fg-dark dark:before:bg-accent-dark'
        : 'text-fg-secondary hover:text-fg hover:bg-surface-hover before:bg-transparent dark:text-fg-secondary-dark dark:hover:text-fg-dark dark:hover:bg-surface-hover-dark'
    }`;

  const NavItemLink: React.FC<{
    item: NavigationItem;
    resolvedPath: string;
    useAppStyle: boolean;
  }> = ({ item, resolvedPath, useAppStyle }) => {
    const cls = useAppStyle ? appItemClass : globalItemClass;
    return (
      <Link to={resolvedPath} title={item.name} className={cls(isItemActive(resolvedPath))}>
        {item.icon && (
          <span className={useAppStyle
            ? 'flex items-center justify-center w-[18px] h-[18px] shrink-0 text-current [&>svg]:w-[18px] [&>svg]:h-[18px]'
            : 'flex items-center justify-center w-[23px] h-[23px] shrink-0 text-current [&>svg]:w-[22px] [&>svg]:h-[22px] [&>svg]:stroke-[1.5]'}>
            {item.icon}
          </span>
        )}
        <span className={useAppStyle ? 'flex-1 min-w-0 truncate' : 'max-w-[64px] px-1 break-words'}>{item.name}</span>
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
                className={`relative w-full flex items-center justify-between px-3 py-[9px] rounded-[7px] text-[13px] transition-colors before:absolute before:left-0 before:top-[7px] before:bottom-[7px] before:w-[2.5px] before:rounded-[3px] focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus dark:focus-visible:ring-focus-dark ${
                  useAppStyle
                    ? anyChildActive ? 'text-fg font-medium bg-surface-hover before:bg-accent dark:text-fg-dark dark:bg-surface-hover-dark dark:before:bg-accent-dark' : 'text-fg-secondary hover:text-fg hover:bg-surface-hover before:bg-transparent dark:text-fg-secondary-dark dark:hover:text-fg-dark dark:hover:bg-surface-hover-dark'
                    : anyChildActive ? 'text-fg bg-surface-hover before:bg-accent dark:text-fg-dark dark:bg-surface-hover-dark dark:before:bg-accent-dark' : 'text-fg-tertiary hover:text-fg hover:bg-surface-hover before:bg-transparent dark:text-fg-tertiary-dark dark:hover:text-fg-dark dark:hover:bg-surface-hover-dark'
                }`}
              >
                <span className="flex items-center gap-[11px]">
                  {item.icon && (
                    <span className="flex items-center justify-center w-[18px] h-[18px] shrink-0 text-current [&>svg]:w-[18px] [&>svg]:h-[18px]">
                      {item.icon}
                    </span>
                  )}
                  {item.name}
                </span>
                {isOpen
                  ? <ChevronDown size={14} className="flex-shrink-0 text-fg-faint dark:text-fg-faint-dark" />
                  : <ChevronRight size={14} className="flex-shrink-0 text-fg-faint dark:text-fg-faint-dark" />
                }
              </button>

              {isOpen && (
                <ul className="mt-px mb-1 ml-[22px] pl-3 border-l border-line dark:border-line-dark flex flex-col [&_a]:py-1.5 [&_a]:text-[12.5px] [&_a]:rounded-md [&_a>span:first-child]:hidden [&_a]:before:hidden">
                  {item.children
                    .filter(child => !(child.adminOnly && !user?.is_admin && user?.platform_role !== 'admin'))
                    .filter(child => !(child.editorOnly && !user?.is_admin && user?.platform_role === 'viewer'))
                    .filter(child => !(child.saasOnly && !isSaasMode))
                    .map((child, ci) => {
                      const childPath = appId ? child.path.replace(':appId', appId) : child.path;
                      return (
                        <li key={`${section}-${index}-child-${ci}`}>
                          <NavItemLink item={child} resolvedPath={childPath} useAppStyle={useAppStyle} />
                        </li>
                      );
                    })}
                </ul>
              )}
            </li>
          );
        }

        return (
          <li key={`${section}-${index}`}>
            <NavItemLink item={item} resolvedPath={path} useAppStyle={useAppStyle} />
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
    <div className={`shrink-0 flex min-h-0 bg-surface dark:bg-surface-dark ${className}`}>
      <nav className="flex-1 min-h-0 flex overscroll-contain">
        {navigationConfig && (
          // Design v3 shell: column 1 = global rail (72px), column 2 = App contextual panel (236px, only inside an app)
          <div className="grid h-full min-h-0 grid-cols-[72px_auto] grid-rows-[minmax(0,1fr)_auto]">

            {/* Global: Home + Marketplace + custom */}
            <div className="contents">
              <ul className="col-start-1 row-start-1 row-span-2 flex flex-col pt-2.5 bg-canvas-alt border-r border-line overflow-y-auto dark:bg-canvas-alt-dark dark:border-line-dark">
                {navigationConfig.mainFeatures && renderItems(navigationConfig.mainFeatures, 'mainFeatures')}
                {navigationConfig.custom && renderItems(navigationConfig.custom, 'custom')}
              </ul>

              {/* App context + navigation */}
              {appId && (appNavItems.length > 0 || settingsTrigger) && (
                <div className="col-start-2 row-start-1 row-span-2 w-[236px] flex flex-col min-h-0 overflow-y-auto bg-surface border-r border-line dark:bg-surface-dark dark:border-line-dark">
                  <div className="relative px-4 pt-4 pb-3.5 border-b border-line dark:border-line-dark">
                    <div className="mb-1 text-[10px] uppercase tracking-[0.05em] text-fg-tertiary dark:text-fg-tertiary-dark">App</div>
                    <button
                      type="button"
                      onClick={() => setSwitcherOpen((open) => !open)}
                      aria-haspopup="true"
                      aria-expanded={switcherOpen}
                      title={appName ?? undefined}
                      className="w-full flex items-center justify-between gap-2 p-0 text-left bg-transparent rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-focus dark:focus-visible:ring-focus-dark"
                    >
                      <h4 className="min-w-0 truncate font-display text-[17px] font-normal leading-tight tracking-[-0.02em] text-fg dark:text-fg-dark">
                        {appName ?? '...'}
                      </h4>
                      <ChevronDown size={13} className={`flex-shrink-0 text-fg-tertiary transition-transform duration-150 dark:text-fg-tertiary-dark ${switcherOpen ? 'rotate-180' : ''}`} />
                    </button>

                    {switcherOpen && (
                      <>
                        {/* Transparent backdrop: clicking outside closes the switcher */}
                        <button
                          type="button"
                          tabIndex={-1}
                          aria-hidden="true"
                          onClick={() => setSwitcherOpen(false)}
                          className="fixed inset-0 z-30 cursor-default bg-transparent"
                        />
                        <ul className="absolute top-full left-4 right-4 mt-1 z-40 max-h-80 overflow-y-auto bg-surface border border-line rounded-lg shadow-[0_14px_40px_rgba(32,28,20,0.14)] dark:bg-surface-dark dark:border-line-dark dark:shadow-[0_14px_40px_rgba(0,0,0,0.55)]">
                          {apps.map((a) => {
                            const isCurrent = String(a.app_id) === appId;
                            return (
                              <li key={a.app_id}>
                                <Link
                                  to={`/apps/${a.app_id}`}
                                  onClick={() => setSwitcherOpen(false)}
                                  aria-current={isCurrent ? 'page' : undefined}
                                  className={`flex items-center gap-2.5 px-3.5 py-2.5 text-[13.5px] hover:bg-surface-hover transition-colors focus:outline-none focus-visible:bg-surface-hover dark:hover:bg-surface-hover-dark dark:focus-visible:bg-surface-hover-dark ${
                                    isCurrent ? 'font-medium text-fg bg-surface-tint dark:text-fg-dark dark:bg-surface-tint-dark' : 'text-fg-secondary dark:text-fg-secondary-dark'
                                  }`}
                                >
                                  <span aria-hidden="true" className="w-[26px] h-[26px] flex-shrink-0 rounded-md bg-accent font-display text-[11px] font-medium text-white flex items-center justify-center dark:bg-accent-dark">
                                    {a.name.split(' ').map((n) => n[0]).join('').toUpperCase().slice(0, 2)}
                                  </span>
                                  <span className="flex-1 min-w-0 truncate">{a.name}</span>
                                  {isCurrent && <span aria-hidden="true" className="w-1.5 h-1.5 flex-shrink-0 rounded-full bg-accent dark:bg-accent-dark" />}
                                </Link>
                              </li>
                            );
                          })}
                        </ul>
                      </>
                    )}
                  </div>

                  <ul className="flex flex-col gap-px p-2.5">
                    {renderItems(appNavItems, 'appNavigation', true)}

                    {/* Collapsible App Settings */}
                    {settingsTrigger && (
                      <li>
                        <button
                          type="button"
                          onClick={() => setSettingsOpen(prev => !prev)}
                          className={`relative w-full flex items-center justify-between px-3 py-[9px] rounded-[7px] text-[13px] transition-colors before:absolute before:left-0 before:top-[7px] before:bottom-[7px] before:w-[2.5px] before:rounded-[3px] focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus dark:focus-visible:ring-focus-dark ${
                            isInSettings
                              ? 'text-fg font-medium bg-surface-hover before:bg-accent dark:text-fg-dark dark:bg-surface-hover-dark dark:before:bg-accent-dark'
                              : 'text-fg-secondary hover:text-fg hover:bg-surface-hover before:bg-transparent dark:text-fg-secondary-dark dark:hover:text-fg-dark dark:hover:bg-surface-hover-dark'
                          }`}
                        >
                          <span className="flex items-center gap-[11px]">
                            {settingsTrigger.icon && (
                              <span className="flex items-center justify-center w-[18px] h-[18px] shrink-0 text-current [&>svg]:w-[18px] [&>svg]:h-[18px]">
                                {settingsTrigger.icon}
                              </span>
                            )}
                            {settingsTrigger.name}
                          </span>
                          {settingsOpen
                            ? <ChevronDown size={14} className="flex-shrink-0 text-fg-faint dark:text-fg-faint-dark" />
                            : <ChevronRight size={14} className="flex-shrink-0 text-fg-faint dark:text-fg-faint-dark" />
                          }
                        </button>

                        {settingsOpen && settingsItems.length > 0 && (
                          <ul className="mt-px mb-1 ml-[22px] pl-3 border-l border-line dark:border-line-dark flex flex-col [&_a]:py-1.5 [&_a]:text-[12.5px] [&_a]:rounded-md [&_a>span:first-child]:hidden [&_a]:before:hidden">
                            {settingsItems.map((item) => {
                              const path = item.path.replace(':appId', appId);
                              return (
                                <li key={item.path}>
                                  <Link to={path} className={appItemClass(isItemActive(path))}>
                                    {item.icon && (
                                      <span className="flex items-center w-4 h-4 shrink-0 text-current">
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

            {/* Administration — only shown when there are visible items */}
            {navigationConfig.admin && navigationConfig.admin.some(item =>
              (!item.adminOnly || user?.is_admin || user?.platform_role === 'admin') &&
              !(item.saasOnly && !isSaasMode)
            ) && (
              <>
                {/* Rail entry, anchored bottom-left */}
                <div className="col-start-1 row-start-2 z-10 border-t border-line dark:border-line-dark">
                  <Link
                    to={firstAdminItem?.path ?? '/admin/users'}
                    title="Global admin"
                    className={globalItemClass(isAdminRoute)}
                  >
                    <span className="flex items-center justify-center w-[23px] h-[23px] shrink-0 text-current">
                      <svg width="23" height="23" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                        <path d="M12 3.5l6.5 2.5v5c0 4.2-2.8 7-6.5 8.5-3.7-1.5-6.5-4.3-6.5-8.5V6L12 3.5z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
                        <path d="M9.2 11.9l2 2 3.6-3.9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    </span>
                    <span className="max-w-[64px] px-1 text-[9px] leading-[1.15]">Global admin</span>
                  </Link>
                </div>

                {/* Contextual panel with the administration options (no switcher) */}
                {isAdminRoute && (
                  <div className="col-start-2 row-start-1 row-span-2 w-[236px] flex flex-col min-h-0 overflow-y-auto bg-surface border-r border-line dark:bg-surface-dark dark:border-line-dark">
                    <div className="px-4 pt-4 pb-3.5 border-b border-line dark:border-line-dark">
                      <h4 className="truncate font-display text-[17px] font-normal leading-tight tracking-[-0.02em] text-fg dark:text-fg-dark">
                        Global admin
                      </h4>
                    </div>
                    <ul className="flex flex-col gap-px p-2.5">
                      {renderItems(navigationConfig.admin, 'admin', true)}
                    </ul>
                  </div>
                )}
              </>
            )}

          </div>
        )}

        {children}
      </nav>
    </div>
  );
};
