import React, { createContext, useContext, useState, useEffect } from 'react';
import type { ReactNode } from 'react';
import { configService } from '../core/ConfigService';

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

interface DeploymentModeContextType {
  isSaasMode: boolean;
  isLoading: boolean;
  tiers: Tiers | null;
}

const DeploymentModeContext = createContext<DeploymentModeContextType>({
  isSaasMode: false,
  isLoading: true,
  tiers: null,
});

export const useDeploymentMode = () => useContext(DeploymentModeContext);

interface DeploymentModeProviderProps {
  children: ReactNode;
}

export const DeploymentModeProvider: React.FC<DeploymentModeProviderProps> = ({ children }) => {
  const [isSaasMode, setIsSaasMode] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [tiers, setTiers] = useState<Tiers | null>(null);

  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const baseUrl = configService.getApiBaseUrl();
        const response = await fetch(`${baseUrl}/internal/config`);
        if (response.ok) {
          const data = await response.json();
          setIsSaasMode(data.deployment_mode === 'saas');
          setTiers(data.tiers ?? null);
        }
      } catch {
        // Default to self-managed if the endpoint is unreachable
        setIsSaasMode(false);
        setTiers(null);
      } finally {
        setIsLoading(false);
      }
    };

    fetchConfig();
  }, []);

  return (
    <DeploymentModeContext.Provider value={{ isSaasMode, isLoading, tiers }}>
      {children}
    </DeploymentModeContext.Provider>
  );
};
