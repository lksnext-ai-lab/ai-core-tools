import { apiService, ApiError } from './api';

export interface LocalUserCreated {
  readonly user_id: number;
  readonly email: string;
  readonly name: string;
  readonly set_password_token: string;
  readonly expires_at: string;
}

export interface ResetLinkResult {
  readonly set_password_token: string;
  readonly expires_at: string;
}

export interface User {
  readonly user_id: number;
  readonly email: string;
  readonly name?: string;
  readonly created_at: string;
  readonly owned_apps_count: number;
  readonly api_keys_count: number;
  readonly is_active: boolean;
  readonly is_omniadmin?: boolean;
  readonly platform_role?: 'viewer' | 'editor' | 'admin';
}

export interface UserListResponse {
  readonly users: User[];
  readonly total: number;
  readonly page: number;
  readonly per_page: number;
  readonly total_pages: number;
}

/** The three deletion modes accepted by DELETE /internal/admin/users/{user_id}. */
export type DeletionMode = 'block' | 'cascade_apps' | 'transfer_apps';

/** A brief summary of a single app, included in the 409 body when the user owns apps. */
export interface OwnedApp {
  readonly app_id: number;
  readonly name: string;
}

/** Typed error thrown when the backend returns 409 because the target user owns apps. */
export class OwnedAppsError extends Error {
  constructor(
    message: string,
    readonly ownedApps: OwnedApp[],
  ) {
    super(message);
    this.name = 'OwnedAppsError';
  }
}

export interface DeleteUserOptions {
  readonly mode?: DeletionMode;
  readonly transferToUserId?: number;
}

/** Summary of an app returned by the admin transfer endpoint (mirrors backend AppTransferSummary). */
export interface AppTransferResult {
  readonly app_id: number;
  readonly name: string;
  readonly previous_owner_id: number;
  readonly new_owner_id: number;
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
  private readonly baseUrl = '/internal/admin';

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

  async deleteUser(
    userId: number,
    opts?: DeleteUserOptions,
  ): Promise<{ message: string }> {
    const mode = opts?.mode ?? 'block';
    const body: Record<string, unknown> = { mode };
    if (opts?.transferToUserId !== undefined) {
      body['transfer_to_user_id'] = opts.transferToUserId;
    }
    try {
      return await apiService.request(`${this.baseUrl}/users/${userId}`, {
        method: 'DELETE',
        body: JSON.stringify(body),
      }) as { message: string };
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 409) {
        // api.ts has already consumed the response body, so owned_apps cannot be
        // recovered here. Callers should pre-check owned_apps_count; typed error
        // still allows instanceof branching.
        throw new OwnedAppsError(err.message, []);
      }
      throw err;
    }
  }

  async transferAppOwner(
    appId: number,
    newOwnerId: number,
  ): Promise<AppTransferResult> {
    return await apiService.request(`${this.baseUrl}/apps/${appId}/transfer`, {
      method: 'POST',
      body: JSON.stringify({ new_owner_id: newOwnerId }),
    }) as AppTransferResult;
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

  async resetUserMarketplaceQuota(userId: number): Promise<{ message: string; user_id: number; previous_count: number; new_count: number; reset_by: string; timestamp: string }> {
    return await apiService.request(`${this.baseUrl}/users/${userId}/reset-marketplace-quota`, {
      method: 'POST',
    });
  }

  async createLocalUser(email: string, name: string): Promise<LocalUserCreated> {
    return await apiService.request(`${this.baseUrl}/users/local`, {
      method: 'POST',
      body: JSON.stringify({ email, name }),
    }) as LocalUserCreated;
  }

  async issueResetLink(userId: number): Promise<ResetLinkResult> {
    return await apiService.request(`${this.baseUrl}/users/${userId}/reset-link`, {
      method: 'POST',
    }) as ResetLinkResult;
  }

  async setPlatformRole(userId: number, role: 'viewer' | 'editor' | 'admin'): Promise<{ message: string; user_id: number; platform_role: string; warnings?: string[] }> {
    return await apiService.request(`${this.baseUrl}/users/${userId}/set-platform-role`, {
      method: 'POST',
      body: JSON.stringify({ role }),
    });
  }
}

export const adminService = new AdminService(); 