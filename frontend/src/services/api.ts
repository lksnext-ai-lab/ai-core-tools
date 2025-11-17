// API Service - Think of this like your backend services!
import { configService } from '../core/ConfigService';

class ApiService {
  private get baseURL(): string {
    return configService.getApiBaseUrl();
  }

  private getAuthToken(): string | null {
    // Get token from localStorage (same as auth service)
    const token = localStorage.getItem('auth_token');
    return token;
  }

  async request(endpoint: string, options: RequestInit = {}) {
    const url = `${this.baseURL}${endpoint}`;
    
    const defaultHeaders: Record<string, string> = {};

    // Only set Content-Type if not FormData (browser will set it automatically for FormData)
    if (!(options.body instanceof FormData)) {
      defaultHeaders['Content-Type'] = 'application/json';
    }

    // Use token from auth service instead of hardcoded
    const token = this.getAuthToken();
    if (token) {
      defaultHeaders['Authorization'] = `Bearer ${token}`;
    }

    const config: RequestInit = {
      headers: {
        ...defaultHeaders,
        ...options.headers,
      },
      ...options,
    };

    const response = await fetch(url, config);
    
    if (!response.ok) {
      throw new Error(`API Error: ${response.status} ${response.statusText}`);
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
    return this.request('/auth/pending-invitations');
  }

  async respondToInvitation(invitationId: number, action: 'accept' | 'decline') {
    return this.request(`/auth/invitations/${invitationId}/respond`, {
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
  async uploadFileForChat(appId: number, agentId: number, file: File) {
    const formData = new FormData();
    formData.append('file', file);

    return this.request(`/internal/apps/${appId}/agents/${agentId}/upload-file`, {
      method: 'POST',
      body: formData,
    });
  }

  async listAttachedFiles(appId: number, agentId: number) {
    return this.request(`/internal/apps/${appId}/agents/${agentId}/files`);
  }

  async removeAttachedFile(appId: number, agentId: number, fileId: string) {
    return this.request(`/internal/apps/${appId}/agents/${agentId}/files/${fileId}`, {
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
    return this.request(`/internal/conversations?agent_id=${agentId}${title ? `&title=${encodeURIComponent(title)}` : ''}`, {
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

  // ==================== UTILITY METHODS ====================
}

// Export singleton instance - like how you'd use services in backend
export const apiService = new ApiService();