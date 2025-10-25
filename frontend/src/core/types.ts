export interface ClientConfig {
  clientId: string;
  name: string;
  theme: ThemeConfig;
  auth: AuthConfig;
  branding: BrandingConfig;
  api?: ApiConfig;
  navigation?: NavigationConfig;
  features?: FeatureConfig;
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
  settings?: NavigationItem[];
  admin?: NavigationItem[];
  custom?: NavigationItem[];
}
