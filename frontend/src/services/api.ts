import { configService } from '../core/ConfigService';
import { authService } from './auth';
import { getCsrfToken } from './cookies';
import type { StreamEvent } from '../types/streaming';

/** Non-2xx HTTP error; callers can branch on `.status` without string-sniffing. */
export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = 'ApiError';
  }
}
import type {
  MarketplaceCatalogParams,
  MarketplaceCatalogResponse,
  MarketplaceAgentDetail,
  MarketplaceConversation,
  MarketplaceProfile,
  MarketplaceProfileUpdate,
  MarketplaceVisibility,
  AgentRatingResponse,
  UserRatingResponse,
  MarketplaceQuotaUsage,
} from '../types/marketplace';
import type {
  CrawlPolicy,
  CrawlPolicyInput,
  CrawlJob,
  CrawlJobListResponse,
  TriggerCrawlResponse,
  DomainUrlDetail,
  DomainUrlListResponse,
  DomainUrlActionResponse,
} from '../types/crawl';

type ConflictMode = 'fail' | 'rename' | 'override';

const MUTATING_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

// DeploymentModeContext cannot be read here (not a hook), so it writes the
// resolved auth mode via setApiAuthMode(). The default is derived from the
// env/runtime OIDC flag so early requests (e.g. CapabilitiesContext) already
// use the correct mode before the context resolves /internal/config.
const _rc = (globalThis as Record<string, unknown>).__RUNTIME_CONFIG__ as Record<string, string> | undefined;
const _oidcDefault = _rc?.VITE_OIDC_ENABLED === undefined
  ? import.meta.env.VITE_OIDC_ENABLED === 'true'
  : _rc.VITE_OIDC_ENABLED === 'true';
let _apiAuthMode: 'oidc' | 'local' = _oidcDefault ? 'oidc' : 'local';

export function setApiAuthMode(mode: 'oidc' | 'local'): void {
  _apiAuthMode = mode;
}

class ApiService {
  private get baseURL(): string {
    return configService.getApiBaseUrl();
  }

  // Coalesces concurrent 401-triggered refreshes into a single in-flight promise.
  private _refreshPromise: Promise<boolean> | null = null;

  private async _doRefresh(): Promise<boolean> {
    if (!this._refreshPromise) {
      this._refreshPromise = authService.refresh().finally(() => {
        this._refreshPromise = null;
      });
    }
    return this._refreshPromise;
  }

  // Called when a refresh fails or a retried request still 401s (LOCAL mode only).
  private clearClientAuthAndRedirect(): void {
    // Use logout() (not clearAuth()) to clear the httpOnly session cookies. Best-effort.
    authService.logout().catch(() => {}).finally(() => {
      if (typeof globalThis !== 'undefined' && globalThis.location) {
        globalThis.location.href = '/login';
      }
    });
  }

  // LOCAL: cookies carry auth; CSRF header on mutating calls. OIDC: Authorization bearer.
  private buildAuthHeaders(method: string | undefined, isFormData: boolean): Record<string, string> {
    const headers: Record<string, string> = {};

    if (!isFormData) {
      headers['Content-Type'] = 'application/json';
    }

    const effectiveMethod = (method ?? 'GET').toUpperCase();

    if (_apiAuthMode === 'oidc') {
      const token = authService.getOIDCToken();
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
    } else {
      if (MUTATING_METHODS.has(effectiveMethod)) {
        const csrf = getCsrfToken();
        if (csrf) {
          headers['X-CSRF-Token'] = csrf;
        }
      }
    }

    return headers;
  }

  private extractErrorMessage(errorData: unknown): string | null {
    if (!errorData || typeof errorData !== 'object') return null;
    const data = errorData as Record<string, unknown>;

    if (typeof data['error'] === 'string') return data['error'];
    if (data['detail'] !== undefined) {
      return typeof data['detail'] === 'string'
        ? data['detail']
        : JSON.stringify(data['detail']);
    }
    if (typeof data['message'] === 'string') return data['message'];
    return null;
  }

  private async handleResponseError(response: Response): Promise<never> {
    let message = `API Error: ${response.status} ${response.statusText}`;

    try {
      const errorData: unknown = await response.json();
      const extracted = this.extractErrorMessage(errorData);
      if (extracted) {
        message = extracted;
      }
    } catch (error) {
      console.debug('Failed to parse error response JSON:', error);
      if (response.status === 403) {
        message = 'You do not have permission to perform this action.';
      }
    }

    throw new ApiError(message, response.status);
  }

  async request(
    endpoint: string,
    options: RequestInit = {},
    _isRetryAfterRefresh = false,
    _requestOptions: { suppressAuthRedirect?: boolean } = {},
  ): Promise<unknown> {
    const url = `${this.baseURL}${endpoint}`;
    const authHeaders = this.buildAuthHeaders(
      typeof options.method === 'string' ? options.method : 'GET',
      options.body instanceof FormData,
    );

    const config: RequestInit = {
      ...options,
      credentials: 'include',
      headers: {
        ...authHeaders,
        ...(options.headers as Record<string, string> | undefined),
      },
    };

    const response = await fetch(url, config);

    if (response.status === 401) {
      // Callers that probe optional endpoints can suppress the hard redirect.
      if (_requestOptions.suppressAuthRedirect) {
        throw new Error('Authentication required');
      }

      // OIDC re-auth is owned by oidc-client-ts / OIDCProvider / ProtectedRoute.
      if (_apiAuthMode === 'oidc') {
        throw new Error('Authentication required');
      }

      const isRefreshEndpoint = endpoint.includes('/auth/refresh');
      if (!_isRetryAfterRefresh && !isRefreshEndpoint) {
        const refreshed = await this._doRefresh();
        if (refreshed) {
          // Cookie may have rotated — rebuild headers on retry.
          return this.request(endpoint, options, true, _requestOptions);
        }
      }
      this.clearClientAuthAndRedirect();
      throw new Error('Authentication required');
    }

    if (!response.ok) {
      await this.handleResponseError(response);
    }

    if (response.status === 204) return null;
    return response.json();
  }

  async getApps() {
    return this.request('/internal/apps/');
  }

  async getApp(appId: number) {
    return this.request(`/internal/apps/${appId}`);
  }

