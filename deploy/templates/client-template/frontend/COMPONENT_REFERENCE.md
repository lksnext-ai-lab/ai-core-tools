# AI-Core-Tools Library - Component Reference

This document provides a comprehensive reference for all components available in the `@lksnext/ai-core-tools-base` library.

## Table of Contents

- [Core Components](#core-components)
- [Layout Components](#layout-components)
- [Theme System](#theme-system)
- [Authentication](#authentication)
- [Configuration](#configuration)
- [Examples](#examples)

## Core Components

### ExtensibleBaseApp

The main application component that provides a complete, extensible application structure.

```typescript
import { ExtensibleBaseApp } from '@lksnext/ai-core-tools-base';
import type { LibraryConfig, ExtraRoute } from '@lksnext/ai-core-tools-base';

const config: LibraryConfig = {
  name: 'My App',
  themeProps: { defaultTheme: 'custom' },
  // ... other configuration
};

const extraRoutes: ExtraRoute[] = [
  {
    path: '/custom-page',
    element: <CustomPage />,
    name: 'Custom Page',
    protected: true
  }
];

<ExtensibleBaseApp 
  config={config}
  extraRoutes={extraRoutes}
/>
```

**Props:**
- `config: LibraryConfig` - Application configuration
- `extraRoutes?: ExtraRoute[]` - Additional routes to add

## Layout Components

### Header

Configurable header component with logo, title, and custom content support.

```typescript
import { Header } from '@lksnext/ai-core-tools-base';

<Header
  title="My App"
  logoUrl="/logo.png"
  className="bg-blue-600 text-white"
  children={
    <div className="flex items-center space-x-4">
      <ThemeSelector />
      <button>Action</button>
    </div>
  }
/>
```

**Props:**
- `title?: string` - Header title
- `logoUrl?: string` - Logo image URL
- `className?: string` - Additional CSS classes
- `children?: React.ReactNode` - Custom header content

### Sidebar

Navigation sidebar component with customizable content.

```typescript
import { Sidebar } from '@lksnext/ai-core-tools-base';

<Sidebar
  children={
    <div className="p-4">
      <h4 className="font-semibold mb-4">Navigation</h4>
      <nav className="space-y-2">
        <a href="/dashboard">Dashboard</a>
        <a href="/settings">Settings</a>
      </nav>
    </div>
  }
/>
```

**Props:**
- `children?: React.ReactNode` - Sidebar content
- `className?: string` - Additional CSS classes

### Footer

Configurable footer component with copyright and custom content.

```typescript
import { Footer } from '@lksnext/ai-core-tools-base';

<Footer
  copyright="© 2024 My Company"
  showVersion={true}
  children={
    <div className="flex justify-between">
      <div>Links</div>
      <div>Version</div>
    </div>
  }
/>
```

**Props:**
- `copyright?: string` - Copyright text
- `showVersion?: boolean` - Show version information
- `className?: string` - Additional CSS classes
- `children?: React.ReactNode` - Custom footer content

### Layout

Complete layout component that combines header, sidebar, and footer.

```typescript
import { Layout } from '@lksnext/ai-core-tools-base';

<Layout
  headerProps={{
    title: "My App",
    logoUrl: "/logo.png"
  }}
  sidebarProps={{
    children: <NavigationMenu />
  }}
  footerProps={{
    copyright: "© 2024 My Company"
  }}
>
  <div>Your content here</div>
</Layout>
```

**Props:**
- `headerProps?: HeaderProps` - Header configuration
- `sidebarProps?: SidebarProps` - Sidebar configuration
- `footerProps?: FooterProps` - Footer configuration
- `children?: React.ReactNode` - Main content
- `className?: string` - Additional CSS classes

## Theme System

### ThemeProvider

Provides theme context to the application.

```typescript
import { ThemeProvider } from '@lksnext/ai-core-tools-base';

<ThemeProvider theme={customTheme}>
  <App />
</ThemeProvider>
```

**Props:**
- `theme: ThemeConfig` - Theme configuration
- `children: React.ReactNode` - Child components

### useTheme Hook

Access theme information and controls in components.

```typescript
import { useTheme } from '@lksnext/ai-core-tools-base';

const MyComponent = () => {
  const { theme, switchTheme } = useTheme();
  
  return (
    <div style={{ color: theme.colors?.text }}>
      <button 
        onClick={() => switchTheme('dark')}
        style={{ backgroundColor: theme.colors?.primary }}
      >
        Switch Theme
      </button>
    </div>
  );
};
```

**Returns:**
- `theme: ThemeConfig` - Current theme configuration
- `switchTheme: (themeName: string) => void` - Switch to a different theme

### ThemeSelector

Interactive theme selection component.

```typescript
import { ThemeSelector } from '@lksnext/ai-core-tools-base';

<ThemeSelector 
  themes={{ custom: customTheme }}
  showLabel={false}
/>
```

**Props:**
- `themes?: Record<string, ThemeConfig>` - Available themes
- `showLabel?: boolean` - Show theme name label
- `className?: string` - Additional CSS classes

## Authentication

### AuthProvider

Provides authentication context to the application.

```typescript
import { AuthProvider } from '@lksnext/ai-core-tools-base';

<AuthProvider config={authConfig}>
  <App />
</AuthProvider>
```

**Props:**
- `config: AuthProps` - Authentication configuration
- `children: React.ReactNode` - Child components

### useAuth Hook

Access authentication state and methods.

```typescript
import { useAuth } from '@lksnext/ai-core-tools-base';

const MyComponent = () => {
  const { user, isAuthenticated, login, logout } = useAuth();
  
  if (!isAuthenticated) {
    return <button onClick={login}>Login</button>;
  }
  
  return (
    <div>
      <p>Welcome, {user?.name}!</p>
      <button onClick={logout}>Logout</button>
    </div>
  );
};
```

**Returns:**
- `user: User | null` - Current user information
- `isAuthenticated: boolean` - Authentication status
- `login: () => void` - Login function
- `logout: () => void` - Logout function

## Configuration

### LibraryConfig Interface

Main configuration interface for the library.

```typescript
interface LibraryConfig {
  // Basic configuration
  name: string;
  logo?: string;
  favicon?: string;
  
  // Theme configuration
  themeProps?: {
    defaultTheme?: string;
    customThemes?: Record<string, ThemeConfig>;
    showThemeSelector?: boolean;
  };
  
  // Component configuration
  headerProps?: {
    title?: string;
    logoUrl?: string;
    className?: string;
    children?: React.ReactNode;
  };
  
  footerProps?: {
    copyright?: string;
    showVersion?: boolean;
    className?: string;
    children?: React.ReactNode;
  };
  
  // Feature configuration
  features?: {
    showHeader?: boolean;
    showSidebar?: boolean;
    showFooter?: boolean;
    showThemeSelector?: boolean;
  };
  
  // Authentication configuration
  authProps?: {
    enabled?: boolean;
    oidc?: OIDCConfig;
  };
  
  // API configuration
  apiConfig?: {
    baseUrl?: string;
    timeout?: number;
    retries?: number;
  };
}
```

### ExtraRoute Interface

Interface for adding custom routes to the application.

```typescript
interface ExtraRoute {
  path: string;
  element: React.ReactNode;
  name: string;
  icon?: React.ReactNode;
  protected?: boolean;
}
```

### ThemeConfig Interface

Interface for theme configuration.

```typescript
interface ThemeConfig {
  name: string;
  colors: {
    primary: string;
    secondary: string;
    accent: string;
    background: string;
    surface: string;
    text: string;
  };
  logo?: string;
  favicon?: string;
}
```

## Examples

### Basic Usage

```typescript
import { ExtensibleBaseApp } from '@lksnext/ai-core-tools-base';
import { libraryConfig } from './config/libraryConfig';

function App() {
  return (
    <ExtensibleBaseApp 
      config={libraryConfig}
      extraRoutes={[]}
    />
  );
}
```

### Custom Layout

```typescript
import { 
  Header, 
  Sidebar, 
  Footer, 
  Layout,
  useTheme 
} from '@lksnext/ai-core-tools-base';

const CustomApp = () => {
  const { theme } = useTheme();
  
  return (
    <Layout
      headerProps={{
        title: "Custom App",
        children: <ThemeSelector />
      }}
      sidebarProps={{
        children: <CustomNavigation />
      }}
      footerProps={{
        copyright: "© 2024 Custom Company"
      }}
    >
      <div className="p-6">
        <h1>Welcome to Custom App</h1>
        <p>This is a custom layout using individual components.</p>
      </div>
    </Layout>
  );
};
```

### Theme Customization

```typescript
import { ThemeProvider, useTheme } from '@lksnext/ai-core-tools-base';

const customTheme: ThemeConfig = {
  name: 'custom',
  colors: {
    primary: '#3B82F6',
    secondary: '#1E40AF',
    accent: '#F59E0B',
    background: '#F9FAFB',
    surface: '#FFFFFF',
    text: '#111827'
  }
};

const ThemedApp = () => {
  return (
    <ThemeProvider theme={customTheme}>
      <App />
    </ThemeProvider>
  );
};
```

### Adding Custom Routes

```typescript
import { ExtensibleBaseApp } from '@lksnext/ai-core-tools-base';
import CustomPage from './pages/CustomPage';

const extraRoutes: ExtraRoute[] = [
  {
    path: '/custom-page',
    element: <CustomPage />,
    name: 'Custom Page',
    icon: '⭐',
    protected: true
  },
  {
    path: '/public-page',
    element: <PublicPage />,
    name: 'Public Page',
    protected: false
  }
];

<ExtensibleBaseApp 
  config={config}
  extraRoutes={extraRoutes}
/>
```

## Best Practices

### 1. Theme Integration

Always use the `useTheme` hook to access theme colors:

```typescript
const MyComponent = () => {
  const { theme } = useTheme();
  
  return (
    <div 
      style={{ 
        backgroundColor: theme.colors?.surface,
        color: theme.colors?.text 
      }}
    >
      Content
    </div>
  );
};
```

### 2. Component Composition

Use individual components for maximum flexibility:

```typescript
// Good: Flexible composition
<Layout
  headerProps={{ title: "App" }}
  sidebarProps={{ children: <Nav /> }}
>
  <Content />
</Layout>

// Avoid: Tightly coupled components
<PrebuiltAppWithEverything />
```

### 3. Configuration Management

Keep configuration in separate files:

```typescript
// config/libraryConfig.ts
export const libraryConfig: LibraryConfig = {
  // ... configuration
};

// App.tsx
import { libraryConfig } from './config/libraryConfig';
```

### 4. Type Safety

Always use TypeScript interfaces:

```typescript
import type { LibraryConfig, ExtraRoute } from '@lksnext/ai-core-tools-base';
```

## Troubleshooting

### Common Issues

1. **Theme not applied**: Ensure `ThemeProvider` wraps your app
2. **Components not styled**: Check if CSS is imported
3. **Routes not working**: Verify `ExtraRoute` configuration
4. **Authentication issues**: Check `AuthProvider` configuration

### Getting Help

- Check the [CLIENT_SETUP_GUIDE.md](./CLIENT_SETUP_GUIDE.md) for setup instructions
- Review the example pages in the template
- Check the browser console for error messages
- Ensure all required dependencies are installed

## Migration Guide

### From Old to New System

1. **Replace BaseApp with ExtensibleBaseApp**
2. **Update configuration format to LibraryConfig**
3. **Use individual components instead of monolithic components**
4. **Update theme system to use useTheme hook**
5. **Convert routes to ExtraRoute format**

### Breaking Changes

- `BaseApp` → `ExtensibleBaseApp`
- `ClientConfig` → `LibraryConfig`
- Theme system now uses hooks instead of props
- Navigation configuration simplified
