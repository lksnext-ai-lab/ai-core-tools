# Plugin Development

> Part of [Mattin AI Documentation](../README.md)

## Overview

**Plugins** extend client projects with reusable, modular features. Plugins are npm packages that provide:
- Custom pages and components
- Navigation entries
- Routes
- Themes
- Business logic

**Benefits**:
- **Reusability**: Share features across multiple clients
- **Modularity**: Enable/disable features easily
- **Maintainability**: Update plugins independently
- **Distribution**: Publish to npm for team use

## Plugin Structure

```
my-plugin/
├── src/
│   ├── index.ts              # Plugin factory function
│   ├── pages/
│   │   └── PluginPage.tsx    # Plugin page components
│   └── types.ts               # TypeScript types
├── package.json
├── tsconfig.json
└── README.md
```

### package.json

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "main": "dist/index.js",
  "types": "dist/index.d.ts",
  "files": ["dist"],
  "scripts": {
    "build": "tsc",
    "dev": "tsc --watch"
  },
  "peerDependencies": {
    "react": "^18.0.0",
    "react-dom": "^18.0.0",
    "@lksnext/ai-core-tools-base": "^1.0.0"
  },
  "devDependencies": {
    "typescript": "^5.0.0",
    "@types/react": "^18.0.0",
    "@types/react-dom": "^18.0.0"
  }
}
```

### Entry Point (src/index.ts)

```typescript
import type { PluginInterface } from '@lksnext/ai-core-tools-base';
import PluginPage from './pages/PluginPage';

export interface MyPluginConfig {
  featureEnabled: boolean;
  customColor: string;
}

export function createMyPlugin(config: MyPluginConfig): PluginInterface {
  return {
    name: 'my-plugin',
    version: '1.0.0',
    
    navigation: [
      {
        path: '/my-plugin',
        name: 'My Plugin',
        icon: '🔌',
        section: 'custom',
        requiresAuth: true
      }
    ],
    
    routes: [
      {
        path: '/my-plugin',
        element: <PluginPage color={config.customColor} />,
        requiresAuth: true
      }
    ]
  };
}
```

## Creating a Plugin

### Step 1: Initialize Project

```bash
mkdir my-plugin
cd my-plugin
npm init -y
npm install --save-dev typescript @types/react @types/react-dom
npm install --save-peer react react-dom @lksnext/ai-core-tools-base
```

### Step 2: Configure TypeScript

```json
// tsconfig.json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "ESNext",
    "lib": ["ES2020", "DOM"],
    "jsx": "react-jsx",
    "declaration": true,
    "outDir": "./dist",
    "esModuleInterop": true,
    "skipLibCheck": true
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist"]
}
```

### Step 3: Create Plugin Page

```typescript
// src/pages/PluginPage.tsx
import React from 'react';
import { Card, Button } from '@lksnext/ai-core-tools-base';

interface PluginPageProps {
  color: string;
}

export default function PluginPage({ color }: PluginPageProps) {
  return (
    <div className="p-6">
      <Card>
        <h1 className="text-3xl font-bold" style={{ color }}>
          My Plugin
        </h1>
        <p>Custom plugin content</p>
        <Button variant="primary">Action</Button>
      </Card>
    </div>
  );
}
```

### Step 4: Create Plugin Factory

```typescript
// src/index.ts
import type { PluginInterface, NavigationItem, Route } from '@lksnext/ai-core-tools-base';
import PluginPage from './pages/PluginPage';

export interface MyPluginConfig {
  color: string;
  title: string;
}

export function createMyPlugin(config: MyPluginConfig): PluginInterface {
  return {
    name: 'my-plugin',
    version: '1.0.0',
    
    navigation: [
      {
        path: '/my-plugin',
        name: config.title,
        icon: '🔌',
        section: 'custom'
      }
    ],
    
    routes: [
      {
        path: '/my-plugin',
        element: <PluginPage color={config.color} />
      }
    ]
  };
}

export * from './types';
```

### Step 5: Build & Publish

```bash
# Build
npm run build

