import React from 'react';
import { Header } from '../Header/Header';
import { Sidebar } from '../Sidebar/Sidebar';
import { Footer } from '../Footer/Footer';
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
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* Full-width Header */}
      {showHeader && (
        <Header 
          navigationConfig={navigationConfig}
          title={sidebarProps?.title || headerProps?.title}
          logoUrl={sidebarProps?.logoUrl || headerProps?.logoUrl}
          {...headerProps}
        />
      )}

      {/* Main Content Row */}
      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar */}
        {showSidebar && (
          <Sidebar 
            navigationConfig={navigationConfig}
            {...sidebarProps}
          />
        )}

        {/* Main Content Area */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Page Content */}
          <main className={`flex-1 overflow-x-auto overflow-y-visible p-6 ${mainProps.className || ''}`}>
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
