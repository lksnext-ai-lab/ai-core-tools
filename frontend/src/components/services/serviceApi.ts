import { apiService } from '../../services/api';
import type {
  ListProviderModelsRequest,
  ListProviderModelsResponse,
  SandboxServiceFormData,
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
  /** Sandbox services have no "list models" concept — omitted for `kind === 'sandbox'`. */
  listModels?(req: ListProviderModelsRequest): Promise<ListProviderModelsResponse>;
  /**
   * Test the connection with the provided payload. When ``serviceId`` is
   * supplied (edit mode) and the payload's API key is masked, the backend
   * recovers the stored key transparently — so the user doesn't have to
   * re-type the secret on every check.
   */
  testConnection(
    payload: ServiceFormData | SandboxServiceFormData,
    serviceId?: number,
  ): Promise<TestConnectionResult>;
}

/**
 * Resolve the right API methods for the given service context.
 *
 * Both the wizard's "list models" hook and the "test connection" button
 * need to fan out across six endpoints (AI/embedding/sandbox × app/system).
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
        testConnection: (payload, serviceId) =>
          apiService.testSystemAIServiceConnectionWithConfig(
            payload,
            serviceId,
          ) as Promise<TestConnectionResult>,
      };
    }
    if (kind === 'embedding') {
      return {
        listModels: (req) =>
          apiService.listSystemEmbeddingServiceProviderModels(req),
        testConnection: (payload, serviceId) =>
          apiService.testSystemEmbeddingServiceConnectionWithConfig(
            payload,
            serviceId,
          ) as Promise<TestConnectionResult>,
      };
    }
    return {
      testConnection: (payload, serviceId) =>
        apiService.testSystemSandboxServiceConnectionWithConfig(
          payload,
          serviceId,
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
      testConnection: (payload, serviceId) =>
        apiService.testAIServiceConnectionWithConfig(
          id,
          payload,
          serviceId,
        ) as Promise<TestConnectionResult>,
    };
  }
  if (kind === 'embedding') {
    return {
      listModels: (req) => apiService.listEmbeddingServiceProviderModels(id, req),
      testConnection: (payload, serviceId) =>
        apiService.testEmbeddingServiceConnectionWithConfig(
          id,
          payload,
          serviceId,
        ) as Promise<TestConnectionResult>,
    };
  }
  return {
    testConnection: (payload, serviceId) =>
      apiService.testSandboxServiceConnectionWithConfig(
        id,
        payload,
        serviceId,
      ) as Promise<TestConnectionResult>,
  };
}
