// API Service - Think of this like your backend services!
class ApiService {
  private baseURL = 'http://localhost:8000';
  private token = 'temp-token-456'; // TODO: Replace with real auth (trying user_id 1)

  private async request(endpoint: string, options: RequestInit = {}) {
    const url = `${this.baseURL}${endpoint}`;
    const config: RequestInit = {
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.token}`,
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

  // ==================== AGENTS API ====================
  async getAgents(appId: number) {
    return this.request(`/internal/apps/${appId}/agents/`);
  }

  async getAgent(appId: number, agentId: number) {
    return this.request(`/internal/apps/${appId}/agents/${agentId}`);
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

  async respondToInvitation(collaborationId: number, action: 'accept' | 'decline') {
    return this.request(`/internal/apps/0/collaboration/invitations/${collaborationId}/respond`, {
      method: 'POST',
      body: JSON.stringify({
        action
      }),
    });
  }

  async getMyInvitations() {
    return this.request(`/internal/apps/0/collaboration/my-invitations`);
  }

  // TODO: Add more endpoints as needed
}

// Export singleton instance - like how you'd use services in backend
export const apiService = new ApiService(); 