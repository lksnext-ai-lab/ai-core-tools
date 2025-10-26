# Client Project Setup Guide for AI-Core-Tools Extensible Library

This guide provides instructions on how to set up, customize, and deploy a new client project based on the **new extensible** `ai-core-tools` library.

## 1. Overview

The `ai-core-tools` project is now designed as a **fully modular and extensible platform**. Each client will have its own separate frontend project, which consumes the `ai-core-tools` base frontend as a **reusable React library** and connects to the shared `ai-core-tools` backend. This allows for client-specific branding, features, and authentication while maintaining a common, maintainable core.

**🚀 New Extensible Features:**
- **Modular Components**: Import individual components (Header, Sidebar, Footer, Layout, etc.)
- **Simplified Configuration**: Easy-to-use `LibraryConfig` interface
- **Advanced Theme System**: Multiple themes, custom CSS, theme switching
- **Route Extensibility**: Add custom routes and pages easily
- **Component Customization**: Deep customization options for all major components
- **Authentication Integration**: OIDC and session auth support

**Key Principles:**
- **Frontend-Only Projects**: Each client gets its own frontend repository/folder.
- **Base as Library**: The `ai-core-tools/frontend` is built as a reusable React library.
- **Client Customization**: Clients can define their own themes, add custom pages, and extend existing functionality.
- **Shared Backend**: All client projects connect to the same `ai-core-tools` backend instance.
- **OIDC Authentication**: Frontend supports OIDC for user authentication, configurable per client. API keys are still supported for backend API access.

## 2. Project Structure

A new client project will have the following structure:

```
client-project-name/
├── public/                         # Static assets (e.g., client logo)
├── src/
│   ├── config/
│   │   └── clientConfig.ts         # Client-specific configuration
│   ├── components/                 # Client-specific React components
│   ├── themes/                     # Client-specific theme overrides
│   ├── App.tsx                     # Main client app, imports BaseApp
│   └── ... (other client-specific files)
├── package.json                    # Frontend dependencies (includes @lksnext/ai-core-tools-base)
├── vite.config.ts                  # Frontend build configuration
├── README.md                       # Client project documentation
└── ... (other frontend files)
```

**Note**: Client projects only contain the frontend. The backend remains the shared AI Core Tools backend that all clients connect to.

## 3. Creating a New Client Project

Use the provided automation script to quickly scaffold a new client project:

```bash
./deploy/scripts/create-client-project.sh <client-name>
```

**Example:**
```bash
./deploy/scripts/create-client-project.sh my-client
```

This script will:
1. Create a new folder `clients/my-client` in the root of the `ai-core-tools` repository.
2. Copy the frontend template into the new client folder.
3. Replace placeholders like `CLIENT_ID_HERE` with `my-client` in all relevant files.

**After running the script:**
- Navigate to `clients/my-client` and run `npm install`.
- Review and configure the client-specific settings.

## 4. Frontend Customization

The client frontend is a standard React/Vite application that consumes the `@lksnext/ai-core-tools-base` library.

### 4.1. `src/config/libraryConfig.ts`

This is the primary file for configuring your client's frontend using the new **simplified LibraryConfig**.

```typescript
// clients/my-client/src/config/libraryConfig.ts
import type { LibraryConfig } from '@lksnext/ai-core-tools-base';
import { customTheme } from '../themes/customTheme';

export const libraryConfig: LibraryConfig = {
  // Basic configuration
  name: 'My Awesome Client AI',
  logo: '/my-client-logo.png',
  favicon: '/my-client-favicon.ico',
  
  // Theme configuration
  themeProps: {
    defaultTheme: 'client-custom',
    customThemes: {
      'client-custom': customTheme,
      'corporate': { /* corporate theme */ }
    },
    showThemeSelector: true
  },
  
  // Header configuration
  headerProps: {
    title: 'My Awesome Client AI',
    logoUrl: '/my-client-logo.png'
  },
  
  // Footer configuration
  footerProps: {
    copyright: '© 2024 My Company. All rights reserved.',
    showVersion: true
  },
  
  // Authentication configuration
  authProps: {
    enabled: true,
    oidc: {
      authority: 'https://your-oidc-provider.com',
      client_id: 'my-client',
      callbackPath: '/callback'
    }
  },
  
  // API configuration
  apiConfig: {
    baseUrl: 'http://localhost:8000',
    timeout: 30000,
    retries: 3
  },
  
  // Feature configuration
  features: {
    showSidebar: true,
    showHeader: true,
    showFooter: true,
    showThemeSelector: true
  }
};
```

**Key Configuration Options:**
- **`name`**: The display name for your client.
- **`themeProps`**: Configure multiple themes and theme switching.
- **`headerProps`**: Customize header appearance and content.
- **`footerProps`**: Configure footer content and visibility.
- **`authProps`**: Configure authentication (OIDC or session-based).
- **`apiConfig`**: Configure backend API connection.
- **`features`**: Toggle various UI features on/off.

