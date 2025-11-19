import React from 'react';
import { Layout } from './layout/Layout';
import ProtectedRoute from './ProtectedRoute';
import type { NavigationConfig } from '../core/types';

interface ProtectedLayoutRouteProps {
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
}

/**
 * Reusable component that wraps content with ProtectedRoute and Layout.
 * This eliminates duplication across route definitions.
 */
export const ProtectedLayoutRoute: React.FC<ProtectedLayoutRouteProps> = ({
  children,
  navigationConfig,
  headerProps,
  footerProps,
  layoutProps,
  navigationProps,
  showSidebar = true,
  showHeader = true,
  showFooter = true,
}) => {
  return (
    <ProtectedRoute>
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
    </ProtectedRoute>
  );
};