# Publish
npm publish
```

## Plugin API

### PluginInterface

```typescript
interface PluginInterface {
  name: string;                    // Plugin identifier
  version: string;                 // Semver version
  navigation: NavigationItem[];    // Navigation entries
  routes: Route[];                 // React Router routes
  theme?: Theme;                   // Optional custom theme
}
```

### NavigationItem

```typescript
interface NavigationItem {
  path: string;           // Route path (/my-plugin)
  name: string;           // Display name (My Plugin)
  icon: string;           // Icon (emoji or icon class)
  section: 'main' | 'custom' | 'ai' | 'admin';
  requiresAuth?: boolean; // Requires authentication (default: true)
}
```

### Route

```typescript
interface Route {
  path: string;               // Route path
  element: React.ReactElement; // Page component
  requiresAuth?: boolean;     // Requires authentication
}
```

### Navigation Merging

Navigation items are merged into client's navigation structure:

```typescript
// Plugin navigation
{ section: 'custom', path: '/plugin', name: 'Plugin' }

// Merged into client's libraryConfig
navigation: {
  add: {
    custom: [
      ...pluginNavigation,
      // Other custom nav items
    ]
  }
}
```

### Route Registration

Routes are added to client's routing:

```typescript
// App.tsx
import { myPlugin } from './config/libraryConfig';

<Routes>
  {myPlugin.routes.map(route => (
    <Route key={route.path} path={route.path} element={route.element} />
  ))}
</Routes>
```

## Example Plugins

### hello-world-plugin

**Purpose**: Demo plugin showing basic structure

**Features**:
- Single page component
- Custom welcome message
- Configurable icon and title

**Usage**:
```typescript
import { createHelloWorldPlugin } from 'hello-world-plugin';

const plugin = createHelloWorldPlugin({
  pageTitle: 'Hello',
  navigationIcon: '👋',
  navigationSection: 'custom',
  requiresAuth: false,
  welcomeMessage: 'Welcome!'
});
```

### temp-agents-plugin

**Purpose**: Temporary agent management

**Features**:
- Create temporary agents
- Auto-expiration
- Management UI

**Usage**:
```typescript
import { createTempAgentsPlugin } from 'temp-agents-plugin';

const plugin = createTempAgentsPlugin({
  defaultExpiration: 3600, // 1 hour
  maxAgents: 10
});
```

### holiday-indexing-plugin

**Purpose**: Holiday-specific content indexing

**Features**:
- Holiday detection
- Custom indexing logic
- Seasonal themes

**Usage**:
```typescript
import { createHolidayIndexingPlugin } from 'holiday-indexing-plugin';

const plugin = createHolidayIndexingPlugin({
  holidays: ['christmas', 'new-year'],
  indexInterval: 86400 // Daily
});
```

## Publishing & Distribution

### npm Registry

**Public**:
```bash
npm publish
```

**Private** (scoped):
```bash
npm publish --access restricted
```

### Internal Registry

For private organizational use:

```bash
# Configure registry
npm config set registry https://npm.your-company.com

# Publish
npm publish
```

### Git Repository

Direct installation from Git:

```bash
npm install github:your-org/my-plugin
```

### Local Development

Test plugin locally before publishing:

```bash
# In plugin directory
npm link

# In client project
npm link my-plugin
```

## Best Practices

1. **Peer dependencies**: Declare React and base library as peers
2. **TypeScript**: Use TypeScript for type safety
3. **Configuration**: Make plugins configurable
4. **Namespacing**: Prefix routes to avoid conflicts
5. **Documentation**: Include comprehensive README
6. **Versioning**: Follow semantic versioning
7. **Testing**: Write unit tests
8. **Bundle size**: Keep plugins lightweight

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| "Module not found" | Plugin not installed | `npm install plugin-name` |
| Type errors | Incorrect types | Check `PluginInterface` definition |
| Routes not working | Routes not added | Add plugin routes to App.tsx |
| Navigation missing | Not added to config | Add to libraryConfig navigation |
| Peer dependency conflict | Version mismatch | Update plugin or base library |

## See Also

- [Client Project Setup](client-setup.md) — Creating clients
- [Frontend Architecture](../architecture/frontend.md) — Base library structure
