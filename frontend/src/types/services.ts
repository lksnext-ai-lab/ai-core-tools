/**
 * Shared types for the AI Service / Embedding Service wizard.
 * Mirrors `backend/schemas/provider_models_schemas.py` — keep them in sync.
 */

export interface ProviderCapabilities {
  readonly chat: boolean;
  readonly embedding: boolean;
  readonly vision: boolean;
  readonly audio: boolean;
  readonly function_calling: boolean;
  readonly tool_use: boolean;
  readonly reasoning: boolean;
  readonly json_mode: boolean;
}

export type ModelInfoSource = 'api' | 'catalog' | 'heuristic';

export interface ProviderModelInfo {
  readonly id: string;
  readonly display_name: string;
  readonly family: string | null;
  readonly capabilities: ProviderCapabilities;
  readonly context_window: number | null;
  readonly owned_by: string | null;
  readonly deprecated: boolean;
  /** Unix timestamp (seconds) when the provider released the model.
   *  Captured per-adapter from the SDK response — null for providers
   *  that don't expose a timestamp (e.g. Google AI Studio). Drives the
   *  recency sort and the "New" badge in ModelSelectionStep. */
  readonly created_at: number | null;
  readonly source: ModelInfoSource;
}

export type ListPurpose = 'chat' | 'embedding';

export interface ListProviderModelsRequest {
  provider: string;
  api_key: string;
  base_url?: string;
  api_version?: string;
  // AWS Bedrock identifiers. The secret access key travels in `api_key`;
  // these non-secret fields carry the access key id and region.
  aws_access_key_id?: string;
  aws_region?: string;
  // server overrides this — sending it is a no-op but keeps the type honest
  purpose?: ListPurpose;
}

export interface ListProviderModelsResponse {
  readonly provider: string;
  readonly models: readonly ProviderModelInfo[];
  readonly warnings: readonly string[];
  readonly requires_manual_input: boolean;
}

export type ServiceKind = 'ai' | 'embedding' | 'sandbox';
export type ServiceScope = 'app' | 'system';
export type ServiceWizardMode = 'create' | 'edit-model';

/** Shape persisted on create/update — same fields the legacy form sent. */
export interface ServiceFormData {
  name: string;
  provider: string;
  model_name: string;
  api_key: string;
  base_url: string;
  api_version?: string;
  supports_video?: boolean;
  // AWS Bedrock identifiers (non-secret). The secret access key is sent
  // via `api_key`; these carry the access key id and region.
  aws_access_key_id?: string;
  aws_region?: string;
}

/** Existing service shape returned by getAIService / getEmbeddingService. */
export interface ExistingService {
  readonly service_id: number;
  readonly name: string;
  readonly provider: string;
  readonly model_name: string;
  readonly api_key: string; // already masked when coming from the backend
  readonly base_url: string;
  readonly supports_video?: boolean;
  readonly api_version?: string;
  readonly aws_access_key_id?: string;
  readonly aws_region?: string;
}

/**
 * Shape persisted on create/update for a Sandbox Service. There is no
 * `model_name` concept — the sandbox providers (OpenSandbox, Daytona, E2B)
 * expose an isolated code-execution environment, not a language model.
 * Field names mirror `CreateUpdateSandboxServiceSchema` on the backend
 * (`backend/schemas/sandbox_service_schemas.py`) exactly so payloads pass
 * through without renaming.
 */
export interface SandboxServiceFormData {
  name: string;
  provider: string;
  api_key: string;
  base_url: string;
  // Provider-specific extra_config fields (non-secret).
  opensandbox_image?: string;
  daytona_target?: string;
  daytona_workspace?: string;
  daytona_cpu?: number;
  daytona_memory_gb?: number;
  e2b_template?: string;
  e2b_workspace?: string;
}

/** Existing sandbox service shape returned by the sandbox service detail endpoints. */
export interface ExistingSandboxService {
  readonly service_id: number;
  readonly name: string;
  readonly provider: string;
  readonly api_key: string; // already masked when coming from the backend
  readonly base_url: string;
  readonly created_at?: string;
  readonly is_system?: boolean;
  readonly needs_api_key?: boolean;
  readonly opensandbox_image?: string;
  readonly daytona_target?: string;
  readonly daytona_workspace?: string;
  readonly daytona_cpu?: number;
  readonly daytona_memory_gb?: number;
  readonly e2b_template?: string;
  readonly e2b_workspace?: string;
}
