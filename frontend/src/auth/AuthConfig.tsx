import React from 'react';
import { OIDCProvider } from './OIDCProvider';

export interface AuthProps {
  enabled?: boolean;
  oidc?: {
    authority: string;
    client_id: string;
    callbackPath?: string;
    scope?: string;
    audience?: string;
  };
}

interface AuthProviderProps {
  config?: AuthProps;
  children: React.ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ 
  config, 
  children 
}) => {
  // If auth is disabled or not configured, render children without auth
  if (!config?.enabled || !config.oidc) {
    return <>{children}</>;
  }

  // Convert to the format expected by OIDCProvider
  const oidcConfig = {
    type: 'oidc' as const,
    oidc: {
      enabled: true,
      authority: config.oidc.authority,
      clientId: config.oidc.client_id,
      redirectUri: `${globalThis.location.origin}${config.oidc.callbackPath || '/callback'}`,
      scope: config.oidc.scope || 'openid profile email',
      audience: config.oidc.audience
    }
  };

  return (
    <OIDCProvider config={oidcConfig}>
      {children}
    </OIDCProvider>
  );
};
