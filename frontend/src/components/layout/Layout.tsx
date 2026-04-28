import React from 'react';
import { Header } from '../header/Header';
import { Sidebar } from '../sidebar/Sidebar';
import { Footer } from '../footer/Footer';
import { PageTitle } from '../header/PageTitle';
import QuotaWarningBanner from '../QuotaWarningBanner';
import type { NavigationConfig } from '../../core/types';

interface LayoutProps {
  children: React.ReactNode;
  navigationConfig?: NavigationConfig;
  headerProps?: {
    className?: string;
    children?: React.ReactNode;
    title?: string;
    logoUrl?: string;
  };
  sidebarProps?: {
    className?: string;
    children?: React.ReactNode;
    title?: string;
    logoUrl?: string;
  };
  footerProps?: {
    className?: string;
    children?: React.ReactNode;
    showVersion?: boolean;
  };
  layoutProps?: {
    mainClassName?: string;
    className?: string;
  };
  navigationProps?: {
    className?: string;
    showIcons?: boolean;
  };
  mainProps?: {
    className?: string;
  };
  showSidebar?: boolean;
  showHeader?: boolean;
  showFooter?: boolean;
}

export const Layout: React.FC<LayoutProps> = ({
  children,
  navigationConfig,
  headerProps = {},
  sidebarProps = {},
  footerProps = {},
  mainProps = {},
  showSidebar = true,
  showHeader = true,
  showFooter = true
}) => {
  return (
    <div className="h-screen overflow-hidden bg-gray-50 flex flex-col">
      {/* Full-width Header */}
      {showHeader && (
        <Header
          navigationConfig={navigationConfig}
          title={sidebarProps?.title || headerProps?.title}
          logoUrl={sidebarProps?.logoUrl || headerProps?.logoUrl}
          {...headerProps}
        >
          {headerProps?.children ?? <PageTitle navigationConfig={navigationConfig} />}
        </Header>
      )}

      <QuotaWarningBanner />

      {/* Main Content Row — min-h-0 lets children shrink below their intrinsic
          size so the sidebar's tall nav never pushes the document past 100vh */}
      <div className="flex-1 flex overflow-hidden min-h-0">
        {/* Sidebar */}
        {showSidebar && (
          <Sidebar
            navigationConfig={navigationConfig}
            {...sidebarProps}
          />
        )}

        {/* Main Content Area */}
        <div className="flex-1 flex flex-col overflow-hidden min-h-0 min-w-0">
          {/* Page Content — owns its own scroll so the sidebar never pushes it */}
          <main className={`flex-1 min-h-0 overflow-auto p-6 ${mainProps.className || ''}`}>
            {children}
          </main>
          
          {/* Footer */}
          {showFooter && (
            <Footer {...footerProps} />
          )}
        </div>
      </div>
    </div>
  );
};
