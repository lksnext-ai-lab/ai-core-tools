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

export type ServiceKind = 'ai' | 'embedding';
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
