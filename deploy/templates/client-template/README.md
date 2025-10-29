# AI-Core-Tools Client Template

This template demonstrates how to create a client project using the **new extensible AI-Core-Tools library**.

## 🚀 What's New in the Extensible Library

### Modular Components
- **Header**: Customizable header with logo, title, and user menu
- **Sidebar**: Navigation sidebar with configurable menu items
- **Footer**: Configurable footer with version info and custom content
- **Layout**: Orchestrates all layout components
- **ThemeSelector**: Theme switching component

### Simplified Configuration
- **LibraryConfig**: Much easier configuration interface
- **Theme System**: Multiple themes, custom CSS, easy switching
- **Route Management**: Add custom routes with `ExtraRoute`
- **Component Props**: Deep customization options for all components

### Enhanced Features
- **Authentication**: OIDC and session auth support
- **Responsive Design**: Mobile-first responsive layout
- **TypeScript**: Full TypeScript support with type definitions
- **Custom CSS**: Support for custom CSS variables and styles

## 📁 Template Structure

```
client-template/
├── frontend/
│   ├── src/
│   │   ├── config/
│   │   │   └── libraryConfig.ts      # Main configuration file
│   │   ├── pages/
│   │   │   ├── ExtensibilityDemo.tsx # Demo page showcasing features
│   │   │   ├── CustomPage.tsx        # Example custom page
│   │   │   ├── CustomFeature.tsx     # Example custom feature
│   │   │   └── CustomHomePage.tsx    # Custom home page
│   │   ├── themes/
│   │   │   └── customTheme.ts        # Custom theme definition
│   │   ├── components/
│   │   │   └── ui/
│   │   │       └── ClientCard.tsx    # Example custom component
│   │   └── App.tsx                   # Main app using ExtensibleBaseApp
│   ├── public/
│   │   ├── mattin-small.png          # Default Mattin logo (can be replaced)
│   │   ├── favicon.ico               # Default favicon (can be replaced)
│   │   └── README.md                 # Assets documentation
│   ├── package.json                  # Dependencies
│   ├── vite.config.ts               # Build configuration
│   └── CLIENT_SETUP_GUIDE.md        # Detailed setup guide
├── hello-world-plugin/              # 🔌 Sample plugin demonstrating plugin architecture
│   ├── src/
│   │   ├── config/
│   │   │   └── pluginConfig.ts      # Plugin configuration and factory
│   │   ├── pages/
│   │   │   ├── HelloWorldPage.tsx   # Custom page component
│   │   │   └── HelloWorldAdminPage.tsx # Admin page component
│   │   └── index.ts                 # Main exports
│   ├── package.json                  # Plugin dependencies
│   ├── tsconfig.json                # TypeScript configuration
│   └── README.md                    # Plugin documentation
├── PLUGIN_EXAMPLES.md               # 📖 Guide for creating and using plugins
└── README.md                        # This file
```

## 🎯 Key Features Demonstrated

### 1. ExtensibleBaseApp Usage
```typescript
import { ExtensibleBaseApp } from '@lksnext/ai-core-tools-base';
import { libraryConfig } from './config/libraryConfig';

function App() {
  return (
    <ExtensibleBaseApp 
      config={libraryConfig}
      extraRoutes={extraRoutes}
    />
  );
}
```

### 2. Modular Component Usage
```typescript
import { 
  Header, 
  Sidebar, 
  Footer, 
  Layout, 
  ThemeSelector,
  useTheme 
} from '@lksnext/ai-core-tools-base';

// Use individual components in your custom layouts
```

### 3. Theme System
```typescript
// Multiple themes with easy switching
themeProps: {
  defaultTheme: 'client-custom',
  customThemes: {
    'client-custom': customTheme,
    'corporate': corporateTheme
  },
  showThemeSelector: true
}
```

### 4. Route Extensibility
```typescript
const extraRoutes: ExtraRoute[] = [
  {
    path: '/extensibility-demo',
    element: <ExtensibilityDemo />,
    name: 'Extensibility Demo',
    protected: true
  }
];
```

### 5. Plugin Architecture
```typescript
// In config/libraryConfig.ts
import { createHelloWorldPlugin } from '../hello-world-plugin';

// Create plugin instance with custom configuration
const helloWorldPlugin = createHelloWorldPlugin({
  pageTitle: 'Hello World Demo',
  navigationIcon: '👋',
  navigationSection: 'custom',
  requiresAuth: false
});

// Add plugin navigation and routes to your config - all in one place!
export const libraryConfig: LibraryConfig = {
  navigation: {
    add: {
      custom: [...helloWorldPlugin.navigation],
      admin: [...helloWorldPlugin.navigation.filter(item => item.section === 'admin')]
    }
  },
  routes: [
    ...helloWorldPlugin.routes  // Plugin routes are added here
  ]
};
```

## 🛠️ Getting Started

1. **Create a new client project:**
   ```bash
   ./deploy/scripts/create-client-project.sh my-client
   ```

2. **Navigate to your client directory:**
   ```bash
   cd clients/my-client
   ```

3. **Install dependencies:**
   ```bash
   npm install
   ```

4. **Configure your client:**
   - Update `src/config/libraryConfig.ts` with your details
   - Replace `public/mattin-small.png` with your logo (optional)
   - Replace `public/favicon.ico` with your favicon (optional)

5. **Start development:**
   ```bash
   npm run dev
   ```

6. **Visit the extensibility demo:**
   - Go to `http://localhost:3000/extensibility-demo`
   - See all the new features in action!

## 📚 Documentation

- **CLIENT_SETUP_GUIDE.md**: Comprehensive setup and customization guide
- **ExtensibilityDemo.tsx**: Interactive demo of all new features
- **libraryConfig.ts**: Example configuration with all options

## 🎨 Customization Examples

### Custom Theme
```typescript
export const customTheme: ThemeConfig = {
  name: 'client-custom',
  colors: {
    primary: '#10b981',    // Your brand colors
    secondary: '#8b5cf6',
    accent: '#f59e0b',
    background: '#f9fafb',
    surface: '#ffffff',
    text: '#111827'
  },
  customStyles: `
    .client-button {
      background: var(--client-primary);
      transition: all 0.2s ease;
    }
  `
};
```

### Custom Layout
```typescript
import { Header, Sidebar, Footer, useTheme } from '@lksnext/ai-core-tools-base';

const CustomLayout = () => {
  const { theme } = useTheme();
  
  return (
    <div className="min-h-screen flex flex-col">
      <Header title="My App" />
      <div className="flex flex-1">
        <Sidebar />
        <main className="flex-1 p-6">
          {/* Your content */}
        </main>
      </div>
      <Footer />
    </div>
  );
};
```

## 🔧 Available Scripts

- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm run preview` - Preview production build
- `npm run lint` - Run ESLint
- `npm run lint:fix` - Fix ESLint issues

## 🚀 Next Steps

1. **Explore the ExtensibilityDemo page** to see all features
2. **Customize your theme** in `src/themes/customTheme.ts`
3. **Add your custom pages** in `src/pages/`
4. **Configure navigation** in `libraryConfig.ts`
5. **Deploy your client** using your preferred hosting service

## 📞 Support

For questions or issues:
- Check the CLIENT_SETUP_GUIDE.md for detailed instructions
- Review the ExtensibilityDemo.tsx for code examples
- Refer to the main AI-Core-Tools documentation

---

**Happy coding! 🎉**