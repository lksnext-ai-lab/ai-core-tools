import React from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
import type { NavigationConfig, NavigationItem } from '../../core/types';

interface BreadcrumbsProps {
  navigationConfig?: NavigationConfig;
}

interface Crumb {
  label: string;
  path?: string; // undefined = current page (not clickable)
}

// Paths that should never show breadcrumbs (no appId context)
const TOP_LEVEL_PATHS = new Set(['/home', '/marketplace', '/apps', '/about', '/profile']);

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

export const Breadcrumbs: React.FC<BreadcrumbsProps> = ({ navigationConfig }) => {
  const location = useLocation();
  const { appId } = useParams<{ appId?: string }>();

  const pathname = location.pathname;

  // No appId: only suppress on known top-level paths
  if (!appId) {
    if (TOP_LEVEL_PATHS.has(pathname)) return null;
    // Unknown top-level path outside an app — nothing useful to show
    return null;
  }

  // Inside an app but on the dashboard itself — header already shows app name
  const dashboardPath = `/apps/${appId}`;
  if (pathname === dashboardPath) return null;

  const pathLookup = buildPathLookup(navigationConfig, appId);

  const crumbs: Crumb[] = [];
  const settingsBase = `/apps/${appId}/settings`;
  const adminPrefixes = ['/admin/users', '/admin/stats', '/admin/settings'];

  // Admin routes: prefix with "Administration"
  const isAdminRoute = adminPrefixes.some((p) => pathname === p || pathname.startsWith(p + '/'));
  if (isAdminRoute) {
    crumbs.push({ label: 'Administration' });
    const label = pathLookup.get(pathname);
    if (label) {
      crumbs.push({ label });
    }
    return renderBreadcrumbs(crumbs);
  }

  // Settings sub-routes: add "App Settings" as parent crumb
  if (pathname !== settingsBase && pathname.startsWith(settingsBase + '/')) {
    crumbs.push({ label: 'App Settings', path: settingsBase });
    const label = pathLookup.get(pathname);
    if (label) {
      crumbs.push({ label });
    } else {
      // Unknown sub-page inside settings
      crumbs.push({ label: 'Edit' });
    }
    return renderBreadcrumbs(crumbs);
  }

  // Settings page itself
  if (pathname === settingsBase) {
    crumbs.push({ label: 'App Settings' });
    return renderBreadcrumbs(crumbs);
  }

  // Direct app-section pages (e.g. /apps/:appId/agents)
  const directLabel = pathLookup.get(pathname);
  if (directLabel) {
    crumbs.push({ label: directLabel });
    return renderBreadcrumbs(crumbs);
  }

  // Sub-pages of app sections (e.g. /apps/:appId/agents/new or /apps/:appId/agents/456)
  // Find the longest matching parent path
  const parts = pathname.split('/').filter(Boolean);
  // Walk up one level: remove last segment to get parent
  const parentPath = '/' + parts.slice(0, parts.length - 1).join('/');
  const parentLabel = pathLookup.get(parentPath);

  if (parentLabel) {
    crumbs.push({ label: parentLabel, path: parentPath });
    const lastSegment = parts[parts.length - 1];
    // "new" stays as "New", numeric IDs become "Edit"
    const isNew = lastSegment === 'new';
    crumbs.push({ label: isNew ? 'New' : 'Edit' });
    return renderBreadcrumbs(crumbs);
  }

  // Nothing matched — render nothing
  return null;
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
                className="text-sm text-gray-500 hover:text-gray-700 transition-colors"
              >
                {crumb.label}
              </Link>
            ) : (
              <span className="text-sm text-gray-700 font-medium">
                {crumb.label}
              </span>
            )}
          </React.Fragment>
        );
      })}
    </nav>
  );
}
