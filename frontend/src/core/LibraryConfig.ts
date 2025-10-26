import type { ThemeConfig, NavigationConfig } from './types';
import type { AuthProps } from '../auth/AuthConfig';

export interface LibraryConfig {
  // Basic configuration
  name?: string;
  logo?: string;
  favicon?: string;
  homePage?: React.ComponentType;
  
  // Theme configuration
  themeProps?: {
    defaultTheme?: string;
    customThemes?: Record<string, ThemeConfig>;
    showThemeSelector?: boolean;
  };
  
  // Layout configuration
  headerProps?: {
    title?: string;
    logoUrl?: string;
    className?: string;
    children?: React.ReactNode;
  };
  
  footerProps?: {
    copyright?: string;
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
  
  // Navigation configuration
  navigationConfig?: NavigationConfig;
  
  // Authentication configuration
  authProps?: AuthProps;
  
  // API configuration
  apiConfig?: {
    baseUrl?: string;
    timeout?: number;
    retries?: number;
  };
  
  // Feature configuration
  features?: {
    showSidebar?: boolean;
    showHeader?: boolean;
    showFooter?: boolean;
    showThemeSelector?: boolean;
  };
}
