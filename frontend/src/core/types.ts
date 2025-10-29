export interface ClientConfig {
  clientId: string;
  name: string;
  theme: ThemeConfig;
  auth: AuthConfig;
  branding: BrandingConfig;
  api?: ApiConfig;
  navigation?: NavigationConfig;
  features?: FeatureConfig;
  homePage?: React.ComponentType; // Allow client to override home page
}

export interface ThemeConfig {
  name: string;
  colors: {
    primary: string;
    secondary: string;
    accent: string;
    background: string;
    surface: string;
    text: string;
  };
  logo?: string;
  favicon?: string;
  customStyles?: string;
}

export interface AuthConfig {
  type: 'session' | 'oidc';
  oidc?: {
    enabled: boolean;
    authority: string;
    clientId: string;
    redirectUri: string;
    scope?: string;
  };
}

export interface ApiConfig {
  baseUrl: string;
  timeout?: number;
  retries?: number;
}

export interface BrandingConfig {
  companyName: string;
  logo: string;
  favicon: string;
  headerTitle?: string;
}

export interface ExtraRoute {
  path: string;
  element: React.ReactNode;
  name?: string;
  protected?: boolean;
  adminOnly?: boolean;  // Requires admin privileges (is_admin === true)
}

export interface FeatureConfig {
  enabledModules?: string[];
  customPages?: CustomPage[];
  extraRoutes?: ExtraRoute[];
}

export interface CustomPage {
  path: string;
  component: React.ComponentType;
  name: string;
  protected?: boolean;
}

export interface MCPConfig {
  config_id: number;
  name: string;
  description?: string;
  transport_type?: string;
  created_at: string;
}

export interface NavigationItem {
  path: string;
  name: string;
  icon?: string;
  section?: string;
  protected?: boolean;
  adminOnly?: boolean;
}

export interface NavigationConfig {
  mainFeatures?: NavigationItem[];
  appNavigation?: NavigationItem[];
  settings?: NavigationItem[];
  admin?: NavigationItem[];
  custom?: NavigationItem[];
}

// New extensible navigation types
export interface NavigationOverride {
  path: string;
  name?: string;
  icon?: string;
  section?: string;
  protected?: boolean;
  adminOnly?: boolean;
  hidden?: boolean; // Hide this navigation item
}

export interface NavigationAdditions {
  mainFeatures?: NavigationItem[];
  appNavigation?: NavigationItem[];
  settings?: NavigationItem[];
  admin?: NavigationItem[];
  custom?: NavigationItem[];
}

export interface ExtensibleNavigationConfig {
  // Add new navigation items
  add?: NavigationAdditions;
  // Override existing navigation items
  override?: NavigationOverride[];
  // Remove navigation items by path
  remove?: string[];
}

// Re-export LibraryConfig from LibraryConfig.ts
export type { LibraryConfig } from './LibraryConfig';
