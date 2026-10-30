import React, { useEffect, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { apiService } from '../../services/api';
import type { NavigationConfig, NavigationItem } from '../../core/types';

interface BreadcrumbsProps {
  navigationConfig?: NavigationConfig;
}

interface Crumb {
  label: string;
  path?: string; // undefined = current page (not clickable)
  translationKey?: string;
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

const ACTION_LABELS: Record<string, { label: string; translationKey: string }> = {
  new: { label: 'New', translationKey: 'breadcrumbs.action.new' },
  edit: { label: 'Edit', translationKey: 'breadcrumbs.action.edit' },
  playground: { label: 'Playground', translationKey: 'breadcrumbs.action.playground' },
  detail: { label: 'Detail', translationKey: 'breadcrumbs.action.detail' },
  runs: { label: 'Runs', translationKey: 'breadcrumbs.action.runs' },
  files: { label: 'Files', translationKey: 'breadcrumbs.action.files' },
  conversation: { label: 'Conversation', translationKey: 'breadcrumbs.action.conversation' },
  general: { label: 'General', translationKey: 'breadcrumbs.action.general' },
};

const NAVIGATION_LABELS: Record<string, { name: string; translationKey: string }> = {
  '/home': { name: 'Home', translationKey: 'breadcrumbs.navigation.home' },
  '/marketplace': { name: 'Marketplace', translationKey: 'breadcrumbs.navigation.marketplace' },
  '/apps': { name: 'My Apps', translationKey: 'breadcrumbs.navigation.myApps' },
  '/about': { name: 'About', translationKey: 'breadcrumbs.navigation.about' },
  '/apps/:appId': { name: 'Dashboard', translationKey: 'breadcrumbs.navigation.dashboard' },
  '/apps/:appId/agents': { name: 'Agents', translationKey: 'breadcrumbs.navigation.agents' },
  '/apps/:appId/scheduled-tasks': { name: 'Scheduled Tasks', translationKey: 'breadcrumbs.navigation.scheduledTasks' },
  '/apps/:appId/data': { name: 'Data sources', translationKey: 'breadcrumbs.navigation.dataSources' },
  '/apps/:appId/silos': { name: 'Silos', translationKey: 'breadcrumbs.navigation.silos' },
  '/apps/:appId/repositories': { name: 'Repositories', translationKey: 'breadcrumbs.navigation.repositories' },
  '/apps/:appId/domains': { name: 'Domains', translationKey: 'breadcrumbs.navigation.domains' },
  '/apps/:appId/sharepoint': { name: 'SharePoint', translationKey: 'breadcrumbs.navigation.sharePoint' },
  '/apps/:appId/mcp-servers': { name: 'MCP Servers', translationKey: 'breadcrumbs.navigation.mcpServers' },
  '/apps/:appId/metrics': { name: 'Metrics', translationKey: 'breadcrumbs.navigation.metrics' },
  '/apps/:appId/skills': { name: 'Skills', translationKey: 'breadcrumbs.navigation.skills' },
  '/apps/:appId/middlewares': { name: 'Middlewares', translationKey: 'breadcrumbs.navigation.middlewares' },
  '/apps/:appId/settings': { name: 'App Settings', translationKey: 'breadcrumbs.navigation.appSettings' },
  '/apps/:appId/settings/output-destinations': { name: 'Output Channels', translationKey: 'breadcrumbs.navigation.outputChannels' },
  '/apps/:appId/settings/ai-services': { name: 'AI Services', translationKey: 'breadcrumbs.navigation.aiServices' },
  '/apps/:appId/settings/embedding-services': { name: 'Embedding Services', translationKey: 'breadcrumbs.navigation.embeddingServices' },
  '/apps/:appId/settings/sandbox-services': { name: 'Sandbox Services', translationKey: 'breadcrumbs.navigation.sandboxServices' },
  '/apps/:appId/settings/mcp-configs': { name: 'MCP Configs', translationKey: 'breadcrumbs.navigation.mcpConfigs' },
  '/apps/:appId/settings/api-keys': { name: 'API Keys', translationKey: 'breadcrumbs.navigation.apiKeys' },
  '/apps/:appId/settings/data-structures': { name: 'Data Structures', translationKey: 'breadcrumbs.navigation.dataStructures' },
  '/apps/:appId/settings/collaboration': { name: 'Collaboration', translationKey: 'breadcrumbs.navigation.collaboration' },
  '/admin/users': { name: 'Users', translationKey: 'breadcrumbs.navigation.users' },
  '/admin/stats': { name: 'Statistics', translationKey: 'breadcrumbs.navigation.statistics' },
  '/admin/metrics': { name: 'Agent Metrics', translationKey: 'breadcrumbs.navigation.agentMetrics' },
  '/admin/settings': { name: 'Settings', translationKey: 'breadcrumbs.navigation.settings' },
  '/admin/saas-users': { name: 'SaaS Users', translationKey: 'breadcrumbs.navigation.saasUsers' },
  '/admin/system-ai-services': { name: 'System AI Services', translationKey: 'breadcrumbs.navigation.systemAiServices' },
  '/admin/system-embedding-services': { name: 'System Embedding Services', translationKey: 'breadcrumbs.navigation.systemEmbeddingServices' },
  '/admin/system-sandbox-services': { name: 'System Sandbox Services', translationKey: 'breadcrumbs.navigation.systemSandboxServices' },
  '/admin/system-skills': { name: 'System Skills', translationKey: 'breadcrumbs.navigation.systemSkills' },
  '/admin/tier-config': { name: 'Tier Config', translationKey: 'breadcrumbs.navigation.tierConfig' },
};

function getNavigationTranslationKey(item: NavigationItem): string | undefined {
  const knownLabel = NAVIGATION_LABELS[item.path];
  return knownLabel?.name === item.name ? knownLabel.translationKey : undefined;
}

function getSuffixCrumbs(basePath: string, pathname: string): Crumb[] {
  const remaining = pathname.slice(basePath.length).split('/').filter(Boolean);
  const crumbs = remaining.flatMap((segment) => {
    const action = ACTION_LABELS[segment];
    if (action) return [{ ...action }];
    return /^\d+$/.test(segment) ? [] : [{ label: segment }];
  });

  if (crumbs.length > 0) return crumbs;
  if (remaining.length === 0) return [];

  return ['/scheduled-tasks', '/mcp-servers', '/sharepoint'].some((suffix) => basePath.endsWith(suffix))
    ? [{ label: 'Detail', translationKey: 'breadcrumbs.action.detail' }]
    : [{ label: 'Edit', translationKey: 'breadcrumbs.action.edit' }];
}

function findEntry(entries: NavigationEntry[], pathname: string): NavigationEntry | undefined {
  return entries
    .filter((entry) => pathname === entry.path || pathname.startsWith(`${entry.path}/`))
    .sort((a, b) => b.path.length - a.path.length)[0];
}

function getEntryCrumbs(match: NavigationEntry, pathname: string): Crumb[] {
  return [
    ...match.ancestors.map((ancestor) => ({
      label: ancestor.name,
      translationKey: getNavigationTranslationKey(ancestor),
    })),
    {
      label: match.item.name,
      path: match.path,
      translationKey: getNavigationTranslationKey(match.item),
    },
    ...getSuffixCrumbs(match.path, pathname),
  ];
}

function getAdminCrumbs(pathname: string, navigationConfig?: NavigationConfig): Crumb[] | null {
  if (!pathname.startsWith('/admin/')) return null;
  const match = findEntry(collectEntries(navigationConfig?.admin, ''), pathname);
  return [
    { label: 'Administration', translationKey: 'breadcrumbs.administration' },
    ...(match ? getEntryCrumbs(match, pathname) : []),
  ];
}

function getGlobalCrumbs(pathname: string, navigationConfig?: NavigationConfig): Crumb[] | null {
  if (pathname !== '/marketplace' && pathname !== '/apps') return null;

  const entry = collectEntries(navigationConfig?.mainFeatures, '')
    .find((item) => item.path === pathname);
  const fallbackLabel = pathname === '/apps' ? 'My Apps' : 'Marketplace';
  const label = entry?.item.name ?? fallbackLabel;
  const translationKey = entry
    ? getNavigationTranslationKey(entry.item)
    : NAVIGATION_LABELS[pathname]?.translationKey;
  return [{ label, translationKey }];
}

function getSettingsCrumbs(
  pathname: string,
  appId: string,
  navigationConfig?: NavigationConfig
): Crumb[] | null {
  const settingsBase = `/apps/${appId}/settings`;
  if (pathname !== settingsBase && !pathname.startsWith(`${settingsBase}/`)) return null;

  const crumbs: Crumb[] = [{
    label: 'App Settings',
    path: settingsBase,
    translationKey: 'breadcrumbs.navigation.appSettings',
  }];
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
      : getSuffixCrumbs(settingsBase, pathname)),
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
  const { t } = useTranslation('common');
  const location = useLocation();
  const { appId } = useParams<{ appId?: string }>();
  const appName = useAppName(appId);
  const pathname = location.pathname;

  if (!appId) {
    const crumbs = getAdminCrumbs(pathname, navigationConfig)
      ?? getGlobalCrumbs(pathname, navigationConfig);
    return crumbs ? renderBreadcrumbs(crumbs, t) : null;
  }

  const dashboardPath = `/apps/${appId}`;
  const rootCrumb: Crumb = appName
    ? { label: appName, path: dashboardPath }
    : {
        label: t('breadcrumbs.appFallback', { appId }),
        path: dashboardPath,
      };
  if (pathname === dashboardPath) return renderBreadcrumbs([rootCrumb], t);

  const settingsCrumbs = getSettingsCrumbs(pathname, appId, navigationConfig);
  if (settingsCrumbs) return renderBreadcrumbs([rootCrumb, ...settingsCrumbs], t);

  const entries = [
    ...collectEntries(navigationConfig?.appNavigation, appId),
    ...collectEntries(navigationConfig?.custom, appId),
  ];
  const match = findEntry(entries, pathname);
  return match
    ? renderBreadcrumbs([rootCrumb, ...getEntryCrumbs(match, pathname)], t)
    : null;
};

function renderBreadcrumbs(crumbs: Crumb[], t: (key: string) => string): React.ReactElement | null {
  if (crumbs.length === 0) return null;

  return (
    <nav aria-label={t('breadcrumbs.ariaLabel')} className="flex items-center gap-1">
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
                {crumb.translationKey ? t(crumb.translationKey) : crumb.label}
              </Link>
            ) : (
              <span className="text-[13px] text-fg font-medium whitespace-nowrap dark:text-fg-dark">
                {crumb.translationKey ? t(crumb.translationKey) : crumb.label}
              </span>
            )}
          </React.Fragment>
        );
      })}
    </nav>
  );
}
