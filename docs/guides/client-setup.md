# Client Project Setup

> Part of [Mattin AI Documentation](../README.md)

## Overview

**Client projects** are separate frontends that consume the `@lksnext/ai-core-tools-base` library. Each client can customize:
- Branding (logo, favicon, name)
- Theme (colors, typography)
- Custom pages and components
- Navigation structure
- Plugins

**Architecture**:
```
@lksnext/ai-core-tools-base (npm package)
    ↓ (imported by)
clients/
  ├── client-a/frontend/  → Custom branding + theme A
  ├── client-b/frontend/  → Custom branding + theme B
  └── client-c/frontend/  → Custom branding + theme C
```

## Creating a Client Project

### Using create-client-project.sh

```bash
# From repository root
./deploy/scripts/create-client-project.sh my-client

# Output:
# Client project created at: clients/my-client
#   frontend/          - Main client application
#   hello-world-plugin/ - Sample plugin
#   PLUGIN_EXAMPLES.md - Plugin guide
```

**What it creates**:
```
clients/my-client/
├── frontend/
│   ├── src/
│   │   ├── config/
│   │   │   └── libraryConfig.ts   # Main configuration
│   │   ├── themes/
│   │   │   └── customTheme.ts     # Custom theme
│   │   ├── pages/
│   │   │   └── CustomHomePage.tsx # Custom home page
│   │   └── App.tsx                 # App entry point
│   ├── public/
│   │   ├── client-logo.png         # Your logo
│   │   └── client-favicon.ico      # Your favicon
│   ├── package.json
│   └── vite.config.ts
├── hello-world-plugin/            # Sample plugin
└── PLUGIN_EXAMPLES.md             # Plugin documentation
```

## Project Structure

### libraryConfig.ts

**Main configuration file** at `src/config/libraryConfig.ts`:

```typescript
import type { LibraryConfig } from '@lksnext/ai-core-tools-base';
import { customTheme } from '../themes/customTheme';
import CustomHomePage from '../pages/CustomHomePage';

export const libraryConfig: LibraryConfig = {
  // Basic branding
  name: 'My Company AI',
  logo: '/client-logo.png',
  favicon: '/client-favicon.ico',
  homePage: CustomHomePage,
  
  // Theme configuration
  themeProps: {
    defaultTheme: 'corporate',
    customThemes: {
      'corporate': customTheme
    },
    showThemeSelector: true
  },
  
  // Header configuration
  headerProps: {
    title: 'My Company AI Platform',
    className: 'bg-blue-800 text-white'
  },
  
  // Footer configuration
  footerProps: {
    copyright: '© 2024 My Company. All rights reserved.',
    showVersion: true
  },
  
  // Custom navigation
  navigation: {
    add: {
      custom: [
        {
          path: '/dashboard',
          name: 'Dashboard',
          icon: '📊',
          section: 'main'
        }
      ]
    },
    remove: ['/agents']  // Hide default pages
  }
};
```

### src/themes/

Custom theme files:

```typescript
// src/themes/customTheme.ts
import type { Theme } from '@lksnext/ai-core-tools-base';

export const customTheme: Theme = {
  name: 'corporate',
  colors: {
    primary: '#1e40af',      // Blue-800
    secondary: '#dc2626',    // Red-600
    accent: '#059669',       // Emerald-600
    background: '#f8fafc',   // Slate-50
    surface: '#ffffff',      // White
    text: '#0f172a'          // Slate-900
  }
};
```

### public/

Static assets:

```
public/
├── client-logo.png      # Logo (recommended: 200x50px PNG)
├── client-favicon.ico   # Favicon (16x16, 32x32, 64x64)
└── custom-assets/       # Additional assets
```

## Configuration

### Theme Customization

**Colors**:
```typescript
themeProps: {
  customThemes: {
    'my-theme': {
      name: 'my-theme',
      colors: {
        primary: '#2563eb',     // Main brand color
        secondary: '#7c3aed',   // Secondary brand color
        accent: '#10b981',      // Accent/highlight color
        background: '#f9fafb',  // Page background
        surface: '#ffffff',     // Card/panel background
        text: '#111827'         // Text color
      }
    }
  }
}
```

**Multiple themes**:
```typescript
customThemes: {
  'light': { /* light theme */ },
  'dark': { /* dark theme */ },
  'high-contrast': { /* accessibility theme */ }
}
```

### Header & Branding

**Title only**:
```typescript
headerProps: {
  title: 'My Company AI'
}
```

**Logo + title**:
```typescript
headerProps: {
  title: 'My Company',
  logoUrl: '/client-logo.png'
}
```

