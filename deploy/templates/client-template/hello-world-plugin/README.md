# Hello World Plugin

A sample plugin demonstrating the AI-Core-Tools plugin architecture. This plugin shows how to create custom pages for both regular users and administrators.

## Features

- **Custom Page**: Interactive Hello World page with counter, real-time clock, and user input
- **Admin Page**: Administrative interface with statistics, settings, and management tools
- **Plugin Architecture**: Demonstrates proper plugin structure and configuration
- **TypeScript Support**: Fully typed with comprehensive interfaces
- **Responsive Design**: Mobile-friendly UI with Tailwind CSS

## Installation

```bash
npm install @lksnext/hello-world-plugin
```

## Usage

### Basic Usage

```typescript
import { createHelloWorldPlugin } from '@lksnext/hello-world-plugin';
import { libraryConfig } from './config/libraryConfig';

// Create the hello world plugin
const helloWorldPlugin = createHelloWorldPlugin({
  pageTitle: 'Hello World',
  navigationIcon: '👋',
  navigationSection: 'custom',
  requiresAuth: false,
  welcomeMessage: 'Welcome to our Hello World plugin!'
});

// Add to your library configuration
export const libraryConfig: LibraryConfig = {
  // ... other config
  navigation: {
    add: {
      custom: [
        ...helloWorldPlugin.navigation
      ],
      admin: [
        ...helloWorldPlugin.navigation.filter(item => item.section === 'admin')
      ]
    }
  }
};
```

### Advanced Configuration

```typescript
const helloWorldPlugin = createHelloWorldPlugin({
  // Custom page settings
  pageTitle: 'My Custom Page',
  navigationIcon: '🌟',
  navigationSection: 'custom',
  requiresAuth: true,
  customPath: '/my-custom-page',
  welcomeMessage: 'Welcome to my custom implementation!',
  
  // Admin page settings
  adminPageTitle: 'Plugin Administration',
  adminNavigationIcon: '⚙️',
  adminPath: '/admin/plugin-settings',
  showAdminPage: true
});
```

## Configuration Options

### HelloWorldPluginConfig

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `pageTitle` | `string` | `'Hello World'` | Title for the main page |
| `navigationIcon` | `string` | `'👋'` | Icon for navigation menu |
| `navigationSection` | `'main' \| 'tools' \| 'custom'` | `'custom'` | Navigation section |
| `requiresAuth` | `boolean` | `false` | Whether page requires authentication |
| `customPath` | `string` | `'/hello-world'` | Custom URL path |
| `welcomeMessage` | `string` | `'Welcome to the Hello World Plugin!'` | Welcome message |
| `adminPageTitle` | `string` | `'Hello World Admin'` | Admin page title |
| `adminNavigationIcon` | `string` | `'⚙️'` | Admin navigation icon |
| `adminPath` | `string` | `'/admin/hello-world'` | Admin page path |
| `showAdminPage` | `boolean` | `true` | Whether to show admin page |

## Components

### HelloWorldPage

The main user-facing page with interactive features:

- **Interactive Counter**: Click to increment, reset functionality
- **Real-time Clock**: Updates every second
- **Personal Greeting**: User input with dynamic greeting
- **Plugin Information**: Shows plugin status and metadata

### HelloWorldAdminPage

Administrative interface with:

- **Statistics Dashboard**: Visit counts, session times, active users
- **Settings Panel**: Toggle notifications, auto-refresh, theme, language
- **Admin Actions**: Reset stats, export data, refresh page
- **Plugin Status**: Real-time plugin health and information

## Plugin Architecture

This plugin demonstrates the standard AI-Core-Tools plugin structure:

```
src/
├── config/
│   └── pluginConfig.ts      # Plugin configuration and factory
├── pages/
│   ├── HelloWorldPage.tsx   # Main user page
│   └── HelloWorldAdminPage.tsx # Admin page
├── components/              # Reusable components (if any)
├── types/                   # TypeScript type definitions
└── index.ts                 # Main export file
```

## Development

### Building the Plugin

```bash
npm run build
```

### Development Mode

```bash
npm run dev
```

### Cleaning Build

```bash
npm run clean
```

## Integration with AI-Core-Tools

This plugin integrates seamlessly with the AI-Core-Tools framework by:

1. **Extending Navigation**: Adds custom and admin navigation items
2. **Adding Routes**: Registers page routes with the router
3. **Theme Integration**: Uses framework's theming system
4. **Authentication**: Respects framework's auth requirements
5. **Type Safety**: Provides full TypeScript support

## Examples

### Minimal Integration

```typescript
import { createHelloWorldPlugin } from '@lksnext/hello-world-plugin';

const helloWorldPlugin = createHelloWorldPlugin();

// Add to navigation
navigation: {
  add: {
    custom: [...helloWorldPlugin.navigation]
  }
}
```

### Full Integration with Multiple Plugins

```typescript
import { createHelloWorldPlugin } from '@lksnext/hello-world-plugin';
import { createAgentsPlugin } from '@lksnext/agents-plugin';

const helloWorldPlugin = createHelloWorldPlugin({
  pageTitle: 'Welcome Page',
  navigationSection: 'custom'
});

const agentsPlugin = createAgentsPlugin({
  pageTitle: 'AI Agents',
  navigationSection: 'tools'
});

export const libraryConfig: LibraryConfig = {
  // ... other config
  navigation: {
    add: {
      custom: [...helloWorldPlugin.navigation],
      tools: [...agentsPlugin.navigation]
    }
  }
};
```

## License

MIT License - see LICENSE file for details.

## Contributing

This is a sample plugin for demonstration purposes. For the main AI-Core-Tools framework, please refer to the main repository.
