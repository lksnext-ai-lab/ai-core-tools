export type ConflictMode = 'fail' | 'rename' | 'override';

export type ComponentType =
  | 'ai_service'
  | 'embedding_service'
  | 'output_parser'
  | 'mcp_config'
  | 'silo'
  | 'repository'
  | 'domain'
  | 'agent'
  | 'app';

export interface ComponentPreviewItem {
  component_type: ComponentType;
  component_name: string;
  bundled: boolean;
  has_conflict: boolean;
  existing_id: number | null;
  warnings: string[];
  needs_api_key: boolean;
  provider: string | null;
}

export interface DependencyInfo {
  source_type: string;
  source_name: string;
  depends_on_type: string;
  depends_on_name: string;
  mandatory: boolean;
  bundled: boolean;
}

export interface AgentImportPreview {
  valid: boolean;
  export_version: string;
  agent: ComponentPreviewItem;
  ai_service: ComponentPreviewItem | null;
  silo: ComponentPreviewItem | null;
  silo_embedding_service: ComponentPreviewItem | null;
  silo_output_parser: ComponentPreviewItem | null;
  output_parser: ComponentPreviewItem | null;
  mcp_configs: ComponentPreviewItem[];
  agent_tools: ComponentPreviewItem[];
  dependencies: DependencyInfo[];
  global_warnings: string[];
  requires_ai_service_selection: boolean;
}

export interface AppImportPreview {
  valid: boolean;
  export_version: string;
  app_name: string;
  ai_services: ComponentPreviewItem[];
  embedding_services: ComponentPreviewItem[];
  output_parsers: ComponentPreviewItem[];
  mcp_configs: ComponentPreviewItem[];
  silos: ComponentPreviewItem[];
  repositories: ComponentPreviewItem[];
  domains: ComponentPreviewItem[];
  agents: ComponentPreviewItem[];
  dependencies: DependencyInfo[];
  component_counts: Record<string, number>;
  global_warnings: string[];
}

export interface AgentImportOptions {
  conflictMode: ConflictMode;
  newName?: string;
  selectedAIServiceId?: number;
  importBundledSilo?: boolean;
  importBundledOutputParser?: boolean;
  importBundledMCPConfigs?: boolean;
  importBundledAgentTools?: boolean;
}

export interface AppImportOptions {
  conflictMode: ConflictMode;
  newAppName?: string;
  componentSelection?: Record<string, string[]>;
  apiKeys?: Record<string, string>;
}

export interface ImportResponse {
  success: boolean;
  message: string;
  summary?: {
    component_type: string;
    component_id: number;
    component_name: string;
    mode: ConflictMode;
    created: boolean;
    dependencies_created?: string[];
    warnings?: string[];
    next_steps?: string[];
  };
}

export interface FullAppImportResponse {
  success: boolean;
  message: string;
  summary?: {
    app_name: string;
    app_id: number;
    total_components: number;
    components_imported: Record<string, number>;
    components_skipped: Record<string, number>;
    total_warnings: string[];
    total_errors: string[];
    duration_seconds: number;
  };
}

export const COMPONENT_TYPE_LABELS: Record<string, string> = {
  ai_service: 'AI Service',
  embedding_service: 'Embedding Service',
  output_parser: 'Output Parser',
  mcp_config: 'MCP Config',
  silo: 'Silo',
  repository: 'Repository',
  domain: 'Domain',
  agent: 'Agent',
  app: 'App',
};

export const COMPONENT_TYPE_ICONS: Record<string, string> = {
  ai_service: 'AI',
  embedding_service: 'Embed',
  output_parser: 'Parser',
  mcp_config: 'MCP',
  silo: 'Silo',
  repository: 'Repo',
  domain: 'Domain',
  agent: 'Agent',
  app: 'App',
};