### 4.2. `src/themes/customTheme.ts`

Customize your client's visual appearance:

```typescript
// clients/my-client/src/themes/customTheme.ts
import type { ThemeConfig } from '@lksnext/ai-core-tools-base';

export const customTheme: ThemeConfig = {
  name: 'my-client-theme',
  colors: {
    primary: '#10b981',    // emerald-500
    secondary: '#8b5cf6',  // violet-500
    accent: '#f59e0b',     // amber-500
    background: '#f9fafb', // gray-50
    surface: '#ffffff',    // white
    text: '#111827'        // gray-900
  },
  logo: '/my-client-logo.png',
  favicon: '/my-client-favicon.ico'
};
```

### 4.3. `src/App.tsx`

This file uses the new **ExtensibleBaseApp** with your `libraryConfig` and custom routes:

```typescript
// clients/my-client/src/App.tsx
import { ExtensibleBaseApp } from '@lksnext/ai-core-tools-base';
import type { ExtraRoute } from '@lksnext/ai-core-tools-base';
import { libraryConfig } from './config/libraryConfig';
import CustomPage from './pages/CustomPage';
import ExtensibilityDemo from './pages/ExtensibilityDemo';

function App() {
  const extraRoutes: ExtraRoute[] = [
    {
      path: '/extensibility-demo',
      element: <ExtensibilityDemo />,
      name: 'Extensibility Demo',
      protected: true
    },
    {
      path: '/custom-page',
      element: <CustomPage />,
      name: 'Custom Page',
      protected: true
    }
  ];

  return (
    <ExtensibleBaseApp 
      config={libraryConfig}
      extraRoutes={extraRoutes}
    />
  );
}

export default App;
```

### 4.4. Extensible Navigation System

The new library features a powerful extensible navigation system that allows you to add, override, or remove navigation items without redefining the entire navigation structure.

#### 4.4.1. Simple Navigation Configuration

Instead of defining the entire navigation, you can now just specify additions and overrides:

```typescript
// Old way (verbose)
navigationConfig: {
  mainFeatures: [/* all main features */],
  admin: [/* all admin features */],
  // ... hundreds of lines
}

// New way (simple)
navigation: {
  add: {
    custom: [
      {
        path: '/my-feature',
        name: 'My Feature',
        icon: '⭐',
        section: 'custom'
      }
    ]
  },
  override: [
    {
      path: '/about',
      name: 'About My Company',
      icon: '🏢'
    }
  ],
  remove: ['/admin/stats'] // Hide statistics
}
```

#### 4.4.2. Navigation Configuration Options

**Add New Navigation Items:**
```typescript
navigation: {
  add: {
    mainFeatures: [
      {
        path: '/dashboard',
        name: 'Dashboard',
        icon: '📊',
        section: 'mainFeatures'
      }
    ],
    custom: [
      {
        path: '/reports',
        name: 'Reports',
        icon: '📋',
        section: 'custom'
      }
    ],
    admin: [
      {
        path: '/admin/audit',
        name: 'Audit Logs',
        icon: '📝',
        section: 'admin',
        adminOnly: true
      }
    ]
  }
}
```

**Override Existing Items:**
```typescript
navigation: {
  override: [
    {
      path: '/apps',
      name: 'My Projects',  // Change name
      icon: '📱'            // Change icon
    },
    {
      path: '/admin/users',
      name: 'Team Management',
      adminOnly: true
    }
  ]
}
```

**Remove Navigation Items:**
```typescript
navigation: {
  remove: [
    '/admin/stats',  // Hide statistics
    '/about'         // Hide about page
  ]
}
```

#### 4.4.3. Using Modular Components

The new library allows you to import and use individual components:

```typescript
// Import individual components
import { 
  Header, 
  Sidebar, 
  Footer, 
  Layout, 
  ThemeSelector,
  useTheme 
} from '@lksnext/ai-core-tools-base';

// Create a custom layout
const CustomLayout: React.FC = () => {
  const { theme } = useTheme();
  
  return (
    <div className="min-h-screen flex flex-col">
      <Header 
        title="My Custom App"
        logoUrl="/my-logo.png"
        className="bg-blue-600 text-white"
      />
      <div className="flex flex-1">
        <Sidebar 
          navigationConfig={myNavigationConfig}
          className="w-64 bg-gray-100"
        />
        <main className="flex-1 p-6">
          <ThemeSelector />
          {/* Your content */}
        </main>
      </div>
      <Footer 
        copyright="© 2024 My Company"
        showVersion={true}
      />
    </div>
  );
};
```

### 4.5. Adding Custom Components and Pages

You can create new React components and pages within `src/components` or `src/pages` (or any other structure you prefer).

