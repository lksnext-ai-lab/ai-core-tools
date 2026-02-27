// API Service - Think of this like your backend services!
import { configService } from '../core/ConfigService';
import type {
  MarketplaceCatalogParams,
  MarketplaceCatalogResponse,
  MarketplaceAgentDetail,
  MarketplaceConversation,
  MarketplaceProfile,
  MarketplaceProfileUpdate,
  MarketplaceVisibility,
} from '../types/marketplace';

class ApiService {
  private get baseURL(): string {
    return configService.getApiBaseUrl();
  }

  private getAuthToken(): string | null {
    // Get token from localStorage (same as auth service)
    const token = localStorage.getItem('auth_token');
    return token;
  }

  private prepareHeaders(options: RequestInit): Record<string, string> {
    const headers: Record<string, string> = {};

    // Only set Content-Type if not FormData (browser will set it automatically for FormData)
    if (!(options.body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
    }

    // Use token from auth service instead of hardcoded
    const token = this.getAuthToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    return headers;
  }

  private extractErrorMessage(errorData: any): string | null {
    if (!errorData) return null;

    if (errorData.error) {
      return errorData.error;
    }
    if (errorData.detail) {
      return typeof errorData.detail === 'string'
        ? errorData.detail
        : JSON.stringify(errorData.detail);
    }
    if (errorData.message) {
      return errorData.message;
    }
    return null;
  }

  private async handleResponseError(response: Response): Promise<never> {
    // Handle 401 Unauthorized - token expired or invalid
    if (response.status === 401) {
      // Clear invalid token
      localStorage.removeItem('auth_token');
      localStorage.removeItem('auth_expires');

      // Don't redirect - let the app handle auth state via ProtectedRoute
      throw new Error('Authentication required');
    }

    // Try to parse error message from response
    let errorMessage = `API Error: ${response.status} ${response.statusText}`;

    try {
      const errorData = await response.json();
      const extracted = this.extractErrorMessage(errorData);
      if (extracted) {
        errorMessage = extracted;
      }
    } catch (error) {
      // Log error for debugging but continue to check status code
      console.debug('Failed to parse error response JSON:', error);

      // Failed to parse JSON, check for specific status codes
      if (response.status === 403) {
        errorMessage = "You do not have permission to perform this action.";
      }
    }

    throw new Error(errorMessage);
  }

  async request(endpoint: string, options: RequestInit = {}) {
    const url = `${this.baseURL}${endpoint}`;
    const defaultHeaders = this.prepareHeaders(options);

    const config: RequestInit = {
      headers: {
        ...defaultHeaders,
        ...options.headers,
      },
      ...options,
    };

    const response = await fetch(url, config);

    if (!response.ok) {
      await this.handleResponseError(response);
    }

    return response.json();
  }

  // ==================== APPS API ====================
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

  async updateApp(appId: number, data: { name: string; langsmith_api_key?: string; agent_rate_limit?: number; max_file_size_mb?: number; agent_cors_origins?: string }) {
    return this.request(`/internal/apps/${appId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
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

  // ==================== USAGE STATS API ====================
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

  // ==================== AGENTS API ====================
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
    return this.request(`/internal/apps/${appId}/agents/${agentId}`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
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

  async resetAgentConversation(appId: number, agentId: number) {
    return this.request(`/internal/apps/${appId}/agents/${agentId}/reset`, {
      method: 'POST',
    });
  }

  async getConversationHistory(appId: number, agentId: number) {
    return this.request(`/internal/apps/${appId}/agents/${agentId}/conversation-history`, {
      method: 'GET',
    });
  }

  // ==================== AI SERVICES API ====================
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

  async testAIServiceConnectionWithConfig(appId: number, data: any) {
    return this.request(`/internal/apps/${appId}/ai-services/test-connection`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // ==================== EMBEDDING SERVICES ====================
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

  // ==================== MCP CONFIGS ====================
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

  // ==================== SKILLS ====================
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

  // ==================== MCP SERVERS (Expose Agents as MCP Tools) ====================
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

  // ==================== API KEYS ====================
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

  // ==================== OUTPUT PARSERS (DATA STRUCTURES) ====================
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

  // ==================== COLLABORATION ====================
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

  // ==================== MEDIA API ====================
  async uploadMedia(appId: number, repositoryId: number, files: File[], folderId?: number, config?: {
    forced_language?: string;
    chunk_min_duration?: number;
    chunk_max_duration?: number;
    chunk_overlap?: number;
  }, transcriptionServiceId?: number) {
    const formData = new FormData();
    const headers: Record<string, string> = {};
    
    files.forEach(file => formData.append('files', file));
    
    if (folderId !== undefined && folderId !== null) {
      formData.append('folder_id', folderId.toString());
      console.log('API: Added folder_id to FormData:', folderId);
    } else {
      console.log('API: No folder_id provided or folderId is null/undefined');
    }
    
    if (transcriptionServiceId) formData.append('transcription_service_id', transcriptionServiceId.toString());
    if (config?.forced_language) formData.append('forced_language', config.forced_language);
    if (config?.chunk_min_duration) formData.append('chunk_min_duration', config.chunk_min_duration.toString());
    if (config?.chunk_max_duration) formData.append('chunk_max_duration', config.chunk_max_duration.toString());
    if (config?.chunk_overlap) formData.append('chunk_overlap', config.chunk_overlap.toString());

    const token = this.getAuthToken();
    console.log('API: Auth token for upload:', token ? 'Token exists' : 'No token found');
        
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
      console.log('API: Authorization header set for upload');
    } else {
      console.log('API: WARNING - No token found for upload request');
    }

    console.log('API: Making upload request to:', `/internal/apps/${appId}/repositories/${repositoryId}/resources`);

    return this.request(`/internal/apps/${appId}/repositories/${repositoryId}/media`, {
      method: 'POST',
      headers: headers,
      body: formData,
    });
  }
  
  async addYouTube(appId: number, repositoryId: number, url: string, folderId?: number, config?: {
    forced_language?: string;
    chunk_min_duration?: number;
    chunk_max_duration?: number;
    chunk_overlap?: number;
  }, transcriptionServiceId?: number) {
    const formData = new FormData();
    const headers: Record<string, string> = {};
    const token = this.getAuthToken();
    console.log('API: Auth token for upload:', token ? 'Token exists' : 'No token found');

    formData.append('url', url);
    if (folderId !== undefined && folderId !== null) {
      formData.append('folder_id', folderId.toString());
      console.log('API: Added folder_id to FormData:', folderId);
    } else {
      console.log('API: No folder_id provided or folderId is null/undefined');
    }
    if (transcriptionServiceId) formData.append('transcription_service_id', transcriptionServiceId.toString());
    if (config?.forced_language) formData.append('forced_language', config.forced_language);
    if (config?.chunk_min_duration) formData.append('chunk_min_duration', config.chunk_min_duration.toString());
    if (config?.chunk_max_duration) formData.append('chunk_max_duration', config.chunk_max_duration.toString());
    if (config?.chunk_overlap) formData.append('chunk_overlap', config.chunk_overlap.toString());
        
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
      console.log('API: Authorization header set for upload');
    } else {
      console.log('API: WARNING - No token found for upload request');
    }

    console.log('API: Making upload request to:', `/internal/apps/${appId}/repositories/${repositoryId}/resources`);

    return this.request(`/internal/apps/${appId}/repositories/${repositoryId}/media/youtube`, {
      method: 'POST',
      headers: headers,
      body: formData,
    });
  }

  async getMediaStatus(appId: number, repositoryId: number, mediaId: number) {
    return this.request(`/internal/apps/${appId}/repositories/${repositoryId}/media/${mediaId}`);
  }

  async listMedia(appId: number, repositoryId: number, folderId?: number) {
    const params = folderId !== undefined ? `?folder_id=${folderId}` : '';
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
    return this.request(`/internal/apps/${appId}/silos/0`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateSilo(appId: number, siloId: number, data: { name: string; description?: string; embedding_service_id?: number; vector_db_type?: string; fixed_metadata?: boolean; status?: string }) {
    return this.request(`/internal/apps/${appId}/silos/${siloId}`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async deleteSilo(appId: number, siloId: number) {
    return this.request(`/internal/apps/${appId}/silos/${siloId}`, {
      method: 'DELETE',
    });
  }

  async searchSiloDocuments(appId: number, siloId: number, query: string, limit: number = 10, filterMetadata?: Record<string, any>) {
    return this.request(`/internal/apps/${appId}/silos/${siloId}/search`, {
      method: 'POST',
      body: JSON.stringify({
        query,
        limit,
        filter_metadata: filterMetadata
      }),
    });
  }

  async deleteSiloDocuments(appId: number, siloId: number, documentIds: string[]) {
    return this.request(`/internal/apps/${appId}/silos/${siloId}/documents`, {
      method: 'DELETE',
      body: JSON.stringify({ document_ids: documentIds }),
    });
  }

  // ==================== REPOSITORIES API ====================
  async getRepositories(appId: number) {
    console.log('API: Getting repositories for appId:', appId);
    const result = await this.request(`/internal/apps/${appId}/repositories/`);
    console.log('API: Repositories result:', result);
    return result;
  }

  async getRepository(appId: number, repositoryId: number) {
    return this.request(`/internal/apps/${appId}/repositories/${repositoryId}`);
  }

  async createRepository(appId: number, data: { name: string; embedding_service_id?: number; vector_db_type?: string }) {
    return this.request(`/internal/apps/${appId}/repositories/0`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateRepository(appId: number, repositoryId: number, data: { name: string; embedding_service_id?: number; vector_db_type?: string }) {
    return this.request(`/internal/apps/${appId}/repositories/${repositoryId}`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async deleteRepository(appId: number, repositoryId: number) {
    return this.request(`/internal/apps/${appId}/repositories/${repositoryId}`, {
      method: 'DELETE',
    });
  }

  async uploadResources(appId: number, repositoryId: number, files: File[], folderId?: number) {
    console.log('API: uploadResources called with:', { appId, repositoryId, filesCount: files.length, folderId });
    
    const formData = new FormData();
    files.forEach(file => {
      formData.append('files', file);
      console.log('API: Added file to FormData:', file.name);
    });
    
    // Add folder_id if provided
    if (folderId !== undefined && folderId !== null) {
      formData.append('folder_id', folderId.toString());
      console.log('API: Added folder_id to FormData:', folderId);
    } else {
      console.log('API: No folder_id provided or folderId is null/undefined');
    }

    // Get the auth token manually for this request
    const token = this.getAuthToken();
    console.log('API: Auth token for upload:', token ? 'Token exists' : 'No token found');
    
    const headers: Record<string, string> = {};
    
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
      console.log('API: Authorization header set for upload');
    } else {
      console.log('API: WARNING - No token found for upload request');
    }

    console.log('API: Making upload request to:', `/internal/apps/${appId}/repositories/${repositoryId}/resources`);
    
    try {
      const result = await this.request(`/internal/apps/${appId}/repositories/${repositoryId}/resources`, {
        method: 'POST',
        headers: headers, // Only set Authorization, let browser handle Content-Type for FormData
        body: formData,
      });
      console.log('API: Upload successful:', result);
      console.log('API: Failed files in result:', result.failed_files);
      console.log('API: Created resources in result:', result.created_resources);
      return result;
    } catch (error) {
      console.error('API: Upload failed:', error);
      throw error;
    }
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
    const token = this.getAuthToken();
    const headers: Record<string, string> = {};
    
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(`${this.baseURL}/internal/apps/${appId}/repositories/${repositoryId}/resources/${resourceId}/download`, {
      method: 'GET',
      headers: headers,
    });

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

  // ==================== PLAYGROUND API ====================
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

  // ==================== FILE MANAGEMENT API ====================
  async uploadFileForChat(appId: number, agentId: number, file: File, conversationId?: number | null) {
    const formData = new FormData();
    formData.append('file', file);
    
    // Associate file with specific conversation if provided
    if (conversationId) {
      formData.append('conversation_id', conversationId.toString());
    }

    return this.request(`/internal/apps/${appId}/agents/${agentId}/upload-file`, {
      method: 'POST',
      body: formData,
    });
  }

  async listAttachedFiles(appId: number, agentId: number, conversationId?: number | null) {
    // Filter files by conversation if provided
    const url = conversationId 
      ? `/internal/apps/${appId}/agents/${agentId}/files?conversation_id=${conversationId}`
      : `/internal/apps/${appId}/agents/${agentId}/files`;
    return this.request(url);
  }

  async removeAttachedFile(appId: number, agentId: number, fileId: string, conversationId?: number | null) {
    // Include conversation_id for proper file lookup
    const url = conversationId
      ? `/internal/apps/${appId}/agents/${agentId}/files/${fileId}?conversation_id=${conversationId}`
      : `/internal/apps/${appId}/agents/${agentId}/files/${fileId}`;
    return this.request(url, {
      method: 'DELETE',
    });
  }

  async processOCR(appId: number, agentId: number, file: File) {
    const formData = new FormData();
    formData.append('pdf_file', file);

    return this.request(`/internal/apps/${appId}/ocr/${agentId}/process`, {
      method: 'POST',
      body: formData,
    });
  }

  // ==================== DOMAINS API ====================
  async getDomains(appId: number) {
    return this.request(`/internal/apps/${appId}/domains/`);
  }

  async getDomain(appId: number, domainId: number) {
    return this.request(`/internal/apps/${appId}/domains/${domainId}`);
  }

  async createDomain(
    appId: number,
    domainId: number,
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
    return this.request(`/internal/apps/${appId}/domains/${domainId}`, {
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
      embedding_service_id?: number;
      vector_db_type?: string;
    }
  ) {
    return this.request(`/internal/apps/${appId}/domains/${domainId}`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async deleteDomain(appId: number, domainId: number) {
    return this.request(`/internal/apps/${appId}/domains/${domainId}`, {
      method: 'DELETE',
    });
  }

  async getDomainUrls(appId: number, domainId: number, page = 1, perPage = 20) {
    return this.request(`/internal/apps/${appId}/domains/${domainId}/urls?page=${page}&per_page=${perPage}`);
  }

  async addUrlToDomain(appId: number, domainId: number, data: { url: string }) {
    return this.request(`/internal/apps/${appId}/domains/${domainId}/urls`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async deleteUrlFromDomain(appId: number, domainId: number, urlId: number) {
    return this.request(`/internal/apps/${appId}/domains/${domainId}/urls/${urlId}`, {
      method: 'DELETE',
    });
  }

  async reindexUrl(appId: number, domainId: number, urlId: number) {
    return this.request(`/internal/apps/${appId}/domains/${domainId}/urls/${urlId}/reindex`, {
      method: 'POST',
    });
  }

  async unindexUrl(appId: number, domainId: number, urlId: number) {
    return this.request(`/internal/apps/${appId}/domains/${domainId}/urls/${urlId}/unindex`, {
      method: 'POST',
    });
  }

  async rejectUrl(appId: number, domainId: number, urlId: number) {
    return this.request(`/internal/apps/${appId}/domains/${domainId}/urls/${urlId}/reject`, {
      method: 'POST',
    });
  }

  async reindexDomain(appId: number, domainId: number) {
    return this.request(`/internal/apps/${appId}/domains/${domainId}/reindex`, {
      method: 'POST',
    });
  }

  async getUrlContent(appId: number, domainId: number, urlId: number) {
    return this.request(`/internal/apps/${appId}/domains/${domainId}/urls/${urlId}/content`);
  }

  // ==================== VERSION API ====================

  async getVersion(): Promise<{ name: string; version: string }> {
    const response = await this.request('/internal/version/');
    return response;
  }

  // ==================== FOLDERS API ====================
  
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

  // ==================== CONVERSATION METHODS ====================
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

  // ==================== MARKETPLACE ====================

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
    files?: File[],
  ): Promise<any> {
    const formData = new FormData();
    formData.append('message', message);
    if (files) {
      files.forEach((file) => formData.append('files', file));
    }
    return this.request(
      `/internal/marketplace/conversations/${conversationId}/chat`,
      {
        method: 'POST',
        body: formData,
        // Do NOT set Content-Type — browser sets it with boundary for FormData
      },
    );
  }

  // Agent marketplace management (EDITOR+)

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

  // ==================== UTILITY METHODS ====================
}

// Export singleton instance - like how you'd use services in backend
export const apiService = new ApiService();