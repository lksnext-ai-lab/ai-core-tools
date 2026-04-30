import { apiService } from '../../services/api';
import type {
  ListProviderModelsRequest,
  ListProviderModelsResponse,
  ServiceFormData,
  ServiceKind,
  ServiceScope,
} from '../../types/services';

export interface TestConnectionResult {
  readonly status: 'success' | 'error';
  readonly message: string;
  readonly response?: string;
}

/** Strongly-typed view of the API surface needed by a single (kind, scope) combo. */
export interface ServiceApiClient {
  listModels(req: ListProviderModelsRequest): Promise<ListProviderModelsResponse>;
  testConnection(payload: ServiceFormData): Promise<TestConnectionResult>;
}

/**
 * Resolve the right API methods for the given service context.
 *
 * Both the wizard's "list models" hook and the "test connection" button
 * need to fan out across four endpoints (AI/embedding × app/system).
 * Centralising that fan-out here keeps the dispatch logic in one place
 * — adding a new action means touching this factory only.
 *
 * Throws if ``scope === 'app'`` but ``appId`` is missing — that is a
 * programming error and callers should treat it as such.
 */
export function getServiceApiClient(
  kind: ServiceKind,
  scope: ServiceScope,
  appId: number | undefined,
): ServiceApiClient {
  if (scope === 'system') {
    if (kind === 'ai') {
      return {
        listModels: (req) =>
          apiService.listSystemAIServiceProviderModels(req),
        testConnection: (payload) =>
          apiService.testSystemAIServiceConnectionWithConfig(
            payload,
          ) as Promise<TestConnectionResult>,
      };
    }
    return {
      listModels: (req) =>
        apiService.listSystemEmbeddingServiceProviderModels(req),
      testConnection: (payload) =>
        apiService.testSystemEmbeddingServiceConnectionWithConfig(
          payload,
        ) as Promise<TestConnectionResult>,
    };
  }

  if (appId == null) {
    throw new Error('appId is required when scope is "app"');
  }
  const id = appId;

  if (kind === 'ai') {
    return {
      listModels: (req) => apiService.listAIServiceProviderModels(id, req),
      testConnection: (payload) =>
        apiService.testAIServiceConnectionWithConfig(
          id,
          payload,
        ) as Promise<TestConnectionResult>,
    };
  }
  return {
    listModels: (req) => apiService.listEmbeddingServiceProviderModels(id, req),
    testConnection: (payload) =>
      apiService.testEmbeddingServiceConnectionWithConfig(
        id,
        payload,
      ) as Promise<TestConnectionResult>,
  };
}
