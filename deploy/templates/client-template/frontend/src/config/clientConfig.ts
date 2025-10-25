import type { ClientConfig } from '@lksnext/ai-core-tools-base';
import { customTheme } from '../themes/customTheme';

export const clientConfig: ClientConfig = {
  clientId: 'CLIENT_ID_HERE',
  name: 'CLIENT_NAME_HERE',
  theme: customTheme,
  auth: {
    type: 'oidc',  // or 'session'
    oidc: {
      enabled: true,
      authority: 'https://your-oidc-provider.com',
      clientId: 'your-client-id',
      redirectUri: 'http://localhost:3000/callback',
      scope: 'openid profile email'
    }
  },
  branding: {
    companyName: 'CLIENT_COMPANY_NAME',
    logo: '/client-logo.png',
    favicon: '/client-favicon.ico',
    headerTitle: 'CLIENT_HEADER_TITLE'
  },
  api: {
    baseUrl: 'http://localhost:8000', // Backend API URL
    timeout: 30000,
    retries: 3
  },
  navigation: {
    // Add custom navigation items
    custom: [
      {
        path: '/apps/:appId/custom-feature',
        name: 'Custom Feature',
        icon: '⭐',
        section: 'custom'
      }
    ]
  }
};
