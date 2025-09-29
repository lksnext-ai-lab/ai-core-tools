export interface IdentityProviderConfig {
  key: string;
  name: string;
  authority: string;
  clientId: string;
  scope: string;
  redirectUri: string;
  postLogoutRedirectUri?: string;
  extraAuthorizeParams?: Record<string, string>;
  logoutUrl?: string;
}

const DEFAULT_SCOPE = 'openid profile email';

type ProviderEnvPrefix = 'OIDC_MICROSOFT' | 'OIDC_GOOGLE' | 'OIDC_KEYCLOAK';

const providerMetadata: Array<{
  key: string;
  name: string;
  prefix: ProviderEnvPrefix;
  defaults?: Partial<IdentityProviderConfig>;
}> = [
  {
    key: 'microsoft',
    name: 'Microsoft',
    prefix: 'OIDC_MICROSOFT',
    defaults: {
      extraAuthorizeParams: {
        prompt: 'select_account',
      },
    },
  },
  {
    key: 'google',
    name: 'Google',
    prefix: 'OIDC_GOOGLE',
    defaults: {
      extraAuthorizeParams: {
        prompt: 'select_account',
        access_type: 'offline',
      },
      logoutUrl: 'https://accounts.google.com/Logout',
    },
  },
  {
    key: 'keycloak',
    name: 'Keycloak',
    prefix: 'OIDC_KEYCLOAK',
  },
];

const toConfig = (prefix: ProviderEnvPrefix) => {
  const authority = import.meta.env[`VITE_${prefix}_AUTHORITY` as const];
  const clientId = import.meta.env[`VITE_${prefix}_CLIENT_ID` as const];
  const redirectUri =
    import.meta.env[`VITE_${prefix}_REDIRECT_URI` as const] || `${window.location.origin}/auth/callback`;
  const postLogoutRedirectUri =
    import.meta.env[`VITE_${prefix}_LOGOUT_REDIRECT_URI` as const] || `${window.location.origin}/login`;
  const scope = import.meta.env[`VITE_${prefix}_SCOPE` as const] || DEFAULT_SCOPE;

  if (!authority || !clientId) {
    return null;
  }

  return {
    authority,
    clientId,
    redirectUri,
    postLogoutRedirectUri,
    scope,
  } satisfies Partial<IdentityProviderConfig>;
};

export function getIdentityProviders(): IdentityProviderConfig[] {
  const providers: IdentityProviderConfig[] = [];

  for (const { key, name, prefix, defaults } of providerMetadata) {
    const config = toConfig(prefix);
    if (!config) {
      continue;
    }

    providers.push({
      key,
      name,
      authority: config.authority!,
      clientId: config.clientId!,
      redirectUri: config.redirectUri!,
      postLogoutRedirectUri: config.postLogoutRedirectUri,
      scope: config.scope ?? DEFAULT_SCOPE,
      extraAuthorizeParams: defaults?.extraAuthorizeParams,
      logoutUrl: defaults?.logoutUrl,
    });
  }

  return providers;
}

export function getIdentityProviderByKey(key: string): IdentityProviderConfig | undefined {
  return getIdentityProviders().find((provider) => provider.key === key);
}

export function getDefaultIdentityProvider(): IdentityProviderConfig | undefined {
  const providers = getIdentityProviders();
  return providers[0];
}
