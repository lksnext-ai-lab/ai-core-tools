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
    audience?: string;
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

export interface Skill {
  skill_id: number;
  name: string;
  description?: string;
  content?: string;
  created_at: string;
}

// MCP Server types - for exposing agents as MCP tools
export interface MCPServerAgent {
  agent_id: number;
  agent_name: string;
  agent_description?: string;
  tool_name_override?: string;
  tool_description_override?: string;
  is_available: boolean;  // Whether agent is still valid (exists and is_tool=true)
  unavailable_reason?: string;  // Reason if not available
}

// Agent MCP usage info
export interface AgentMCPUsage {
  agent_id: number;
  is_tool: boolean;
  mcp_servers: Array<{
    server_id: number;
    server_name: string;
    app_id: number;
  }>;
  used_in_mcp_servers: boolean;
}

export interface MCPConnectionHints {
  claude_desktop: Record<string, unknown>;
  cursor: Record<string, unknown>;
  curl_example: string;
  endpoint_url: string;
  endpoint_url_by_id: string;
}

export interface MCPServer {
  server_id: number;
  name: string;
  slug: string;
  description?: string;
  is_active: boolean;
  rate_limit: number;
  agent_count?: number;
  endpoint_url: string;
  endpoint_url_by_id?: string;
  agents?: MCPServerAgent[];
  connection_hints?: MCPConnectionHints;
  create_date?: string;
  update_date?: string;
}

export interface MCPServerListItem {
  server_id: number;
  name: string;
  slug: string;
  description?: string;
  is_active: boolean;
  agent_count: number;
  endpoint_url: string;
  create_date?: string;
}

export interface CreateMCPServer {
  name: string;
  slug?: string;
  description?: string;
  is_active?: boolean;
  rate_limit?: number;
  agent_ids?: number[];
}

export interface UpdateMCPServer {
  name?: string;
  slug?: string;
  description?: string;
  is_active?: boolean;
  rate_limit?: number;
  agent_ids?: number[];
}

export interface AppSlugInfo {
  app_id: number;
  slug?: string;
  mcp_base_url: string;
}

export interface ToolAgent {
  agent_id: number;
  name: string;
  description?: string;
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
