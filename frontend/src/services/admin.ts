import { apiService } from './api';

export interface User {
  user_id: number;
  email: string;
  name?: string;
  created_at: string;
  owned_apps_count: number;
  api_keys_count: number;
  is_active: boolean;
  is_omniadmin?: boolean;
}

export interface UserListResponse {
  users: User[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface SystemStats {
  total_users: number;
  active_users: number;
  inactive_users: number;
  total_apps: number;
  total_agents: number;
  total_api_keys: number;
  active_api_keys: number;
  inactive_api_keys: number;
  recent_users: Array<{
    user_id: number;
    email: string;
    name?: string;
    created_at: string;
  }>;
  users_with_apps: number;
}

class AdminService {
  private baseUrl = '/internal/admin';

  async getUsers(page: number = 1, perPage: number = 10, search?: string): Promise<UserListResponse> {
    const params = new URLSearchParams({
      page: page.toString(),
      per_page: perPage.toString(),
    });
    
    if (search) {
      params.append('search', search);
    }

    return await apiService.request(`${this.baseUrl}/users?${params}`);
  }

  async getUser(userId: number): Promise<User> {
    return await apiService.request(`${this.baseUrl}/users/${userId}`);
  }

  async deleteUser(userId: number): Promise<{ message: string }> {
    return await apiService.request(`${this.baseUrl}/users/${userId}`, {
      method: 'DELETE',
    });
  }

  async getSystemStats(): Promise<SystemStats> {
    return await apiService.request(`${this.baseUrl}/stats`);
  }

  async activateUser(userId: number): Promise<{ message: string; user_id: number; is_active: boolean }> {
    return await apiService.request(`${this.baseUrl}/users/${userId}/activate`, {
      method: 'POST',
    });
  }

  async deactivateUser(userId: number): Promise<{ message: string; user_id: number; is_active: boolean }> {
    return await apiService.request(`${this.baseUrl}/users/${userId}/deactivate`, {
      method: 'POST',
    });
  }
}

export const adminService = new AdminService(); 