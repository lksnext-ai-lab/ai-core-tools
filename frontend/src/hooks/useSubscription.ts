import { useState, useEffect, useCallback } from 'react';
import { apiService } from '../services/api';
import { useDeploymentMode } from '../contexts/DeploymentModeContext';

export interface SubscriptionData {
  tier: string;
  billing_status: string;
  trial_end: string | null;
  call_count: number;
  call_limit: number;
  pct_used: number;
  max_apps: number;
  agents_per_app: number;
  silos_per_app: number;
  skills_per_app: number;
  mcp_servers_per_app: number;
  collaborators_per_app: number;
  admin_override_tier: string | null;
}

export interface UsageData {
  call_count: number;
  call_limit: number;
  period_start: string | null;
  pct_used: number;
}

interface UseSubscriptionReturn {
  subscription: SubscriptionData | null;
  usage: UsageData | null;
  isLoading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

export const useSubscription = (): UseSubscriptionReturn => {
  const { isSaasMode } = useDeploymentMode();
  const [subscription, setSubscription] = useState<SubscriptionData | null>(null);
  const [usage, setUsage] = useState<UsageData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    if (!isSaasMode) {
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const [subData, usageData] = await Promise.all([
        apiService.getSubscription(),
        apiService.getUsage(),
      ]);
      setSubscription(subData as SubscriptionData);
      setUsage(usageData as UsageData);
    } catch (err: any) {
      setError(err?.message ?? 'Failed to load subscription data');
    } finally {
      setIsLoading(false);
    }
  }, [isSaasMode]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { subscription, usage, isLoading, error, refresh: fetchData };
};
