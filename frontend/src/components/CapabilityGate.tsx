import React from 'react';
import type { ReactNode } from 'react';
import { useCapabilities, useCapability } from '../contexts/CapabilitiesContext';

interface CapabilityGateProps {
  name: string;
  fallback?: ReactNode;
  children: ReactNode;
}

/**
 * Renders children only when the named capability is enabled.
 * Renders nothing (or fallback) while capabilities are loading to avoid flash.
 */
export const CapabilityGate: React.FC<CapabilityGateProps> = ({ name, fallback, children }) => {
  const { isLoading } = useCapabilities();
  const enabled = useCapability(name);

  if (isLoading) return null;
  return enabled ? <>{children}</> : <>{fallback ?? null}</>;
};

export default CapabilityGate;
