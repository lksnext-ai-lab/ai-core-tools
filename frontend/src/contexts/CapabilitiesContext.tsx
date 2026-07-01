import React, { createContext, useContext, useState, useEffect } from 'react';
import type { ReactNode } from 'react';
import type { Capabilities } from '../types/sharepoint';
import { apiService } from '../services/api';

interface CapabilitiesContextType {
  capabilities: Capabilities;
  isLoading: boolean;
}

const CapabilitiesContext = createContext<CapabilitiesContextType>({
  capabilities: {},
  isLoading: true,
});

export const useCapabilities = () => useContext(CapabilitiesContext);

export const useCapability = (name: string): boolean => {
  const { capabilities } = useContext(CapabilitiesContext);
  return capabilities[name]?.enabled === true;
};

interface CapabilitiesProviderProps {
  children: ReactNode;
}

export const CapabilitiesProvider: React.FC<CapabilitiesProviderProps> = ({ children }) => {
  const [capabilities, setCapabilities] = useState<Capabilities>({});
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchCapabilities = async () => {
      try {
        // suppressAuthRedirect prevents 401 from triggering the global refresh/redirect loop.
        const data = await apiService.request(
          '/internal/capabilities',
          {},
          false,
          { suppressAuthRedirect: true },
        ) as Capabilities;
        setCapabilities(data);
      } catch {
        // Leave capabilities empty — feature gating defaults to hidden
      } finally {
        setIsLoading(false);
      }
    };

    fetchCapabilities();
  }, []);

  return (
    <CapabilitiesContext.Provider value={{ capabilities, isLoading }}>
      {children}
    </CapabilitiesContext.Provider>
  );
};
