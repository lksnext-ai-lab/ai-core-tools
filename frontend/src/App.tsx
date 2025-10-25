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

import { BaseApp } from './core/BaseApp';
import { baseTheme } from './themes/baseTheme';
import type { ClientConfig } from './core/types';

// Demo configuration for the base application
const demoConfig: ClientConfig = {
  clientId: 'mattin-demo',
  name: 'Mattin AI - Core Tools',
  theme: baseTheme,
  auth: {
    type: 'session' // Use existing session-based auth for demo
  },
  branding: {
    companyName: 'Mattin AI',
    logo: '/mattin-small.png',
    favicon: '/favicon.ico',
    headerTitle: 'Mattin AI - Core Tools'
  },
  api: {
    baseUrl: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
    timeout: 30000,
    retries: 3
  }
};

function App() {
  return (
    <BaseApp 
      clientConfig={demoConfig}
      extraRoutes={[]}
    />
  );
}

export default App;