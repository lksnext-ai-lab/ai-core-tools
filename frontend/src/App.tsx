/*
 * IA-Core-Tools - AI Toolbox Platform
 * Copyright (C) 2024 LKS Next
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

import { ExtensibleBaseApp } from './core/ExtensibleBaseApp';
import { baseTheme } from './themes/baseTheme';
import type { LibraryConfig } from './core/types';

// Get runtime configuration injected by container at startup
// Falls back to build-time environment variables for local development
const runtimeConfig = (window as any).__RUNTIME_CONFIG__;

const getConfig = (key: string, fallback: string = ''): string => {
  return runtimeConfig?.[key] || import.meta.env[key] || fallback;
};

// Demo configuration for the base application
const demoConfig: LibraryConfig = {
  name: 'Mattin AI',
  logo: '/mattin-small.png',
  favicon: '/favicon.ico',
  
  themeProps: {
    defaultTheme: 'base',
    customThemes: {
      'base': baseTheme
    },
    showThemeSelector: false
  },
  
  headerProps: {
    title: 'Mattin AI'
  },
  
  footerProps: {
    copyright: '© 2024 Mattin AI',
    showVersion: true
  },
  
  authProps: {
    enabled: getConfig('VITE_OIDC_ENABLED') === 'true',
    oidc: {
      authority: getConfig('VITE_OIDC_AUTHORITY'),
      client_id: getConfig('VITE_OIDC_CLIENT_ID'),
      callbackPath: '/auth/success',
      scope: getConfig('VITE_OIDC_SCOPE', 'openid profile email'),
      audience: getConfig('VITE_OIDC_AUDIENCE')
    }
  },
  
  apiConfig: {
    baseUrl: getConfig('VITE_API_BASE_URL', 'http://localhost:8000'),
    timeout: 30000,
    retries: 3
  },
  
  features: {
    showSidebar: true,
    showHeader: true,
    showFooter: true
  }
};

function App() {
  return (
    <ExtensibleBaseApp 
      config={demoConfig}
      extraRoutes={[]}
    />
  );
}

export default App;