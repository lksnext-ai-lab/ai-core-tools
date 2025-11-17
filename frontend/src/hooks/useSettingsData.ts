import { useState, useEffect } from 'react';
import { useSettingsCache } from '../contexts/SettingsCacheContext';

/**
 * Custom hook for managing settings page data with caching
 * Eliminates repetitive loading, error handling, and cache management code
 * 
 * @param appId - The application ID
 * @param cacheKey - The cache key for storing data
 * @param apiMethod - The API method to fetch data
 * @param dependencies - Additional dependencies for the useEffect hook
 * @returns Object containing data, loading state, error, and reload function
 */
export function useSettingsData<T>(
  appId: string | undefined,
  cacheKey: keyof ReturnType<typeof useSettingsCache>,
  apiMethod: (appId: number) => Promise<T[]>,
  dependencies: any[] = []
) {
  const [data, setData] = useState<T[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const settingsCache = useSettingsCache();

  /**
   * Load data from cache or API
   * @param force - Force reload from API, bypassing cache
   */
  const loadData = async (force = false) => {
    if (!appId) {
      setLoading(false);
      return;
    }

    // Check cache first (unless force reload)
    if (!force) {
      const getCacheMethod = `get${cacheKey.charAt(0).toUpperCase() + cacheKey.slice(1)}` as keyof typeof settingsCache;
      const cachedData = typeof settingsCache[getCacheMethod] === 'function' 
        ? (settingsCache[getCacheMethod] as (appId: string) => T[] | null)(appId)
        : null;
      
      if (cachedData) {
        setData(cachedData);
        setLoading(false);
        return;
      }
    }

    // Load from API
    try {
      setLoading(true);
      setError(null);
      const response = await apiMethod(parseInt(appId));
      setData(response);
      
      // Cache the response
      const setCacheMethod = `set${cacheKey.charAt(0).toUpperCase() + cacheKey.slice(1)}` as keyof typeof settingsCache;
      if (typeof settingsCache[setCacheMethod] === 'function') {
        (settingsCache[setCacheMethod] as (appId: string, data: T[]) => void)(appId, response);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data');
      console.error(`Error loading ${cacheKey}:`, err);
    } finally {
      setLoading(false);
    }
  };

  // Load data on mount and when dependencies change
  useEffect(() => {
    loadData();
  }, [appId, ...dependencies]);

  /**
   * Force reload data from API
   */
  const reload = () => loadData(true);

  return {
    data,
    setData,
    loading,
    error,
    reload
  };
}

