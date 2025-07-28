// API Service - Think of this like your backend services!
class ApiService {
  private baseURL = 'http://localhost:8000';

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

  async createApp(data: { name: string }) {
    return this.request('/internal/apps/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateApp(appId: number, data: { name: string }) {
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
    return this.request(`/internal/apps/${appId}/collaboration/`);
  }

  async inviteCollaborator(appId: number, email: string, role: string = 'editor') {
    return this.request(`/internal/apps/${appId}/collaboration/invite`, {
      method: 'POST',
      body: JSON.stringify({
        email,
        role
      }),
    });
  }

  async updateCollaboratorRole(appId: number, userId: number, role: string) {
    return this.request(`/internal/apps/${appId}/collaboration/${userId}/role`, {
      method: 'PUT',
      body: JSON.stringify({
        role
      }),
    });
  }

  async removeCollaborator(appId: number, userId: number) {
    return this.request(`/internal/apps/${appId}/collaboration/${userId}`, {
      method: 'DELETE',
    });
  }

  async getMyInvitations() {
    return this.request(`/internal/apps/0/collaboration/my-invitations`);
  }

  // ==================== SILOS API ====================
  async getSilos(appId: number) {
    return this.request(`/internal/apps/${appId}/silos/`);
  }

  async getSilo(appId: number, siloId: number) {
    return this.request(`/internal/apps/${appId}/silos/${siloId}`);
  }

  async createSilo(appId: number, data: any) {
    return this.request(`/internal/apps/${appId}/silos/0`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateSilo(appId: number, siloId: number, data: any) {
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

  async createRepository(appId: number, data: { name: string; embedding_service_id?: number }) {
    return this.request(`/internal/apps/${appId}/repositories/0`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateRepository(appId: number, repositoryId: number, data: { name: string; embedding_service_id?: number }) {
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

  async uploadResources(appId: number, repositoryId: number, files: File[]) {
    console.log('API: uploadResources called with:', { appId, repositoryId, filesCount: files.length });
    
    const formData = new FormData();
    files.forEach(file => {
      formData.append('files', file);
      console.log('API: Added file to FormData:', file.name);
    });

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

  // ==================== PLAYGROUND API ====================
  async chatWithAgent(appId: number, agentId: number, message: string, files?: File[], searchParams?: any) {
    const formData = new FormData();
    formData.append('message', message);
    
    if (searchParams) {
      formData.append('search_params', JSON.stringify(searchParams));
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

  async resetAgentConversation(appId: number, agentId: number) {
    return this.request(`/internal/apps/${appId}/agents/${agentId}/reset`, {
      method: 'POST',
    });
  }

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

    return this.request(`/internal/apps/${appId}/agents/${agentId}/process`, {
      method: 'POST',
      body: formData,
    });
  }

  // TODO: Add more endpoints as needed
}

// Export singleton instance - like how you'd use services in backend
export const apiService = new ApiService(); 