**Example (`src/pages/ExtensibilityDemo.tsx`):**
```typescript
import React, { useState } from 'react';
import { useTheme, ThemeSelector } from '@lksnext/ai-core-tools-base';

const ExtensibilityDemo: React.FC = () => {
  const { theme, switchTheme } = useTheme();
  const [selectedTheme, setSelectedTheme] = useState('client-custom');

  return (
    <div className="max-w-6xl mx-auto p-6">
      <h1 className="text-4xl font-bold mb-4" style={{ color: theme.colors?.primary }}>
        🚀 Extensibility Demo
      </h1>
      
      {/* Theme switching demo */}
      <div className="mb-8">
        <ThemeSelector />
        <button 
          onClick={() => switchTheme('corporate')}
          className="client-button px-4 py-2 rounded-lg"
        >
          Switch to Corporate Theme
        </button>
      </div>
      
      {/* Your custom content */}
    </div>
  );
};

export default ExtensibilityDemo;
```

## 5. Backend Configuration

Since all client projects connect to the same `ai-core-tools` backend, you need to configure the backend to support your client:

### 5.1. Environment Variables

The backend uses environment variables for client-specific configuration:

```bash
# Backend .env configuration
CLIENT_ID=my-client
CLIENT_NAME="My Awesome Client AI"
OIDC_ENABLED=false  # Set to true if using OIDC
OIDC_AUTHORITY=https://your-oidc-provider.com
OIDC_CLIENT_ID=my-client-backend
```

### 5.2. Client Configuration Endpoint

The backend provides a `/api/internal/client-config` endpoint that returns client-specific configuration for the frontend.

## 6. Local Development

To run your client project locally:

1. **Start the AI Core Tools backend:**
   ```bash
   cd /path/to/ai-core-tools/backend
   python -m uvicorn main:app --reload --port 8000
   ```

2. **Start your client frontend:**
   ```bash
   cd /path/to/clients/my-client
   npm install
   npm run dev
   ```

- Frontend will be available at `http://localhost:3000` (or another port if 3000 is busy).
- Backend API will be available at `http://localhost:8000`.

## 7. Deployment

### 7.1. Frontend Deployment

Build your client frontend for production:

```bash
cd /path/to/clients/my-client
npm run build
```

The built files will be in the `dist/` directory and can be deployed to any static hosting service.

### 7.2. Backend Deployment

The backend deployment remains the same as the base `ai-core-tools` backend. Ensure the backend environment variables are configured for your client.

## 8. Customization Examples

### 8.1. Custom Theme

```typescript
// src/themes/customTheme.ts
export const customTheme: ThemeConfig = {
  name: 'corporate-blue',
  colors: {
    primary: '#1e40af',    // blue-800
    secondary: '#dc2626', // red-600
    accent: '#059669',    // emerald-600
    background: '#f8fafc', // slate-50
    surface: '#ffffff',    // white
    text: '#0f172a'        // slate-900
  },
  logo: '/corporate-logo.png',
  favicon: '/corporate-favicon.ico'
};
```

### 8.2. OIDC Authentication

```typescript
// src/config/clientConfig.ts
export const clientConfig: ClientConfig = {
  clientId: 'my-client',
  name: 'My Client AI',
  theme: customTheme,
  auth: {
    type: 'oidc',
    oidc: {
      enabled: true,
      authority: 'https://your-oidc-provider.com/realms/my-client-realm',
      clientId: 'my-client-frontend',
      redirectUri: 'http://localhost:3000/callback',
      scope: 'openid profile email'
    }
  },
  branding: {
    companyName: 'My Client AI',
    logo: '/my-client-logo.png',
    favicon: '/my-client-favicon.ico',
    headerTitle: 'My Client AI'
  }
};
```

## 9. Troubleshooting

### 9.1. Library Import Issues

If you get errors about `@lksnext/ai-core-tools-base` not being found:

1. Make sure the base library is built:
   ```bash
   cd /path/to/ai-core-tools/frontend
   npm run build:lib
   ```

2. Check that the client's `package.json` points to the correct path:
   ```json
   {
     "dependencies": {
       "@lksnext/ai-core-tools-base": "file:../../../ai-core-tools/frontend"
     }
   }
   ```

### 9.2. Theme Not Applied

Ensure your theme is properly imported in `clientConfig.ts` and that the `BaseApp` is using the correct configuration.

### 9.3. Backend Connection Issues

Verify that:
- The backend is running on the expected port
- The API base URL in your client configuration is correct
- CORS is properly configured in the backend

## 10. Future Enhancements

- **Dynamic Route Loading**: Implement a more sophisticated system for dynamically loading client-specific routes and pages.
- **Shared Components**: Create a dedicated shared components library if multiple clients need common custom components.
- **Configuration Management**: Centralize client configuration management (e.g., a dedicated service or a configuration repository).

This guide provides a solid foundation for building and managing client-specific frontend instances of the AI-Core-Tools platform.