import { apiService } from './api';
import type {
  SharePointSource,
  SharePointSourceDetail,
  SharePointSourceCreateRequest,
  SharePointSourceUpdateRequest,
  MicrosoftSite,
  MicrosoftDrive,
  TestConnectionRequest,
} from '../types/sharepoint';

const base = (appId: number) => `/internal/apps/${appId}/sharepoint-sources`;

export const sharepointApi = {
  listSources: (appId: number): Promise<SharePointSource[]> =>
    apiService.request(base(appId)),

  getSource: (appId: number, sourceId: number): Promise<SharePointSourceDetail> =>
    apiService.request(`${base(appId)}/${sourceId}`),

  createSource: (appId: number, data: SharePointSourceCreateRequest): Promise<SharePointSource> =>
    apiService.request(base(appId), { method: 'POST', body: JSON.stringify(data) }),

  updateSource: (
    appId: number,
    sourceId: number,
    data: SharePointSourceUpdateRequest,
  ): Promise<SharePointSource> =>
    apiService.request(`${base(appId)}/${sourceId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deleteSource: (appId: number, sourceId: number): Promise<null> =>
    apiService.request(`${base(appId)}/${sourceId}`, { method: 'DELETE' }),

  triggerSync: (
    appId: number,
    sourceId: number,
  ): Promise<{ message: string; source_id: number; status: string }> =>
    apiService.request(`${base(appId)}/${sourceId}/sync`, { method: 'POST' }),

  searchSites: (params: {
    tenant_id: string;
    client_id: string;
    client_secret: string;
    q: string;
  }): Promise<MicrosoftSite[]> => {
    const qs = new URLSearchParams(params as Record<string, string>).toString();
    return apiService.request(`/internal/microsoft/sites?${qs}`);
  },

  listDrives: (params: {
    tenant_id: string;
    client_id: string;
    client_secret: string;
    site_id: string;
  }): Promise<MicrosoftDrive[]> => {
    const qs = new URLSearchParams(params as Record<string, string>).toString();
    return apiService.request(`/internal/microsoft/drives?${qs}`);
  },

  resolveSite: (params: {
    tenant_id: string;
    client_id: string;
    client_secret: string;
    site_url: string;
  }): Promise<MicrosoftSite> => {
    const qs = new URLSearchParams(params as Record<string, string>).toString();
    return apiService.request(`/internal/microsoft/resolve-site?${qs}`);
  },

  testConnection: (data: TestConnectionRequest): Promise<{ ok: boolean; error?: string }> =>
    apiService.request('/internal/microsoft/test-connection', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};
