import React, { createContext, useContext, useState, useEffect } from 'react';
import type { ReactNode } from 'react';
import { configService } from '../core/ConfigService';
import { setApiAuthMode } from '../services/api';

export interface TierLimits {
  apps: number;
  agents: number;
  silos: number;
  llm_calls: number;
  collaborators: number;
  mcp_servers: number;
}

export interface Tiers {
  free: TierLimits;
  starter: TierLimits;
  pro: TierLimits;
}

export type AuthMode = 'oidc' | 'local';

// Fallback when /internal/config is unreachable or lacks auth_mode — prevents
// an OIDC deployment from silently degrading to LOCAL on a transient failure.
function resolveEnvAuthMode(): AuthMode {
  const runtimeConfig = (globalThis as unknown as Record<string, Record<string, string>>).__RUNTIME_CONFIG__;
  const oidcEnabled = runtimeConfig?.VITE_OIDC_ENABLED === undefined
    ? import.meta.env.VITE_OIDC_ENABLED === 'true'
    : runtimeConfig.VITE_OIDC_ENABLED === 'true';
  return oidcEnabled ? 'oidc' : 'local';
}

interface DeploymentModeContextType {
  readonly isSaasMode: boolean;
  readonly isLoading: boolean;
  readonly tiers: Tiers | null;
  /** 'local' | 'oidc' from /internal/config; null while loading. */
  readonly authMode: AuthMode | null;
}

const DeploymentModeContext = createContext<DeploymentModeContextType>({
  isSaasMode: false,
  isLoading: true,
  tiers: null,
  authMode: null,
});

export const useDeploymentMode = () => useContext(DeploymentModeContext);

interface DeploymentModeProviderProps {
  children: ReactNode;
}

export const DeploymentModeProvider: React.FC<DeploymentModeProviderProps> = ({ children }) => {
  const [isSaasMode, setIsSaasMode] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [tiers, setTiers] = useState<Tiers | null>(null);
  const [authMode, setAuthMode] = useState<AuthMode | null>(null);

  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const baseUrl = configService.getApiBaseUrl();
        const response = await fetch(`${baseUrl}/internal/config`);
        if (response.ok) {
          const data: {
            deployment_mode?: string;
            tiers?: Tiers;
            auth_mode?: string;
          } = await response.json();
          setIsSaasMode(data.deployment_mode === 'saas');
          setTiers(data.tiers ?? null);

          const resolvedMode: AuthMode =
            data.auth_mode === 'oidc' || data.auth_mode === 'local'
              ? data.auth_mode
              : resolveEnvAuthMode();
          setAuthMode(resolvedMode);
          setApiAuthMode(resolvedMode);
        }
      } catch {
        // Preserve the env-intended mode so OIDC deployments survive a transient failure.
        const fallbackMode = resolveEnvAuthMode();
        setIsSaasMode(false);
        setTiers(null);
        setAuthMode(fallbackMode);
        setApiAuthMode(fallbackMode);
      } finally {
        setIsLoading(false);
      }
    };

    fetchConfig();
  }, []);

  return (
    <DeploymentModeContext.Provider value={{ isSaasMode, isLoading, tiers, authMode }}>
      {children}
    </DeploymentModeContext.Provider>
  );
};