**Custom styling**:
```typescript
headerProps: {
  title: 'AI Platform',
  className: 'bg-gradient-to-r from-blue-600 to-purple-600 text-white shadow-lg'
}
```

### Navigation Customization

**Add custom pages**:
```typescript
navigation: {
  add: {
    main: [
      { path: '/dashboard', name: 'Dashboard', icon: '📊' }
    ],
    custom: [
      { path: '/reports', name: 'Reports', icon: '📈' },
      { path: '/settings', name: 'Settings', icon: '⚙️' }
    ]
  }
}
```

**Remove default pages**:
```typescript
navigation: {
  remove: ['/agents', '/silos', '/domains']
}
```

**Reorder sections**:
```typescript
navigationProps: {
  sectionOrder: ['main', 'custom', 'ai', 'admin']
}
```

## Custom Pages & Components

### Adding a Custom Page

1. Create page component:

```typescript
// src/pages/CustomPage.tsx
import React from 'react';

export default function CustomPage() {
  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold">Custom Page</h1>
      <p>Your custom content here</p>
    </div>
  );
}
```

2. Add to `App.tsx`:

```typescript
import CustomPage from './pages/CustomPage';

// In your App component:
<Routes>
  <Route path="/custom" element={<CustomPage />} />
</Routes>
```

3. Add to navigation:

```typescript
// libraryConfig.ts
navigation: {
  add: {
    custom: [
      { path: '/custom', name: 'Custom', icon: '✨' }
    ]
  }
}
```

### Using Base Library Components

Import and use components from the base library:

```typescript
import {
  Card,
  Button,
  Input,
  Select,
  AgentList,
  ConversationHistory
} from '@lksnext/ai-core-tools-base';

function MyComponent() {
  return (
    <Card>
      <h2>My Component</h2>
      <Button variant="primary">Click me</Button>
      <AgentList appId={1} />
    </Card>
  );
}
```

## Updating Client Projects

### Updating Base Library Version

```bash
cd clients/my-client/frontend
npm update @lksnext/ai-core-tools-base
```

### Manual version update:

```bash
npm install @lksnext/ai-core-tools-base@latest
```

### Update Script

Automated update script: `./deploy/scripts/update-client.sh`

```bash
./deploy/scripts/update-client.sh my-client
```

**What it does**:
1. Pulls latest base library version
2. Updates `package.json`
3. Runs `npm install`
4. Rebuilds client

## Existing Client Examples

### holiday

Location: `clients/holiday/`

**Features**:
- Custom theme (holiday colors)
- Custom home page
- Sample plugin integration

### eider-example

Location: `clients/eider-example/`

**Features**:
- Corporate theme
- Custom dashboard
- Multiple plugins

### elkar-example

Location: `clients/elkar-example/`

**Features**:
- Minimal configuration
- Custom branding only
- Uses default pages

## Development Workflow

### 1. Create Client

```bash
./deploy/scripts/create-client-project.sh my-client
cd clients/my-client/frontend
```

### 2. Install Dependencies

```bash
npm install
```

### 3. Configure

Edit `src/config/libraryConfig.ts`:
- Set `name`, `logo`, `favicon`
- Customize theme
- Configure header/footer

### 4. Add Assets

Replace placeholders:
- `public/client-logo.png`
- `public/client-favicon.ico`

### 5. Develop

```bash
npm run dev
# Opens at http://localhost:5173
```

### 6. Build

```bash
npm run build
# Output: dist/
```

### 7. Deploy

```bash
# Serve static files
npm run preview

# Or deploy dist/ to hosting service
```

## Best Practices

1. **Version control**: Each client should be in its own repository (or monorepo subdirectory)
2. **Environment variables**: Use `.env` for client-specific API URLs
3. **Theme consistency**: Match colors to brand guidelines
4. **Lazy loading**: Use React lazy imports for large custom pages
5. **Type safety**: Leverage TypeScript for configuration
6. **Testing**: Test theme changes across all pages
7. **Documentation**: Document custom pages and components

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| "Module not found" | Missing base library | `npm install @lksnext/ai-core-tools-base` |
| Theme not applying | Wrong theme name in config | Check `defaultTheme` matches key in `customThemes` |
| Logo not showing | Wrong path | Use `/` prefix for public files: `/client-logo.png` |
| Build fails | TypeScript errors | Check `libraryConfig` types match `LibraryConfig` interface |
| Custom page not routing | Missing route in App.tsx | Add `<Route path="/custom" element={<CustomPage />} />` |

## See Also

- [Plugin Development](plugin-development.md) — Creating plugins for clients
- [Frontend Architecture](../architecture/frontend.md) — Base library structure
- [Deployment Guide](deployment.md) — Building and deploying client apps