  async createApp(data: { name: string; langsmith_api_key?: string; agent_rate_limit?: number; max_file_size_mb?: number; agent_cors_origins?: string }) {
    return this.request('/internal/apps/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateApp(appId: number, data: { name: string; langsmith_api_key?: string; agent_rate_limit?: number; max_file_size_mb?: number; agent_cors_origins?: string; enable_openai_api?: boolean }) {
    return this.request(`/internal/apps/${appId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async testAppLangsmith(appId: number, apiKey?: string): Promise<{
    valid: boolean;
    status: 'ok' | 'unauthorized' | 'network' | 'unknown';
    message: string;
    project_name?: string | null;
    source?: 'app' | 'env' | 'request' | null;
  }> {
    return this.request(`/internal/apps/${appId}/langsmith/test`, {
      method: 'POST',
      body: JSON.stringify({ api_key: apiKey ?? null }),
    });
  }

  async dismissOnboarding(appId: number) {
    return this.request(`/internal/apps/${appId}/onboarding-dismissed`, {
      method: 'PATCH',
    });
  }

  async deleteApp(appId: number) {
    return this.request(`/internal/apps/${appId}`, {
      method: 'DELETE',
    });
  }

  async leaveApp(appId: number) {
    return this.request(`/internal/apps/${appId}/leave`, {
      method: 'POST',
    });
  }

  async getUsageStats() {
    return this.request('/internal/usage-stats/');
  }

  async getAppUsageStats(appId: number) {
    return this.request(`/internal/usage-stats/${appId}`);
  }

  async getPendingInvitations() {
    return this.request('/internal/auth/pending-invitations');
  }

  async respondToInvitation(invitationId: number, action: 'accept' | 'decline') {
    return this.request(`/internal/auth/invitations/${invitationId}/respond`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    });
  }

  async register(email: string, password: string) {
    return this.request('/internal/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
  }

  async getAgents(appId: number) {
    return this.request(`/internal/apps/${appId}/agents/`);
  }

  async getAgent(appId: number, agentId: number) {
    return this.request(`/internal/apps/${appId}/agents/${agentId}`);
  }

  async createAgent(appId: number, agentId: number, data: any) {
    return this.request(`/internal/apps/${appId}/agents/${agentId}`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateAgent(appId: number, agentId: number, data: any) {
    return this.createAgent(appId, agentId, data);
  }

  async deleteAgent(appId: number, agentId: number) {
    return this.request(`/internal/apps/${appId}/agents/${agentId}`, {
      method: 'DELETE',
    });
  }

  async getAgentMCPUsage(appId: number, agentId: number) {
    return this.request(`/internal/apps/${appId}/agents/${agentId}/mcp-usage`);
  }

  async updateAgentPrompt(appId: number, agentId: number, promptType: 'system' | 'template', prompt: string) {
    return this.request(`/internal/apps/${appId}/agents/${agentId}/update-prompt`, {
      method: 'POST',
      body: JSON.stringify({
        type: promptType,
        prompt: prompt
      }),
    });
  }

  async resetAgentConversation(appId: number, agentId: number, conversationId?: number | null) {
    const params = conversationId ? `?conversation_id=${conversationId}` : '';
    return this.request(`/internal/apps/${appId}/agents/${agentId}/reset${params}`, {
      method: 'POST',
    });
  }

  async getConversationHistory(appId: number, agentId: number) {
    return this.request(`/internal/apps/${appId}/agents/${agentId}/conversation-history`, {
      method: 'GET',
    });
  }

  async exportAgent(
    appId: number,
    agentId: number,
    includeAIService: boolean = true,
    includeSilo: boolean = true,
    includeOutputParser: boolean = true,
    includeMCPConfigs: boolean = true,
    includeAgentTools: boolean = true
  ): Promise<Blob> {
    const headers = this.buildAuthHeaders('POST', false);

    const params = new URLSearchParams({
      include_ai_service: String(includeAIService),
      include_silo: String(includeSilo),
      include_output_parser: String(includeOutputParser),
      include_mcp_configs: String(includeMCPConfigs),
      include_agent_tools: String(includeAgentTools),
    });

    const response = await fetch(
      `${this.baseURL}/internal/apps/${appId}/agents/${agentId}/export?${params}`,
      {
        method: 'POST',
        credentials: 'include',
        headers,
      }
    );

    if (!response.ok) {
      await this.handleResponseError(response);
    }

    return response.blob();
  }

  async importAgent(
    appId: number,
    file: File,
    conflictMode: ConflictMode,
    newName?: string,
    selectedAIServiceId?: number,
    selectedSiloId?: number,
    selectedOutputParserId?: number
  ) {
    const formData = new FormData();
    formData.append('file', file);

    const headers = this.buildAuthHeaders('POST', true);

    let url = `${this.baseURL}/internal/apps/${appId}/agents/import?conflict_mode=${conflictMode}`;
    if (newName) {
      url += `&new_name=${encodeURIComponent(newName)}`;
    }
    if (selectedAIServiceId !== undefined) {
      url += `&selected_ai_service_id=${selectedAIServiceId}`;
    }
    if (selectedSiloId !== undefined) {
      url += `&selected_silo_id=${selectedSiloId}`;
    }
    if (selectedOutputParserId !== undefined) {
      url += `&selected_output_parser_id=${selectedOutputParserId}`;
    }

    const response = await fetch(url, {
      method: 'POST',
      credentials: 'include',
      headers,
      body: formData,
    });

    if (!response.ok) {
      await this.handleResponseError(response);
    }

    return response.json();
  }

  async getAIServices(appId: number) {
    return this.request(`/internal/apps/${appId}/ai-services/`);
  }

  async getAIService(appId: number, serviceId: number) {
    return this.request(`/internal/apps/${appId}/ai-services/${serviceId}`);
  }

  async createAIService(appId: number, data: any) {
    return this.request(`/internal/apps/${appId}/ai-services/0`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateAIService(appId: number, serviceId: number, data: any) {
    return this.request(`/internal/apps/${appId}/ai-services/${serviceId}`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async copyAIService(appId: number, serviceId: number) {
    return this.request(`/internal/apps/${appId}/ai-services/${serviceId}/copy`, {
      method: 'POST',
    });
  }
  
  async deleteAIService(appId: number, serviceId: number) {
    return this.request(`/internal/apps/${appId}/ai-services/${serviceId}`, {
      method: 'DELETE',
    });
  }

  async testAIServiceConnection(appId: number, serviceId: number) {
    return this.request(`/internal/apps/${appId}/ai-services/${serviceId}/test`, {
      method: 'POST',
    });
  }

  async testAIServiceConnectionWithConfig(appId: number, data: any, serviceId?: number) {
    const qs = serviceId != null ? `?service_id=${serviceId}` : '';
    return this.request(`/internal/apps/${appId}/ai-services/test-connection${qs}`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async listAIServiceProviderModels(
    appId: number,
    body: import('../types/services').ListProviderModelsRequest,
  ): Promise<import('../types/services').ListProviderModelsResponse> {
    return this.request(`/internal/apps/${appId}/ai-services/list-models`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  async exportAIService(appId: number, serviceId: number): Promise<Blob> {
    const headers = this.buildAuthHeaders('POST', false);

    const response = await fetch(
      `${this.baseURL}/internal/apps/${appId}/ai-services/${serviceId}/export`,
      {
        method: 'POST',
        credentials: 'include',
        headers,
      }
    );

    if (!response.ok) {
      await this.handleResponseError(response);
    }

    return response.blob();
  }

  async importAIService(
    appId: number,
    file: File,
    conflictMode: ConflictMode,
    newName?: string
  ) {
    const formData = new FormData();
    formData.append('file', file);

    const headers = this.buildAuthHeaders('POST', true);

    let url = `${this.baseURL}/internal/apps/${appId}/ai-services/import?conflict_mode=${conflictMode}`;
    if (newName) {
      url += `&new_name=${encodeURIComponent(newName)}`;
    }

    const response = await fetch(url, {
      method: 'POST',
      credentials: 'include',
      headers,
      body: formData,
    });

    if (!response.ok) {
      await this.handleResponseError(response);
    }

    return response.json();
  }

  async getEmbeddingServices(appId: number) {
    return this.request(`/internal/apps/${appId}/embedding-services/`);
  }

  async getEmbeddingService(appId: number, serviceId: number) {
    return this.request(`/internal/apps/${appId}/embedding-services/${serviceId}`);
  }

  async createEmbeddingService(appId: number, data: any) {
    return this.request(`/internal/apps/${appId}/embedding-services/0`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateEmbeddingService(appId: number, serviceId: number, data: any) {
    return this.request(`/internal/apps/${appId}/embedding-services/${serviceId}`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async deleteEmbeddingService(appId: number, serviceId: number) {
    return this.request(`/internal/apps/${appId}/embedding-services/${serviceId}`, {
      method: 'DELETE',
    });
  }

  async listEmbeddingServiceProviderModels(
    appId: number,
    body: import('../types/services').ListProviderModelsRequest,
  ): Promise<import('../types/services').ListProviderModelsResponse> {
    return this.request(`/internal/apps/${appId}/embedding-services/list-models`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  async testEmbeddingServiceConnectionWithConfig(appId: number, data: any, serviceId?: number) {
    const qs = serviceId != null ? `?service_id=${serviceId}` : '';
    return this.request(`/internal/apps/${appId}/embedding-services/test-connection${qs}`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async exportEmbeddingService(appId: number, serviceId: number): Promise<Blob> {
    const headers = this.buildAuthHeaders('POST', false);

    const response = await fetch(
      `${this.baseURL}/internal/apps/${appId}/embedding-services/${serviceId}/export`,
      {
        method: 'POST',
        credentials: 'include',
        headers,
      }
    );

    if (!response.ok) {
      await this.handleResponseError(response);
    }

    return response.blob();
  }

  async importEmbeddingService(
    appId: number,
    file: File,
    conflictMode: ConflictMode,
    newName?: string
  ) {
    const formData = new FormData();
    formData.append('file', file);

    const headers = this.buildAuthHeaders('POST', true);

    let url = `${this.baseURL}/internal/apps/${appId}/embedding-services/import?conflict_mode=${conflictMode}`;
    if (newName) {
      url += `&new_name=${encodeURIComponent(newName)}`;
    }

    const response = await fetch(url, {
      method: 'POST',
      credentials: 'include',
      headers,
      body: formData,
    });

    if (!response.ok) {
      await this.handleResponseError(response);
    }

    return response.json();
  }

  async getMCPConfigs(appId: number) {
    return this.request(`/internal/apps/${appId}/mcp-configs/`);
  }

  async getMCPConfig(appId: number, configId: number) {
    return this.request(`/internal/apps/${appId}/mcp-configs/${configId}`);
  }

  async createMCPConfig(appId: number, data: any) {
    return this.request(`/internal/apps/${appId}/mcp-configs/0`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateMCPConfig(appId: number, configId: number, data: any) {
    return this.request(`/internal/apps/${appId}/mcp-configs/${configId}`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async deleteMCPConfig(appId: number, configId: number) {
    return this.request(`/internal/apps/${appId}/mcp-configs/${configId}`, {
      method: 'DELETE',
    });
  }

  async testMCPConnection(appId: number, configId: number) {
    return this.request(`/internal/apps/${appId}/mcp-configs/${configId}/test`, {
      method: 'POST',
    });
  }

  async testMCPConnectionWithConfig(appId: number, data: any) {
    return this.request(`/internal/apps/${appId}/mcp-configs/test-connection`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async exportMCPConfig(appId: number, configId: number): Promise<Blob> {
    const headers = this.buildAuthHeaders('POST', false);

    const response = await fetch(
      `${this.baseURL}/internal/apps/${appId}/mcp-configs/${configId}/export`,
      {
        method: 'POST',
        credentials: 'include',
        headers,
      }
    );

    if (!response.ok) {
      await this.handleResponseError(response);
    }

    return response.blob();
  }

  async importMCPConfig(
    appId: number,
    file: File,
    conflictMode: ConflictMode,
    newName?: string
  ) {
    const formData = new FormData();
    formData.append('file', file);

    const headers = this.buildAuthHeaders('POST', true);

    let url = `${this.baseURL}/internal/apps/${appId}/mcp-configs/import?conflict_mode=${conflictMode}`;
    if (newName) {
      url += `&new_name=${encodeURIComponent(newName)}`;
    }

    const response = await fetch(url, {
      method: 'POST',
      credentials: 'include',
      headers,
      body: formData,
    });

    if (!response.ok) {
      await this.handleResponseError(response);
    }

    return response.json();
  }
  async getSkills(appId: number) {
    return this.request(`/internal/apps/${appId}/skills/`);
  }

  async getSkill(appId: number, skillId: number) {
    return this.request(`/internal/apps/${appId}/skills/${skillId}`);
  }

  async createSkill(appId: number, data: any) {
    return this.request(`/internal/apps/${appId}/skills/0`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateSkill(appId: number, skillId: number, data: any) {
    return this.request(`/internal/apps/${appId}/skills/${skillId}`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async deleteSkill(appId: number, skillId: number) {
    return this.request(`/internal/apps/${appId}/skills/${skillId}`, {
      method: 'DELETE',
    });
  }

  async getMCPServers(appId: number) {
    return this.request(`/internal/apps/${appId}/mcp-servers/`);
  }

  async getMCPServer(appId: number, serverId: number) {
    return this.request(`/internal/apps/${appId}/mcp-servers/${serverId}`);
  }

  async createMCPServer(appId: number, data: any) {
    return this.request(`/internal/apps/${appId}/mcp-servers/`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateMCPServer(appId: number, serverId: number, data: any) {
    return this.request(`/internal/apps/${appId}/mcp-servers/${serverId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteMCPServer(appId: number, serverId: number) {
    return this.request(`/internal/apps/${appId}/mcp-servers/${serverId}`, {
      method: 'DELETE',
    });
  }

  async getMCPServerToolAgents(appId: number) {
    return this.request(`/internal/apps/${appId}/mcp-servers/tool-agents`);
  }

  async getAppSlugInfo(appId: number) {
    return this.request(`/internal/apps/${appId}/mcp-servers/slug/info`);
  }

  async updateAppSlug(appId: number, slug: string) {
    return this.request(`/internal/apps/${appId}/mcp-servers/slug`, {
      method: 'PUT',
      body: JSON.stringify({ slug }),
    });
  }

  async getAPIKeys(appId: number) {
    return this.request(`/internal/apps/${appId}/api-keys/`);
  }

  async getAPIKey(appId: number, keyId: number) {
    return this.request(`/internal/apps/${appId}/api-keys/${keyId}`);
  }

  async createAPIKey(appId: number, data: any) {
    return this.request(`/internal/apps/${appId}/api-keys/0`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateAPIKey(appId: number, keyId: number, data: any) {
    return this.request(`/internal/apps/${appId}/api-keys/${keyId}`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async deleteAPIKey(appId: number, keyId: number) {
    return this.request(`/internal/apps/${appId}/api-keys/${keyId}`, {
      method: 'DELETE',
    });
  }

  async toggleAPIKey(appId: number, keyId: number) {
    return this.request(`/internal/apps/${appId}/api-keys/${keyId}/toggle`, {
      method: 'POST',
    });
  }

  async getOutputParsers(appId: number) {
    return this.request(`/internal/apps/${appId}/output-parsers/`);
  }

  async getOutputParser(appId: number, parserId: number) {
    return this.request(`/internal/apps/${appId}/output-parsers/${parserId}`);
  }

  async createOutputParser(appId: number, data: any) {
    return this.request(`/internal/apps/${appId}/output-parsers/0`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateOutputParser(appId: number, parserId: number, data: any) {
    return this.request(`/internal/apps/${appId}/output-parsers/${parserId}`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async deleteOutputParser(appId: number, parserId: number) {
    return this.request(`/internal/apps/${appId}/output-parsers/${parserId}`, {
      method: 'DELETE',
    });
  }

  async exportOutputParser(appId: number, parserId: number): Promise<Blob> {
    const headers = this.buildAuthHeaders('POST', false);

    const response = await fetch(
      `${this.baseURL}/internal/apps/${appId}/output-parsers/${parserId}/export`,
      {
        method: 'POST',
        credentials: 'include',
        headers,
      }
    );

    if (!response.ok) {
      await this.handleResponseError(response);
    }

    return response.blob();
  }

  async importOutputParser(
    appId: number,
    file: File,
    conflictMode: ConflictMode,
    newName?: string
  ) {
    const formData = new FormData();
    formData.append('file', file);

    const headers = this.buildAuthHeaders('POST', true);

    let url = `${this.baseURL}/internal/apps/${appId}/output-parsers/import?conflict_mode=${conflictMode}`;
    if (newName) {
      url += `&new_name=${encodeURIComponent(newName)}`;
    }

    const response = await fetch(url, {
      method: 'POST',
      credentials: 'include',
      headers,
      body: formData,
    });

    if (!response.ok) {
      await this.handleResponseError(response);
    }

    return response.json();
  }

  async searchPlatformUsers(q: string): Promise<Array<{ user_id: number; name: string; email: string; platform_role: string }>> {
    return this.request(`/internal/users/search?q=${encodeURIComponent(q)}`);
  }

  async getCollaborators(appId: number) {
    return this.request(`/internal/collaboration/?app_id=${appId}`);
  }

  async inviteCollaborator(appId: number, email: string, role: string = 'editor') {
    return this.request(`/internal/collaboration/invite?app_id=${appId}`, {
      method: 'POST',
      body: JSON.stringify({
        email,
        role
      }),
    });
  }

  async updateCollaboratorRole(appId: number, userId: number, role: string) {
    return this.request(`/internal/collaboration/${userId}/role?app_id=${appId}`, {
      method: 'PUT',
      body: JSON.stringify({
        role
      }),
    });
  }

  async removeCollaborator(appId: number, userId: number) {
    return this.request(`/internal/collaboration/${userId}?app_id=${appId}`, {
      method: 'DELETE',
    });
  }

  async getMyInvitations() {
    return this.request(`/internal/collaboration/my-invitations`);
  }

  async respondToCollaborationInvitation(collaborationId: number, action: 'accept' | 'decline') {
    return this.request(`/internal/collaboration/invitations/${collaborationId}/respond`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    });
  }

  async uploadMedia(appId: number, repositoryId: number, files: File[], folderId?: number, config?: {
    forced_language?: string;
    chunk_min_duration?: number;
    chunk_max_duration?: number;
    chunk_overlap?: number;
  }) {
    const formData = new FormData();

    files.forEach(file => formData.append('files', file));

    if (folderId !== undefined && folderId !== null) {
      formData.append('folder_id', folderId.toString());
    }

    if (config?.forced_language) formData.append('forced_language', config.forced_language);
    if (config?.chunk_min_duration) formData.append('chunk_min_duration', config.chunk_min_duration.toString());
    if (config?.chunk_max_duration) formData.append('chunk_max_duration', config.chunk_max_duration.toString());
    if (config?.chunk_overlap) formData.append('chunk_overlap', config.chunk_overlap.toString());

    return this.request(`/internal/apps/${appId}/repositories/${repositoryId}/media`, {
      method: 'POST',
      body: formData,
    });
  }

  async addYouTube(appId: number, repositoryId: number, url: string, folderId?: number, config?: {
    forced_language?: string;
    chunk_min_duration?: number;
    chunk_max_duration?: number;
    chunk_overlap?: number;
  }) {
    const formData = new FormData();

    formData.append('url', url);
    if (folderId !== undefined && folderId !== null) {
      formData.append('folder_id', folderId.toString());
    }
    if (config?.forced_language) formData.append('forced_language', config.forced_language);
    if (config?.chunk_min_duration) formData.append('chunk_min_duration', config.chunk_min_duration.toString());
    if (config?.chunk_max_duration) formData.append('chunk_max_duration', config.chunk_max_duration.toString());
    if (config?.chunk_overlap) formData.append('chunk_overlap', config.chunk_overlap.toString());

    return this.request(`/internal/apps/${appId}/repositories/${repositoryId}/media/youtube`, {
      method: 'POST',
      body: formData,
    });
  }

  async getMediaStatus(appId: number, repositoryId: number, mediaId: number) {
    return this.request(`/internal/apps/${appId}/repositories/${repositoryId}/media/${mediaId}`);
  }

  async listMedia(appId: number, repositoryId: number, folderId?: number) {
    const params = folderId === undefined ? '' : `?folder_id=${folderId}`;
    return this.request(`/internal/apps/${appId}/repositories/${repositoryId}/media${params}`);
  }

  async moveMedia(appId: number, repositoryId: number, mediaId: number, newFolderId?: number) {
    const formData = new FormData();
    if (newFolderId !== undefined) {
      formData.append('new_folder_id', newFolderId.toString());
    }
    
    return this.request(`/internal/apps/${appId}/repositories/${repositoryId}/media/${mediaId}/move`, {
      method: 'POST',
      body: formData,
    });
  }

  async deleteMedia(appId: number, repositoryId: number, mediaId: number) {
    return this.request(`/internal/apps/${appId}/repositories/${repositoryId}/media/${mediaId}`, {
      method: 'DELETE',
    })
  }

  // ==================== PLAYGROUND MEDIA API ====================

  async uploadPlaygroundMedia(appId: number, agentId: number, sessionId: string, files: File[], config?: {
    transcription_service_id?: number;
    video_ai_service_id?: number;
    embedding_service_id?: number;
    forced_language?: string;
    chunk_min_duration?: number;
    chunk_max_duration?: number;
    chunk_overlap?: number;
  }) {
    const formData = new FormData();

    files.forEach(file => formData.append('files', file));
    formData.append('session_id', sessionId);
    
    if (config?.transcription_service_id) formData.append('transcription_service_id', config.transcription_service_id.toString());
    if (config?.video_ai_service_id) formData.append('video_ai_service_id', config.video_ai_service_id.toString());
    if (config?.embedding_service_id) formData.append('embedding_service_id', config.embedding_service_id.toString());
    if (config?.forced_language) formData.append('forced_language', config.forced_language);
    if (config?.chunk_min_duration) formData.append('chunk_min_duration', config.chunk_min_duration.toString());
    if (config?.chunk_max_duration) formData.append('chunk_max_duration', config.chunk_max_duration.toString());
    if (config?.chunk_overlap) formData.append('chunk_overlap', config.chunk_overlap.toString());

    return this.request(`/internal/apps/${appId}/agents/${agentId}/playground-media`, {
      method: 'POST',
      body: formData,
    });
  }

  async addPlaygroundYouTube(appId: number, agentId: number, sessionId: string, url: string, config?: {
    transcription_service_id?: number;
    video_ai_service_id?: number;
    embedding_service_id?: number;
    forced_language?: string;
    chunk_min_duration?: number;
    chunk_max_duration?: number;
    chunk_overlap?: number;
  }) {
    const formData = new FormData();

    formData.append('url', url);
    formData.append('session_id', sessionId);
    
    if (config?.transcription_service_id) formData.append('transcription_service_id', config.transcription_service_id.toString());
    if (config?.video_ai_service_id) formData.append('video_ai_service_id', config.video_ai_service_id.toString());
    if (config?.embedding_service_id) formData.append('embedding_service_id', config.embedding_service_id.toString());
    if (config?.forced_language) formData.append('forced_language', config.forced_language);
    if (config?.chunk_min_duration) formData.append('chunk_min_duration', config.chunk_min_duration.toString());
    if (config?.chunk_max_duration) formData.append('chunk_max_duration', config.chunk_max_duration.toString());
    if (config?.chunk_overlap) formData.append('chunk_overlap', config.chunk_overlap.toString());

    return this.request(`/internal/apps/${appId}/agents/${agentId}/playground-media/youtube`, {
      method: 'POST',
      body: formData,
    });
  }

  async listPlaygroundMedia(appId: number, agentId: number, sessionId: string) {
    return this.request(`/internal/apps/${appId}/agents/${agentId}/playground-media?session_id=${encodeURIComponent(sessionId)}`);
  }

  async deletePlaygroundMedia(appId: number, agentId: number, sessionId: string) {
    return this.request(`/internal/apps/${appId}/agents/${agentId}/playground-media?session_id=${encodeURIComponent(sessionId)}`, {
      method: 'DELETE',
    });
  }

  async fetchPlaygroundMediaBlob(appId: number, agentId: number, mediaId: number, sessionId: string): Promise<Blob> {
    const url = this.getPlaygroundMediaStreamUrl(appId, agentId, mediaId, sessionId);
    const headers = this.buildAuthHeaders('GET', false);
    const response = await fetch(url, { headers, credentials: 'include' });
    if (!response.ok) {
      throw new Error(`Failed to fetch media: ${response.status}`);
    }
    return response.blob();
  }

  /**
   * Build the direct stream URL for a playground media item. Used as the
   * <video>/<audio> `src` so the browser can issue HTTP Range requests for
   * true seeking instead of downloading the whole file into memory. The
   * session cookie is sent automatically for same-origin requests.
   */
  getPlaygroundMediaStreamUrl(appId: number, agentId: number, mediaId: number, sessionId: string): string {
    return `${this.baseURL}/internal/apps/${appId}/agents/${agentId}/playground-media/${mediaId}/stream?session_id=${encodeURIComponent(sessionId)}`;
  }

  // ==================== SILOS API ====================
  async getSilos(appId: number) {
    return this.request(`/internal/apps/${appId}/silos/`);
  }

  async getSilo(appId: number, siloId: number) {
    return this.request(`/internal/apps/${appId}/silos/${siloId}`);
  }

  async getSiloOptions(appId: number) {
    return this.request(`/internal/apps/${appId}/silos/0`);
  }

  async createSilo(appId: number, data: { name: string; description?: string; embedding_service_id?: number; vector_db_type?: string; fixed_metadata?: boolean }) {
    return this.request(`/internal/apps/${appId}/silos/`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateSilo(appId: number, siloId: number, data: { name: string; description?: string; fixed_metadata?: boolean; status?: string }) {
    return this.request(`/internal/apps/${appId}/silos/${siloId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteSilo(appId: number, siloId: number) {
    return this.request(`/internal/apps/${appId}/silos/${siloId}`, {
      method: 'DELETE',
    });
  }

  async exportSilo(appId: number, siloId: number, includeDependencies: boolean = true): Promise<Blob> {
    const headers = this.buildAuthHeaders('POST', false);

    const response = await fetch(
      `${this.baseURL}/internal/apps/${appId}/silos/${siloId}/export?include_dependencies=${includeDependencies}`,
      {
        method: 'POST',
        credentials: 'include',
        headers,
      }
    );

    if (!response.ok) {
      await this.handleResponseError(response);
    }

    return response.blob();
  }

  async importSilo(
    appId: number,
    file: File,
    conflictMode: ConflictMode,
    newName?: string,
    selectedEmbeddingServiceId?: number
  ) {
    const formData = new FormData();
    formData.append('file', file);

    const headers = this.buildAuthHeaders('POST', true);

    let url = `${this.baseURL}/internal/apps/${appId}/silos/import?conflict_mode=${conflictMode}`;
    if (newName) {
      url += `&new_name=${encodeURIComponent(newName)}`;
    }
    if (selectedEmbeddingServiceId !== undefined) {
      url += `&selected_embedding_service_id=${selectedEmbeddingServiceId}`;
    }

    const response = await fetch(url, {
      method: 'POST',
      credentials: 'include',
      headers,
      body: formData,
    });

    if (!response.ok) {
      await this.handleResponseError(response);
    }

    return response.json();
  }

  async searchSiloDocuments(
    appId: number,
    siloId: number,
    query: string,
    limit?: number,
    filterMetadata?: Record<string, any>,
    searchOptions?: {
      searchType?: string;
      scoreThreshold?: number;
      fetchK?: number;
      lambdaMult?: number;
      minContentLength?: number;
      maxContentLength?: number;
    },
  ) {
    return this.request(`/internal/apps/${appId}/silos/${siloId}/search`, {
      method: 'POST',
      body: JSON.stringify({
        query,
        ...(limit !== undefined ? { limit } : {}),
        filter_metadata: filterMetadata,
        ...(searchOptions?.searchType && searchOptions.searchType !== 'similarity' ? { search_type: searchOptions.searchType } : {}),
        ...(searchOptions?.scoreThreshold !== undefined ? { score_threshold: searchOptions.scoreThreshold } : {}),
        ...(searchOptions?.fetchK !== undefined ? { fetch_k: searchOptions.fetchK } : {}),
        ...(searchOptions?.lambdaMult !== undefined ? { lambda_mult: searchOptions.lambdaMult } : {}),
        ...(searchOptions?.minContentLength != null && { min_content_length: searchOptions.minContentLength }),
        ...(searchOptions?.maxContentLength != null && { max_content_length: searchOptions.maxContentLength }),
      }),
    });
  }

  async searchSiloDocumentsWithTiming(
    appId: number,
    siloId: number,
    query: string,
    limit?: number,
    filterMetadata?: Record<string, unknown>,
    searchOptions?: {
      searchType?: string;
      scoreThreshold?: number;
      fetchK?: number;
      lambdaMult?: number;
      minContentLength?: number;
      maxContentLength?: number;
    },
  ): Promise<{ data: unknown; serverMs: number | null }> {
    const url = `${this.baseURL}/internal/apps/${appId}/silos/${siloId}/search`;
    const body = JSON.stringify({
      query,
      ...(limit !== undefined ? { limit } : {}),
      filter_metadata: filterMetadata,
      ...(searchOptions?.searchType && searchOptions.searchType !== 'similarity'
        ? { search_type: searchOptions.searchType }
        : {}),
      ...(searchOptions?.scoreThreshold !== undefined
        ? { score_threshold: searchOptions.scoreThreshold }
        : {}),
      ...(searchOptions?.fetchK !== undefined ? { fetch_k: searchOptions.fetchK } : {}),
      ...(searchOptions?.lambdaMult !== undefined ? { lambda_mult: searchOptions.lambdaMult } : {}),
      ...(searchOptions?.minContentLength != null && { min_content_length: searchOptions.minContentLength }),
      ...(searchOptions?.maxContentLength != null && { max_content_length: searchOptions.maxContentLength }),
    });
    const headers = this.buildAuthHeaders('POST', false);
    const response = await fetch(url, { method: 'POST', body, credentials: 'include', headers });
    if (!response.ok) {
      await this.handleResponseError(response);
    }
    const serverMsHeader = response.headers.get('x-server-time-ms');
    const serverMs = serverMsHeader !== null ? parseInt(serverMsHeader, 10) : null;
    const data: unknown = await response.json();
    return { data, serverMs };
  }

  async getSiloNeighbors(
    appId: number | string,
    siloId: number | string,
    sourceType: string,
    sourceId: string,
  ) {
    return this.request(
      `/internal/apps/${appId}/silos/${siloId}/documents/neighbors?source_type=${encodeURIComponent(sourceType)}&source_id=${encodeURIComponent(sourceId)}`,
    );
  }

  async getSiloMetadataValues(
    appId: number | string,
    siloId: number | string,
    field: string,
    prefix?: string,
    limit = 100,
  ) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (prefix) params.set('prefix', prefix);
    return this.request(
      `/internal/apps/${appId}/silos/${siloId}/metadata/${encodeURIComponent(field)}/values?${params}`,
    );
  }

  async deleteSiloDocuments(appId: number, siloId: number, documentIds: string[]) {
    return this.request(`/internal/apps/${appId}/silos/${siloId}/documents`, {
      method: 'DELETE',
      body: JSON.stringify({ document_ids: documentIds }),
    });
  }

  async countSiloDocuments(
    appId: number | string,
    siloId: number | string,
    filterMetadata?: Record<string, unknown> | null,
    minContentLength?: number | null,
    maxContentLength?: number | null,
  ) {
    return this.request(`/internal/apps/${appId}/silos/${siloId}/documents/count`, {
      method: 'POST',
      body: JSON.stringify({
        filter_metadata: filterMetadata ?? null,
        ...(minContentLength != null && { min_content_length: minContentLength }),
        ...(maxContentLength != null && { max_content_length: maxContentLength }),
      }),
    });
  }

  async reindexSiloResource(
    appId: number | string,
    siloId: number | string,
    resourceId: number | string,
  ) {
    return this.request(
      `/internal/apps/${appId}/silos/${siloId}/resources/${resourceId}/reindex`,
      { method: 'POST' },
    );
  }

  async getRepositories(appId: number) {
    return this.request(`/internal/apps/${appId}/repositories/`);
  }

  async getRepository(appId: number, repositoryId: number) {
    return this.request(`/internal/apps/${appId}/repositories/${repositoryId}`);
  }

  async createRepository(appId: number, data: { name: string; embedding_service_id?: number; vector_db_type?: string; transcription_service_id?: number; video_ai_service_id?: number }) {
    return this.request(`/internal/apps/${appId}/repositories/`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateRepository(appId: number, repositoryId: number, data: { name: string; embedding_service_id?: number; vector_db_type?: string; transcription_service_id?: number; video_ai_service_id?: number }) {
    return this.request(`/internal/apps/${appId}/repositories/${repositoryId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteRepository(appId: number, repositoryId: number) {
    return this.request(`/internal/apps/${appId}/repositories/${repositoryId}`, {
      method: 'DELETE',
    });
  }

  async uploadResources(appId: number, repositoryId: number, files: File[], folderId?: number) {
    const formData = new FormData();
    files.forEach(file => formData.append('files', file));

    if (folderId !== undefined && folderId !== null) {
      formData.append('folder_id', folderId.toString());
    }

    return this.request(`/internal/apps/${appId}/repositories/${repositoryId}/resources`, {
      method: 'POST',
      body: formData,
    });
  }

  async deleteResource(appId: number, repositoryId: number, resourceId: number) {
    return this.request(`/internal/apps/${appId}/repositories/${repositoryId}/resources/${resourceId}`, {
      method: 'DELETE',
    });
  }

  async moveResource(appId: number, repositoryId: number, resourceId: number, newFolderId?: number) {
    const formData = new FormData();
    if (newFolderId !== undefined) {
      formData.append('new_folder_id', newFolderId.toString());
    }
    
    return this.request(`/internal/apps/${appId}/repositories/${repositoryId}/resources/${resourceId}/move`, {
      method: 'POST',
      body: formData,
    });
  }

  async downloadResource(appId: number, repositoryId: number, resourceId: number) {
    const headers = this.buildAuthHeaders('GET', false);

    const response = await fetch(
      `${this.baseURL}/internal/apps/${appId}/repositories/${repositoryId}/resources/${resourceId}/download`,
      {
        method: 'GET',
        credentials: 'include',
        headers,
      }
    );

    if (!response.ok) {
      throw new Error(`Download failed: ${response.status} ${response.statusText}`);
    }

    return response.blob();
  }

  async searchRepositoryDocuments(appId: number, repositoryId: number, query: string, limit: number = 10, filterMetadata?: Record<string, any>) {
    return this.request(`/internal/apps/${appId}/repositories/${repositoryId}/search`, {
      method: 'POST',
      body: JSON.stringify({
        query,
        limit,
        filter_metadata: filterMetadata
      }),
    });
  }

  async chatWithAgent(appId: number, agentId: number, message: string, files?: File[], searchParams?: any, conversationId?: number | null) {
    const formData = new FormData();
    formData.append('message', message);
    
    if (searchParams) {
      formData.append('search_params', JSON.stringify(searchParams));
    }
    
    if (conversationId) {
      formData.append('conversation_id', conversationId.toString());
    }
    
    if (files && files.length > 0) {
      files.forEach((file) => {
        formData.append(`files`, file);
      });
    }

    return this.request(`/internal/apps/${appId}/agents/${agentId}/chat`, {
      method: 'POST',
      body: formData,
    });
  }

  private parseSSELines(lines: string[], onEvent: (event: StreamEvent) => void): void {
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed?.startsWith('data: ')) continue;
      try {
        const event = JSON.parse(trimmed.slice(6)) as StreamEvent;
        onEvent(event);
      } catch (parseError) {
        console.warn('Failed to parse SSE event:', trimmed, parseError);
      }
    }
  }

  // EventSource only supports GET, so SSE is consumed via ReadableStream over fetch POST.
  async chatWithAgentStream(
    appId: number,
    agentId: number,
    message: string,
    options: {
      files?: File[];
      searchParams?: unknown;
      conversationId?: number | null;
      onEvent: (event: StreamEvent) => void;
      signal?: AbortSignal;
    }
  ): Promise<void> {
    const formData = new FormData();
    formData.append('message', message);

    if (options.searchParams) {
      formData.append('search_params', JSON.stringify(options.searchParams));
    }
    if (options.conversationId) {
      formData.append('conversation_id', options.conversationId.toString());
    }
    if (options.files && options.files.length > 0) {
      options.files.forEach((file) => formData.append('files', file));
    }

    const url = `${this.baseURL}/internal/apps/${appId}/agents/${agentId}/chat/stream`;
    const headers = this.buildAuthHeaders('POST', true);

    const response = await fetch(url, {
      method: 'POST',
      credentials: 'include',
      headers,
      body: formData,
      signal: options.signal,
    });

    if (!response.ok) {
      await this.handleResponseError(response);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('ReadableStream not supported');
    }

    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';

        this.parseSSELines(lines, options.onEvent);
      }
    } finally {
      reader.releaseLock();
    }
  }

  async uploadFileForChat(appId: number, agentId: number, file: File, conversationId?: number | null) {
    const formData = new FormData();
    formData.append('file', file);

    if (conversationId) {
      formData.append('conversation_id', conversationId.toString());
    }

    return this.request(`/internal/apps/${appId}/agents/${agentId}/upload-file`, {
      method: 'POST',
      body: formData,
    });
  }

  async listAttachedFiles(appId: number, agentId: number, conversationId?: number | null) {
    const url = conversationId
      ? `/internal/apps/${appId}/agents/${agentId}/files?conversation_id=${conversationId}`
      : `/internal/apps/${appId}/agents/${agentId}/files`;
    return this.request(url);
  }

  async removeAttachedFile(appId: number, agentId: number, fileId: string, conversationId?: number | null) {
    const url = conversationId
      ? `/internal/apps/${appId}/agents/${agentId}/files/${fileId}?conversation_id=${conversationId}`
      : `/internal/apps/${appId}/agents/${agentId}/files/${fileId}`;
    return this.request(url, {
      method: 'DELETE',
    });
  }

  async getFileDownloadUrl(appId: number, agentId: number, fileId: string, conversationId?: number | null): Promise<string> {
    const base = `/internal/apps/${appId}/agents/${agentId}/files/${fileId}/download`;
    const url = conversationId ? `${base}?conversation_id=${conversationId}` : base;
    const response = await this.request(url, { method: 'GET' });
    return response.download_url as string;
  }

  async processOCR(appId: number, agentId: number, file: File) {
    const formData = new FormData();
    formData.append('pdf_file', file);

    return this.request(`/internal/apps/${appId}/ocr/${agentId}/process`, {
      method: 'POST',
      body: formData,
    });
  }

  async getDomains(appId: number) {
    return this.request(`/internal/apps/${appId}/domains/`);
  }

  async getDomain(appId: number, domainId: number) {
    return this.request(`/internal/apps/${appId}/domains/${domainId}`);
  }

  async createDomain(
    appId: number,
    data: {
      name: string;
      description?: string;
      base_url: string;
      content_tag?: string;
      content_class?: string;
      content_id?: string;
      embedding_service_id?: number;
      vector_db_type?: string;
    }
  ) {
    return this.request(`/internal/apps/${appId}/domains/`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateDomain(
    appId: number,
    domainId: number,
    data: {
      name: string;
      description?: string;
      base_url: string;
      content_tag?: string;
      content_class?: string;
      content_id?: string;
    }
  ) {
    return this.request(`/internal/apps/${appId}/domains/${domainId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteDomain(appId: number, domainId: number) {
    return this.request(`/internal/apps/${appId}/domains/${domainId}`, {
      method: 'DELETE',
    });
  }

  async listDomainUrls(
    appId: number,
    domainId: number,
    params: {
      page?: number;
      per_page?: number;
      status?: string;
      discovered_via?: string;
      q?: string;
    } = {}
  ): Promise<DomainUrlListResponse> {
    const query = new URLSearchParams();
    if (params.page !== undefined) query.set('page', String(params.page));
    if (params.per_page !== undefined) query.set('per_page', String(params.per_page));
    if (params.status) query.set('status', params.status);
    if (params.discovered_via) query.set('discovered_via', params.discovered_via);
    if (params.q) query.set('q', params.q);
    const qs = query.toString();
    return this.request(`/internal/apps/${appId}/domains/${domainId}/urls${qs ? '?' + qs : ''}`);
  }

  /** @deprecated Use listDomainUrls instead */
  async getDomainUrls(appId: number, domainId: number, page = 1, perPage = 20): Promise<DomainUrlListResponse> {
    return this.listDomainUrls(appId, domainId, { page, per_page: perPage });
  }

  async addDomainUrlManual(
    appId: number,
    domainId: number,
    url: string
  ): Promise<DomainUrlActionResponse> {
    return this.request(`/internal/apps/${appId}/domains/${domainId}/urls`, {
      method: 'POST',
      body: JSON.stringify({ url }),
    });
  }

  /** @deprecated Use addDomainUrlManual instead */
  async addUrlToDomain(appId: number, domainId: number, data: { url: string }): Promise<DomainUrlActionResponse> {
    return this.addDomainUrlManual(appId, domainId, data.url);
  }

  async getDomainUrl(appId: number, domainId: number, urlId: number): Promise<DomainUrlDetail> {
    return this.request(`/internal/apps/${appId}/domains/${domainId}/urls/${urlId}`);
  }

  async deleteDomainUrl(appId: number, domainId: number, urlId: number): Promise<DomainUrlActionResponse> {
    return this.request(`/internal/apps/${appId}/domains/${domainId}/urls/${urlId}`, {
      method: 'DELETE',
    });
  }

  /** @deprecated Use deleteDomainUrl instead */
  async deleteUrlFromDomain(appId: number, domainId: number, urlId: number): Promise<DomainUrlActionResponse> {
    return this.deleteDomainUrl(appId, domainId, urlId);
  }

  async recrawlDomainUrl(appId: number, domainId: number, urlId: number): Promise<DomainUrlActionResponse> {
    return this.request(`/internal/apps/${appId}/domains/${domainId}/urls/${urlId}/recrawl`, {
      method: 'POST',
    });
  }

  async getUrlContent(appId: number, domainId: number, urlId: number) {
    return this.request(`/internal/apps/${appId}/domains/${domainId}/urls/${urlId}/content`);
  }

  async getCrawlPolicy(appId: number, domainId: number): Promise<CrawlPolicy> {
    return this.request(`/internal/apps/${appId}/domains/${domainId}/crawl-policy`);
  }

  async updateCrawlPolicy(appId: number, domainId: number, data: CrawlPolicyInput): Promise<CrawlPolicy> {
    return this.request(`/internal/apps/${appId}/domains/${domainId}/crawl-policy`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async triggerCrawl(appId: number, domainId: number): Promise<TriggerCrawlResponse> {
    return this.request(`/internal/apps/${appId}/domains/${domainId}/crawl-jobs`, {
      method: 'POST',
    });
  }

  async listCrawlJobs(
    appId: number,
    domainId: number,
    params: { page?: number; per_page?: number } = {}
  ): Promise<CrawlJobListResponse> {
    const query = new URLSearchParams();
    if (params.page !== undefined) query.set('page', String(params.page));
    if (params.per_page !== undefined) query.set('per_page', String(params.per_page));
    const qs = query.toString();
    return this.request(`/internal/apps/${appId}/domains/${domainId}/crawl-jobs${qs ? '?' + qs : ''}`);
  }

  async getCrawlJob(appId: number, domainId: number, jobId: number): Promise<CrawlJob> {
    return this.request(`/internal/apps/${appId}/domains/${domainId}/crawl-jobs/${jobId}`);
  }

  async cancelCrawl(appId: number, domainId: number, jobId: number): Promise<CrawlJob> {
    return this.request(`/internal/apps/${appId}/domains/${domainId}/crawl-jobs/${jobId}/cancel`, {
      method: 'POST',
    });
  }

  async getVersion(): Promise<{ name: string; version: string }> {
    const response = await this.request('/internal/version/');
    return response;
  }

  async getFolders(appId: number, repositoryId: number) {
    return this.request(`/internal/apps/${appId}/repositories/${repositoryId}/folders/`);
  }

  async getFolderTree(appId: number, repositoryId: number) {
    return this.request(`/internal/apps/${appId}/repositories/${repositoryId}/folders/tree`);
  }

  async getFolder(appId: number, repositoryId: number, folderId: number) {
    return this.request(`/internal/apps/${appId}/repositories/${repositoryId}/folders/${folderId}`);
  }

  async createFolder(appId: number, repositoryId: number, name: string, parentFolderId?: number) {
    return this.request(`/internal/apps/${appId}/repositories/${repositoryId}/folders/`, {
      method: 'POST',
      body: JSON.stringify({
        name,
        parent_folder_id: parentFolderId || null
      }),
    });
  }

  async updateFolder(appId: number, repositoryId: number, folderId: number, name: string) {
    return this.request(`/internal/apps/${appId}/repositories/${repositoryId}/folders/${folderId}`, {
      method: 'PUT',
      body: JSON.stringify({ name }),
    });
  }

  async deleteFolder(appId: number, repositoryId: number, folderId: number) {
    return this.request(`/internal/apps/${appId}/repositories/${repositoryId}/folders/${folderId}`, {
      method: 'DELETE',
    });
  }

  async moveFolder(appId: number, repositoryId: number, folderId: number, newParentFolderId?: number) {
    return this.request(`/internal/apps/${appId}/repositories/${repositoryId}/folders/${folderId}/move`, {
      method: 'POST',
      body: JSON.stringify({
        new_parent_folder_id: newParentFolderId || null
      }),
    });
  }

  async uploadResourcesToFolder(appId: number, repositoryId: number, folderId: number, files: File[]) {
    return this.uploadResources(appId, repositoryId, files, folderId);
  }

  async createConversation(agentId: number, title?: string) {
    const titleParam = title ? `&title=${encodeURIComponent(title)}` : '';
    return this.request(`/internal/conversations?agent_id=${agentId}${titleParam}`, {
      method: 'POST',
    });
  }

  async listConversations(agentId: number, limit = 50, offset = 0) {
    return this.request(`/internal/conversations?agent_id=${agentId}&limit=${limit}&offset=${offset}`);
  }

  async getConversation(conversationId: number) {
    return this.request(`/internal/conversations/${conversationId}`);
  }

  async getConversationWithHistory(conversationId: number) {
    return this.request(`/internal/conversations/${conversationId}/history`);
  }

  async updateConversation(conversationId: number, data: { title?: string }) {
    return this.request(`/internal/conversations/${conversationId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  async deleteConversation(conversationId: number) {
    return this.request(`/internal/conversations/${conversationId}`, {
      method: 'DELETE',
    });
  }

  async getMarketplaceCatalog(
    params: MarketplaceCatalogParams = {},
  ): Promise<MarketplaceCatalogResponse> {
    const queryParams = new URLSearchParams();
    if (params.search) queryParams.set('search', params.search);
    if (params.category) queryParams.set('category', params.category);
    if (params.my_apps_only) queryParams.set('my_apps_only', 'true');
    if (params.page) queryParams.set('page', String(params.page));
    if (params.page_size) queryParams.set('page_size', String(params.page_size));
    if (params.sort_by) queryParams.set('sort_by', params.sort_by);
    const qs = queryParams.toString();
    const endpoint = qs
      ? '/internal/marketplace/agents?' + qs
      : '/internal/marketplace/agents';
    return this.request(endpoint);
  }

  async getMarketplaceAgentDetail(
    agentId: number,
  ): Promise<MarketplaceAgentDetail> {
    return this.request(`/internal/marketplace/agents/${agentId}`);
  }

  async getMarketplaceCategories(): Promise<{ categories: string[] }> {
    return this.request('/internal/marketplace/categories');
  }

  async rateMarketplaceAgent(
    agentId: number,
    rating: number,
  ): Promise<AgentRatingResponse> {
    return this.request(`/internal/marketplace/agents/${agentId}/rate`, {
      method: 'POST',
      body: JSON.stringify({ rating }),
    });
  }

  async getMyMarketplaceRating(agentId: number): Promise<UserRatingResponse> {
    return this.request(`/internal/marketplace/agents/${agentId}/my-rating`);
  }

  async createMarketplaceConversation(
    agentId: number,
    title?: string,
  ): Promise<any> {
    const titleParam = title
      ? `?title=${encodeURIComponent(title)}`
      : '';
    return this.request(
      `/internal/marketplace/agents/${agentId}/conversations${titleParam}`,
      { method: 'POST' },
    );
  }

  async getMarketplaceConversations(
    limit = 50,
    offset = 0,
  ): Promise<{ conversations: MarketplaceConversation[]; total: number }> {
    return this.request(
      `/internal/marketplace/conversations?limit=${limit}&offset=${offset}`,
    );
  }

  async getMarketplaceConversationHistory(
    conversationId: number,
  ): Promise<any> {
    return this.request(
      `/internal/marketplace/conversations/${conversationId}`,
    );
  }

  async sendMarketplaceMessage(
    conversationId: number,
    message: string,
    fileReferences?: string[],
  ): Promise<any> {
    const formData = new FormData();
    formData.append('message', message);
    if (fileReferences && fileReferences.length > 0) {
      formData.append('file_references', JSON.stringify(fileReferences));
    }
    return this.request(
      `/internal/marketplace/conversations/${conversationId}/chat`,
      {
        method: 'POST',
        body: formData,
      },
    );
  }

  // Mirrors chatWithAgentStream so marketplace UI can reuse useStreamingChat.
  async chatMarketplaceStream(
    conversationId: number,
    message: string,
    options: {
      files?: File[];
      fileReferences?: string[];
      onEvent: (event: StreamEvent) => void;
      signal?: AbortSignal;
    },
  ): Promise<void> {
    const formData = new FormData();
    formData.append('message', message);

    if (options.fileReferences && options.fileReferences.length > 0) {
      formData.append('file_references', JSON.stringify(options.fileReferences));
    }
    if (options.files && options.files.length > 0) {
      options.files.forEach((file) => formData.append('files', file));
    }

    const url = `${this.baseURL}/internal/marketplace/conversations/${conversationId}/chat/stream`;
    const headers = this.buildAuthHeaders('POST', true);

    const response = await fetch(url, {
      method: 'POST',
      credentials: 'include',
      headers,
      body: formData,
      signal: options.signal,
    });

    if (!response.ok) {
      await this.handleResponseError(response);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('ReadableStream not supported');
    }

    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';
        this.parseSSELines(lines, options.onEvent);
      }
    } finally {
      reader.releaseLock();
    }
  }

  async uploadMarketplaceFile(conversationId: number, file: File): Promise<any> {
    const formData = new FormData();
    formData.append('file', file);
    return this.request(
      `/internal/marketplace/conversations/${conversationId}/upload-file`,
      { method: 'POST', body: formData },
    );
  }

  async listMarketplaceFiles(conversationId: number): Promise<any> {
    return this.request(`/internal/marketplace/conversations/${conversationId}/files`);
  }

  async removeMarketplaceFile(conversationId: number, fileId: string): Promise<any> {
    return this.request(
      `/internal/marketplace/conversations/${conversationId}/files/${fileId}`,
      { method: 'DELETE' },
    );
  }

  async getMarketplaceFileDownloadUrl(conversationId: number, fileId: string): Promise<string> {
    const response = await this.request(
      `/internal/marketplace/conversations/${conversationId}/files/${fileId}/download`,
      { method: 'GET' },
    );
    return response.download_url as string;
  }

  async getMarketplaceQuotaUsage(): Promise<MarketplaceQuotaUsage> {
    return this.request('/internal/marketplace/quota-usage');
  }

  async getAgentMarketplaceProfile(
    appId: number,
    agentId: number,
  ): Promise<MarketplaceProfile> {
    return this.request(
      `/internal/apps/${appId}/agents/${agentId}/marketplace-profile`,
    );
  }

  async updateAgentMarketplaceProfile(
    appId: number,
    agentId: number,
    data: MarketplaceProfileUpdate,
  ): Promise<MarketplaceProfile> {
    return this.request(
      `/internal/apps/${appId}/agents/${agentId}/marketplace-profile`,
      {
        method: 'PUT',
        body: JSON.stringify(data),
      },
    );
  }

  async updateAgentMarketplaceVisibility(
    appId: number,
    agentId: number,
    visibility: MarketplaceVisibility,
  ): Promise<{ marketplace_visibility: string }> {
    return this.request(
      `/internal/apps/${appId}/agents/${agentId}/marketplace-visibility`,
      {
        method: 'PUT',
        body: JSON.stringify({ marketplace_visibility: visibility }),
      },
    );
  }

  async exportFullApp(appId: number): Promise<Blob> {
    const response = await fetch(`${this.baseURL}/internal/apps/${appId}/export`, {
      method: 'POST',
      credentials: 'include',
      headers: this.buildAuthHeaders('POST', false),
    });

    if (!response.ok) {
      await this.handleResponseError(response);
    }

    return response.blob();
  }

  async importFullApp(
    file: File,
    conflictMode: ConflictMode,
    newName?: string
  ): Promise<any> {
    const formData = new FormData();
    formData.append('file', file);
    
    const params = new URLSearchParams();
    params.append('conflict_mode', conflictMode);

    if (newName) {
      params.append('new_name', newName);
    }

    const url = `${this.baseURL}/internal/apps/import?${params}`;
    const response = await fetch(url, {
      method: 'POST',
      credentials: 'include',
      headers: this.buildAuthHeaders('POST', true),
      body: formData,
    });

    if (!response.ok) {
      await this.handleResponseError(response);
    }

    return response.json();
  }

  async previewAgentImport(appId: number, file: File) {
    const formData = new FormData();
    formData.append('file', file);

    const url = `${this.baseURL}/internal/apps/${appId}/agents/preview-import`;
    const response = await fetch(url, {
      method: 'POST',
      credentials: 'include',
      headers: this.buildAuthHeaders('POST', true),
      body: formData,
    });

    if (!response.ok) {
      await this.handleResponseError(response);
    }

    return response.json();
  }

  async previewAppImport(file: File) {
    const formData = new FormData();
    formData.append('file', file);

    const url = `${this.baseURL}/internal/apps/preview-import`;
    const response = await fetch(url, {
      method: 'POST',
      credentials: 'include',
      headers: this.buildAuthHeaders('POST', true),
      body: formData,
    });

    if (!response.ok) {
      await this.handleResponseError(response);
    }

    return response.json();
  }

  async importAgentWithOptions(
    appId: number,
    file: File,
    options: {
      conflictMode: string;
      newName?: string;
      selectedAIServiceId?: number;
      importBundledSilo?: boolean;
      importBundledOutputParser?: boolean;
      importBundledMCPConfigs?: boolean;
      importBundledAgentTools?: boolean;
    }
  ) {
    const formData = new FormData();
    formData.append('file', file);

    const params = new URLSearchParams();
    params.append('conflict_mode', options.conflictMode);
    if (options.newName) {
      params.append(
        'new_name',
        options.newName
      );
    }
    if (options.selectedAIServiceId !== undefined) {
      params.append(
        'selected_ai_service_id',
        String(options.selectedAIServiceId)
      );
    }
    if (options.importBundledSilo === false) {
      params.append('import_bundled_silo', 'false');
    }
    if (options.importBundledOutputParser === false) {
      params.append('import_bundled_output_parser', 'false');
    }
    if (options.importBundledMCPConfigs === false) {
      params.append('import_bundled_mcp_configs', 'false');
    }
    if (options.importBundledAgentTools === false) {
      params.append('import_bundled_agent_tools', 'false');
    }

    const url = `${this.baseURL}/internal/apps/${appId}/agents/import?${params}`;
    const response = await fetch(url, {
      method: 'POST',
      credentials: 'include',
      headers: this.buildAuthHeaders('POST', true),
      body: formData,
    });

    if (!response.ok) {
      await this.handleResponseError(response);
    }

    return response.json();
  }

  async importAppWithOptions(
    file: File,
    options: {
      conflictMode: string;
      newAppName?: string;
      componentSelection?: Record<string, string[]>;
      apiKeys?: Record<string, string>;
    }
  ) {
    const formData = new FormData();
    formData.append('file', file);

    const params = new URLSearchParams();
    params.append('conflict_mode', options.conflictMode);
    if (options.newAppName) {
      params.append('new_name', options.newAppName);
    }

    if (options.componentSelection) {
      formData.append(
        'component_selection_json',
        JSON.stringify(options.componentSelection),
      );
    }
    if (options.apiKeys && Object.keys(options.apiKeys).length > 0) {
      formData.append(
        'api_keys_json',
        JSON.stringify(options.apiKeys),
      );
    }

    const url = `${this.baseURL}/internal/apps/import?${params}`;
    const response = await fetch(url, {
      method: 'POST',
      credentials: 'include',
      headers: this.buildAuthHeaders('POST', true),
      body: formData,
    });

    if (!response.ok) {
      await this.handleResponseError(response);
    }

    return response.json();
  }

  async fetchSystemSettings() {
    return this.request('/internal/admin/settings');
  }

  async updateSystemSetting(key: string, value: string) {
    return this.request(`/internal/admin/settings/${encodeURIComponent(key)}`, {
      method: 'PUT',
      body: JSON.stringify({ value }),
    });
  }

  async resetSystemSetting(key: string) {
    return this.request(`/internal/admin/settings/${encodeURIComponent(key)}`, {
      method: 'DELETE',
    });
  }

  async getSubscription() {
    return this.request('/internal/subscription');
  }

  async createCheckoutSession(tier: string) {
    return this.request('/internal/subscription/checkout', {
      method: 'POST',
      body: JSON.stringify({ tier }),
    });
  }

  async createPortalSession() {
    return this.request('/internal/subscription/portal', {
      method: 'POST',
    });
  }

  async getUsage() {
    return this.request('/internal/usage');
  }

  async getAdminSaasUsers() {
    return this.request('/internal/admin/saas/users');
  }

  async overrideUserTier(userId: number, tier: string) {
    return this.request(`/internal/admin/saas/users/${userId}/tier`, {
      method: 'PUT',
      body: JSON.stringify({ tier }),
    });
  }

  async getTierConfig() {
    return this.request('/internal/admin/saas/tier-config');
  }

  async updateTierConfig(data: { tier: string; resource_type: string; limit_value: number }) {
    return this.request('/internal/admin/saas/tier-config', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async getSystemAIServices() {
    return this.request('/internal/admin/system-ai-services');
  }

  async getSystemAIService(serviceId: number) {
    return this.request(`/internal/admin/system-ai-services/${serviceId}`);
  }

  async createSystemAIService(data: {
    name: string;
    provider: string;
    model_name: string;
    api_key: string;
    base_url?: string;
  }) {
    return this.request('/internal/admin/system-ai-services', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateSystemAIService(serviceId: number, data: {
    name: string;
    provider: string;
    model_name: string;
    api_key: string;
    base_url?: string;
  }) {
    return this.request(`/internal/admin/system-ai-services/${serviceId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteSystemAIService(serviceId: number) {
    return this.request(`/internal/admin/system-ai-services/${serviceId}`, {
      method: 'DELETE',
    });
  }

  async getSystemEmbeddingServices() {
    return this.request('/internal/admin/system-embedding-services');
  }

  async createSystemEmbeddingService(data: {
    name: string;
    provider: string;
    model_name: string;
    api_key: string;
    base_url?: string;
  }) {
    return this.request('/internal/admin/system-embedding-services', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateSystemEmbeddingService(serviceId: number, data: {
    name: string;
    provider: string;
    model_name: string;
    api_key: string;
    base_url?: string;
  }) {
    return this.request(`/internal/admin/system-embedding-services/${serviceId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async getSystemEmbeddingServiceImpact(serviceId: number) {
    return this.request(`/internal/admin/system-embedding-services/${serviceId}/impact`);
  }

  async deleteSystemEmbeddingService(serviceId: number) {
    return this.request(`/internal/admin/system-embedding-services/${serviceId}`, {
      method: 'DELETE',
    });
  }

  async listSystemAIServiceProviderModels(
    body: import('../types/services').ListProviderModelsRequest,
  ): Promise<import('../types/services').ListProviderModelsResponse> {
    return this.request('/internal/admin/system-ai-services/list-models', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  async listSystemEmbeddingServiceProviderModels(
    body: import('../types/services').ListProviderModelsRequest,
  ): Promise<import('../types/services').ListProviderModelsResponse> {
    return this.request('/internal/admin/system-embedding-services/list-models', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  async testSystemAIServiceConnectionWithConfig(data: any, serviceId?: number) {
    const qs = serviceId != null ? `?service_id=${serviceId}` : '';
    return this.request(`/internal/admin/system-ai-services/test-connection${qs}`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async testSystemEmbeddingServiceConnectionWithConfig(data: any, serviceId?: number) {
    const qs = serviceId != null ? `?service_id=${serviceId}` : '';
    return this.request(`/internal/admin/system-embedding-services/test-connection${qs}`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async getPlatformChatbotConfig(): Promise<{
    enabled: boolean;
    agent_name: string | null;
    agent_description: string | null;
  }> {
    // Mounted on public pages (/login, /set-password); 401 must not trigger
    // global redirect — the provider's catch block disables the widget instead.
    return this.request(
      '/internal/platform-chatbot/config',
      {},
      false,
      { suppressAuthRedirect: true },
    );
  }

  async sendPlatformChatbotMessage(
    message: string,
    sessionId: string
  ): Promise<{ response: string | Record<string, unknown>; agent_id: number; conversation_id: number | null; metadata: Record<string, unknown> }> {
    return this.request('/internal/platform-chatbot/chat', {
      method: 'POST',
      body: JSON.stringify({ message, session_id: sessionId }),
    });
  }

  async streamPlatformChatbotMessage(
    message: string,
    sessionId: string,
    options: { onEvent: (event: StreamEvent) => void; signal?: AbortSignal }
  ): Promise<void> {
    const url = `${this.baseURL}/internal/platform-chatbot/chat/stream`;
    const headers = this.buildAuthHeaders('POST', false);

    const response = await fetch(url, {
      method: 'POST',
      credentials: 'include',
      headers,
      body: JSON.stringify({ message, session_id: sessionId }),
      signal: options.signal,
    });

    if (!response.ok) {
      await this.handleResponseError(response);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('ReadableStream not supported');
    }

    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';

        this.parseSSELines(lines, options.onEvent);
      }
    } finally {
      reader.releaseLock();
    }
  }
}

export const apiService = new ApiService();