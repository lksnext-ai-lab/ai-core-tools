import { useCallback, useEffect, useRef, useState } from 'react';
import { getServiceApiClient } from '../components/services/serviceApi';
import type {
  ListProviderModelsRequest,
  ListProviderModelsResponse,
  ServiceKind,
  ServiceScope,
} from '../types/services';

interface UseProviderModelsOptions {
  readonly kind: ServiceKind;
  readonly scope: ServiceScope;
  readonly appId?: number;
  readonly request: ListProviderModelsRequest | null;
  readonly enabled: boolean;
}

interface UseProviderModelsResult {
  readonly data: ListProviderModelsResponse | null;
  readonly loading: boolean;
  readonly error: { message: string; status?: number } | null;
  readonly retry: () => void;
}

/**
 * Fetches the model list for a given provider/credentials combination.
 * Caching is intentionally session-local (no persistence): credentials
 * never round-trip through the cache key directly — only a stable hash.
 */
export function useProviderModels({
  kind,
  scope,
  appId,
  request,
  enabled,
}: UseProviderModelsOptions): UseProviderModelsResult {
  const [data, setData] = useState<ListProviderModelsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<UseProviderModelsResult['error']>(null);
  const [tick, setTick] = useState(0);
  const cancelTokenRef = useRef(0);

  const retry = useCallback(() => setTick((n) => n + 1), []);

  useEffect(() => {
    if (!enabled || !request) {
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }

    const myToken = ++cancelTokenRef.current;
    setLoading(true);
    setError(null);

    let client;
    try {
      client = getServiceApiClient(kind, scope, appId);
    } catch (e) {
      setError({ message: e instanceof Error ? e.message : 'Invalid context' });
      setLoading(false);
      return;
    }

    client
      .listModels(request)
      .then((response) => {
        if (cancelTokenRef.current !== myToken) return;
        setData(response);
      })
      .catch((err: unknown) => {
        if (cancelTokenRef.current !== myToken) return;
        const message =
          err instanceof Error ? err.message : 'Failed to load provider models';
        const status =
          typeof err === 'object' && err !== null && 'status' in err
            ? (err as { status?: number }).status
            : undefined;
        setError({ message, status });
        setData(null);
      })
      .finally(() => {
        if (cancelTokenRef.current !== myToken) return;
        setLoading(false);
      });
    // Trigger key includes `tick` so retry() refetches with the same args.
  }, [
    enabled,
    kind,
    scope,
    appId,
    request?.provider,
    request?.api_key,
    request?.base_url,
    request?.api_version,
    tick,
  ]);

  return { data, loading, error, retry };
}
