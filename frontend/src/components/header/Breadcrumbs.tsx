import React, { useEffect, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
import { apiService } from '../../services/api';
import type { NavigationConfig, NavigationItem } from '../../core/types';

interface BreadcrumbsProps {
  navigationConfig?: NavigationConfig;
}

interface Crumb {
  label: string;
  path?: string; // undefined = current page (not clickable)
}

interface NavigationEntry {
  item: NavigationItem;
  ancestors: NavigationItem[];
  path: string;
}

function collectEntries(
  items: NavigationItem[] | undefined,
  appId: string,
  ancestors: NavigationItem[] = []
): NavigationEntry[] {
  if (!items) return [];

  return items.flatMap((item) => [
    {
      item,
      ancestors,
      path: item.path.replace(':appId', appId),
    },
    ...collectEntries(item.children, appId, [...ancestors, item]),
  ]);
}

const ACTION_LABELS: Record<string, string> = {
  new: 'New',
  edit: 'Edit',
  playground: 'Playground',
  detail: 'Detail',
  runs: 'Runs',
  files: 'Files',
  conversation: 'Conversation',
  general: 'General',
};

function getSuffixLabels(basePath: string, pathname: string): string[] {
  const remaining = pathname.slice(basePath.length).split('/').filter(Boolean);
  const labels = remaining
    .map((segment) => ACTION_LABELS[segment] ?? (/^\d+$/.test(segment) ? '' : segment))
    .filter(Boolean);

  if (labels.length > 0) return labels;
  if (remaining.length === 0) return [];

  return ['/scheduled-tasks', '/mcp-servers', '/sharepoint'].some((suffix) => basePath.endsWith(suffix))
    ? ['Detail']
    : ['Edit'];
}

function findEntry(entries: NavigationEntry[], pathname: string): NavigationEntry | undefined {
  return entries
    .filter((entry) => pathname === entry.path || pathname.startsWith(`${entry.path}/`))
    .sort((a, b) => b.path.length - a.path.length)[0];
}

function getEntryCrumbs(match: NavigationEntry, pathname: string): Crumb[] {
  return [
    ...match.ancestors.map((ancestor) => ({ label: ancestor.name })),
    { label: match.item.name, path: match.path },
    ...getSuffixLabels(match.path, pathname).map((label) => ({ label })),
  ];
}

function getAdminCrumbs(pathname: string, navigationConfig?: NavigationConfig): Crumb[] | null {
  if (!pathname.startsWith('/admin/')) return null;
  const match = findEntry(collectEntries(navigationConfig?.admin, ''), pathname);
  return [
    { label: 'Administration' },
    ...(match ? getEntryCrumbs(match, pathname) : []),
  ];
}

function getGlobalCrumbs(pathname: string, navigationConfig?: NavigationConfig): Crumb[] | null {
  if (pathname !== '/marketplace' && pathname !== '/apps') return null;

  const entry = collectEntries(navigationConfig?.mainFeatures, '')
    .find((item) => item.path === pathname);
  const fallbackLabel = pathname === '/apps' ? 'My Apps' : 'Marketplace';
  return [{ label: entry?.item.name ?? fallbackLabel }];
}

function getSettingsCrumbs(
  pathname: string,
  appId: string,
  navigationConfig?: NavigationConfig
): Crumb[] | null {
  const settingsBase = `/apps/${appId}/settings`;
  if (pathname !== settingsBase && !pathname.startsWith(`${settingsBase}/`)) return null;

  const crumbs: Crumb[] = [{ label: 'App Settings', path: settingsBase }];
  if (pathname === settingsBase) return crumbs;

  const entries = [
    ...collectEntries(navigationConfig?.settingsNavigation, appId),
    ...collectEntries(navigationConfig?.settings, appId),
  ];
  const match = findEntry(entries, pathname);
  return [
    ...crumbs,
    ...(match
      ? getEntryCrumbs(match, pathname)
      : getSuffixLabels(settingsBase, pathname).map((label) => ({ label }))),
  ];
}

function useAppName(appId?: string): string | null {
  const [appDetails, setAppDetails] = useState<{ appId: string; name: string } | null>(null);

  useEffect(() => {
    if (!appId) {
      setAppDetails(null);
      return;
    }

    let isCurrent = true;
    apiService.getApp(Number.parseInt(appId, 10))
      .then((app) => {
        if (isCurrent) setAppDetails({ appId, name: app.name });
      })
      .catch(() => {
        if (isCurrent) setAppDetails(null);
      });

    return () => {
      isCurrent = false;
    };
  }, [appId]);

  return appDetails && appDetails.appId === appId ? appDetails.name : null;
}

export const Breadcrumbs: React.FC<BreadcrumbsProps> = ({ navigationConfig }) => {
  const location = useLocation();
  const { appId } = useParams<{ appId?: string }>();
  const appName = useAppName(appId);
  const pathname = location.pathname;

  if (!appId) {
    const crumbs = getAdminCrumbs(pathname, navigationConfig)
      ?? getGlobalCrumbs(pathname, navigationConfig);
    return crumbs ? renderBreadcrumbs(crumbs) : null;
  }

  const dashboardPath = `/apps/${appId}`;
  const rootCrumb = { label: appName ?? `App ${appId}`, path: dashboardPath };
  if (pathname === dashboardPath) return renderBreadcrumbs([rootCrumb]);

  const settingsCrumbs = getSettingsCrumbs(pathname, appId, navigationConfig);
  if (settingsCrumbs) return renderBreadcrumbs([rootCrumb, ...settingsCrumbs]);

  const entries = [
    ...collectEntries(navigationConfig?.appNavigation, appId),
    ...collectEntries(navigationConfig?.custom, appId),
  ];
  const match = findEntry(entries, pathname);
  return match
    ? renderBreadcrumbs([rootCrumb, ...getEntryCrumbs(match, pathname)])
    : null;
};

function renderBreadcrumbs(crumbs: Crumb[]): React.ReactElement | null {
  if (crumbs.length === 0) return null;

  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-1">
      {crumbs.map((crumb, index) => {
        const isLast = index === crumbs.length - 1;
        return (
          <React.Fragment key={`${crumb.label}-${index}`}>
            {index > 0 && (
              <ChevronRight size={12} className="text-gray-400 flex-shrink-0" />
            )}
            {!isLast && crumb.path ? (
              <Link
                to={crumb.path}
                className="text-[13px] text-fg-tertiary hover:text-fg transition-colors whitespace-nowrap dark:text-fg-tertiary-dark dark:hover:text-fg-dark"
              >
                {crumb.label}
              </Link>
            ) : (
              <span className="text-[13px] text-fg font-medium whitespace-nowrap dark:text-fg-dark">
                {crumb.label}
              </span>
            )}
          </React.Fragment>
        );
      })}
    </nav>
  );
}
