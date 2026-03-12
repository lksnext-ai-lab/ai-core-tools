import React from 'react';
import { useLocation, useParams } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
import type { NavigationConfig, NavigationItem } from '../../core/types';

interface PageTitleProps {
  navigationConfig?: NavigationConfig;
}

interface TitlePart {
  label: string;
}

const TOP_LEVEL_PATHS = new Set(['/home', '/marketplace', '/apps', '/about', '/profile']);

const SUFFIX_LABELS: Record<string, string> = {
  playground: 'Playground',
  detail: 'Detail',
  edit: 'Edit',
  new: 'New',
};

function buildPathLookup(
  navigationConfig: NavigationConfig | undefined,
  appId: string
): Map<string, string> {
  const lookup = new Map<string, string>();

  const sections: (NavigationItem[] | undefined)[] = [
    navigationConfig?.mainFeatures,
    navigationConfig?.appNavigation,
    navigationConfig?.settingsNavigation,
    navigationConfig?.settings,
    navigationConfig?.admin,
    navigationConfig?.custom,
  ];

  for (const section of sections) {
    if (!section) continue;
    for (const item of section) {
      const resolvedPath = item.path.replace(':appId', appId);
      lookup.set(resolvedPath, item.name);
    }
  }

  return lookup;
}

export const PageTitle: React.FC<PageTitleProps> = ({ navigationConfig }) => {
  const location = useLocation();
  const { appId } = useParams<{ appId?: string }>();

  const pathname = location.pathname;

  // No title for top-level pages or when outside an app
  if (!appId) return null;
  if (TOP_LEVEL_PATHS.has(pathname)) return null;

  // No title on app dashboard itself
  const dashboardPath = `/apps/${appId}`;
  if (pathname === dashboardPath) return null;

  const pathLookup = buildPathLookup(navigationConfig, appId);
  const parts: TitlePart[] = [];

  const settingsBase = `/apps/${appId}/settings`;
  const adminPrefixes = ['/admin/users', '/admin/stats', '/admin/settings'];

  // Admin routes
  const isAdminRoute = adminPrefixes.some((p) => pathname === p || pathname.startsWith(p + '/'));
  if (isAdminRoute) {
    parts.push({ label: 'Administration' });
    const label = pathLookup.get(pathname);
    if (label) parts.push({ label });
    return renderTitle(parts);
  }

  // Settings sub-routes
  if (pathname !== settingsBase && pathname.startsWith(settingsBase + '/')) {
    parts.push({ label: 'App Settings' });
    const label = pathLookup.get(pathname);
    parts.push({ label: label || 'Edit' });
    return renderTitle(parts);
  }

  // Settings page itself
  if (pathname === settingsBase) {
    parts.push({ label: 'App Settings' });
    return renderTitle(parts);
  }

  // Direct match (e.g. /apps/:appId/agents)
  const directLabel = pathLookup.get(pathname);
  if (directLabel) {
    parts.push({ label: directLabel });
    return renderTitle(parts);
  }

  // Walk up segments iteratively until we find a match
  const segments = pathname.split('/').filter(Boolean);
  for (let i = segments.length - 1; i >= 2; i--) {
    const candidatePath = '/' + segments.slice(0, i).join('/');
    const candidateLabel = pathLookup.get(candidatePath);
    if (candidateLabel) {
      parts.push({ label: candidateLabel });
      const lastSegment = segments[segments.length - 1];
      parts.push({ label: SUFFIX_LABELS[lastSegment] || 'Edit' });
      break;
    }
  }

  if (parts.length === 0) return null;
  return renderTitle(parts);
};

function renderTitle(parts: TitlePart[]): React.ReactElement | null {
  if (parts.length === 0) return null;

  return (
    <div className="flex items-center gap-1.5">
      {parts.map((part, index) => (
        <React.Fragment key={`${part.label}-${index}`}>
          {index > 0 && (
            <ChevronRight size={14} className="text-gray-400 flex-shrink-0" />
          )}
          <span
            className={
              index === parts.length - 1 && parts.length > 1
                ? 'text-sm text-gray-500'
                : 'text-sm font-medium text-gray-700'
            }
          >
            {part.label}
          </span>
        </React.Fragment>
      ))}
    </div>
  );
}
