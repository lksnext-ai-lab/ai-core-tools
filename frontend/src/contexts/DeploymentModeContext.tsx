import React, { createContext, useContext, useState, useEffect } from 'react';
import type { ReactNode } from 'react';
import { configService } from '../core/ConfigService';

interface DeploymentModeContextType {
  isSaasMode: boolean;
  isLoading: boolean;
}

const DeploymentModeContext = createContext<DeploymentModeContextType>({
  isSaasMode: false,
  isLoading: true,
});

export const useDeploymentMode = () => useContext(DeploymentModeContext);

interface DeploymentModeProviderProps {
  children: ReactNode;
}

export const DeploymentModeProvider: React.FC<DeploymentModeProviderProps> = ({ children }) => {
  const [isSaasMode, setIsSaasMode] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const baseUrl = configService.getApiBaseUrl();
        const response = await fetch(`${baseUrl}/internal/config`);
        if (response.ok) {
          const data = await response.json();
          setIsSaasMode(data.deployment_mode === 'saas');
        }
      } catch {
        // Default to self-managed if the endpoint is unreachable
        setIsSaasMode(false);
      } finally {
        setIsLoading(false);
      }
    };

    fetchConfig();
  }, []);

  return (
    <DeploymentModeContext.Provider value={{ isSaasMode, isLoading }}>
      {children}
    </DeploymentModeContext.Provider>
  );
};
