// API Service - Think of this like your backend services!
class ApiService {
  private baseURL = 'http://localhost:8002';
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

  // TODO: Add more endpoints as needed
}

// Export singleton instance - like how you'd use services in backend
export const apiService = new ApiService(); 