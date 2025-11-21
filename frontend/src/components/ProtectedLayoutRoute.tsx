import React from 'react';
import { Layout } from './layout/Layout';
import ProtectedRoute from './ProtectedRoute';
import AdminRoute from './AdminRoute';
import type { NavigationConfig } from '../core/types';

interface LayoutRouteProps {
  children: React.ReactNode;
  navigationConfig: NavigationConfig;
  headerProps?: {
    title?: string;
    logoUrl?: string;
    [key: string]: any;
  };
  footerProps?: any;
  layoutProps?: any;
  navigationProps?: any;
  showSidebar?: boolean;
  showHeader?: boolean;
  showFooter?: boolean;
  routeType?: 'protected' | 'admin';
}

/**
 * Generic component that wraps content with a route protector and Layout.
 * Can be used for both protected and admin routes.
 */
export const LayoutRoute: React.FC<LayoutRouteProps> = ({
  children,
  navigationConfig,
  headerProps,
  footerProps,
  layoutProps,
  navigationProps,
  showSidebar = true,
  showHeader = true,
  showFooter = true,
  routeType = 'protected',
}) => {
  const RouteWrapper = routeType === 'admin' ? AdminRoute : ProtectedRoute;

  return (
    <RouteWrapper>
      <Layout
        navigationConfig={navigationConfig}
        headerProps={headerProps}
        footerProps={footerProps}
        layoutProps={layoutProps}
        navigationProps={navigationProps}
        showSidebar={showSidebar}
        showHeader={showHeader}
        showFooter={showFooter}
      >
        {children}
      </Layout>
    </RouteWrapper>
  );
};

// Convenience exports for backward compatibility and cleaner code
export const ProtectedLayoutRoute: React.FC<Omit<LayoutRouteProps, 'routeType'>> = (props) => (
  <LayoutRoute {...props} routeType="protected" />
);

export const AdminLayoutRoute: React.FC<Omit<LayoutRouteProps, 'routeType'>> = (props) => (
  <LayoutRoute {...props} routeType="admin" />
);
