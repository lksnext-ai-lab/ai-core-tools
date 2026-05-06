export type SharePointSyncStatus = 'IDLE' | 'RUNNING' | 'SUCCESS' | 'PARTIAL' | 'ERROR';
export type SharePointFileStatus = 'PENDING' | 'INDEXED' | 'ERROR';

export interface SharePointFile {
  id: number;
  drive_item_id: string;
  name: string | null;
  path: string | null;
  web_url: string | null;
  mime_type: string | null;
  size_bytes: number | null;
  last_modified_at: string | null;
  status: SharePointFileStatus;
  last_synced_at: string | null;
  error_message: string | null;
}

export interface SharePointSource {
  id: number;
  app_id: number;
  silo_id: number;
  name: string;
  description: string | null;
  tenant_id: string;
  client_id: string;
  site_id: string;
  site_name: string | null;
  site_url: string | null;
  drive_id: string;
  drive_name: string | null;
  file_extension_filters: string[] | null;
  last_synced_at: string | null;
  last_sync_status: SharePointSyncStatus;
  last_sync_error: string | null;
  refresh_interval_minutes: number | null;
  next_run_at: string | null;
  created_at: string;
  updated_at: string;
  file_count: number;
}

export interface SharePointSourceDetail extends SharePointSource {
  files: SharePointFile[];
}

export interface SharePointSourceCreateRequest {
  name: string;
  description?: string;
  tenant_id: string;
  client_id: string;
  client_secret: string;
  site_id: string;
  site_name?: string;
  site_url?: string;
  drive_id: string;
  drive_name?: string;
  file_extension_filters?: string[];
  embedding_service_id?: number;
  vector_db_type?: string;
  silo_name: string;
}

export interface SharePointSourceUpdateRequest {
  name?: string;
  description?: string;
  file_extension_filters?: string[];
  tenant_id?: string;
  client_id?: string;
  client_secret?: string;
}

export interface MicrosoftSite {
  id: string;
  name: string;
  web_url: string;
}

export interface MicrosoftDrive {
  id: string;
  name: string;
  drive_type: string | null;
}

export interface TestConnectionRequest {
  tenant_id: string;
  client_id: string;
  client_secret: string;
  site_id?: string;
  drive_id?: string;
}

export interface Capabilities {
  sharepoint?: { enabled: boolean; version?: string };
  [key: string]: { enabled: boolean; version?: string } | undefined;
}
