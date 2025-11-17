// Example usage of the new modular AI-Core-Tools library
import React from 'react';
import { 
  ExtensibleBaseApp, 
  Header, 
  Sidebar, 
  Footer, 
  Layout, 
  ThemeSelector,
  AuthProvider,
  ThemeProvider,
  type LibraryConfig,
  type AuthProps,
  type ExtraRoute,
  baseTheme
} from '@lksnext/ai-core-tools-base';

// Example 1: Using the new ExtensibleBaseApp with simplified configuration
const MyApp: React.FC = () => {
  const config: LibraryConfig = {
    name: "My Custom AI App",
  logo: "/mattin-small.png",
  favicon: "/favicon.ico",
    
    // Theme configuration
    themeProps: {
      defaultTheme: 'custom',
      customThemes: {
        custom: {
          name: 'Custom Theme',
          colors: {
            primary: '#3B82F6',
            secondary: '#1E40AF',
            accent: '#F59E0B',
            background: '#F9FAFB',
            surface: '#FFFFFF',
            text: '#111827'
          },
          logo: '/mattin-small.png',
          favicon: '/favicon.ico'
        }
      },
      showThemeSelector: true
    },
    
    // Header customization
    headerProps: {
      title: "My Custom Header",
      className: "bg-blue-600 text-white"
    },
    
    // Footer customization
    footerProps: {
      copyright: "© 2024 My Company",
      showVersion: true
    },
    
    // Navigation configuration
    navigationConfig: {
      mainFeatures: [
        { path: '/', name: 'Home', icon: '🏠' },
        { path: '/dashboard', name: 'Dashboard', icon: '📊' }
      ],
      custom: [
        { path: '/custom-page', name: 'Custom Page', icon: '⭐' }
      ]
    },
    
    // Authentication configuration
    authProps: {
      enabled: true,
      oidc: {
        authority: 'https://my-auth-provider.com',
        client_id: 'my-client-id',
        callbackPath: '/callback'
      }
    },
    
    // Feature configuration
    features: {
      showSidebar: true,
      showHeader: true,
      showFooter: true,
      showThemeSelector: true
    }
  };

  const extraRoutes: ExtraRoute[] = [
    {
      path: '/custom-page',
      element: <div className="p-8"><h1>Custom Page</h1></div>,
      name: 'Custom Page',
      protected: true
    }
  ];

  return (
    <ExtensibleBaseApp 
      config={config}
      extraRoutes={extraRoutes}
    />
  );
};

// Example 2: Using individual components for custom layouts
const CustomLayoutApp: React.FC = () => {
  const customTheme = {
    ...baseTheme,
    name: 'Custom Theme',
    colors: {
      ...baseTheme.colors,
      primary: '#10B981',
      secondary: '#059669'
    }
  };

  const authConfig: AuthProps = {
    enabled: true,
    oidc: {
      authority: 'https://my-auth-provider.com',
      client_id: 'my-client-id'
    }
  };

  return (
    <ThemeProvider theme={customTheme}>
      <AuthProvider config={authConfig}>
        <Layout
          headerProps={{
            children: (
              <div className="flex items-center space-x-4">
                <h1 className="text-xl font-bold">My Custom App</h1>
                <ThemeSelector 
                  themes={{ custom: customTheme }}
                  showLabel={false}
                />
              </div>
            )
          }}
          sidebarProps={{
            children: (
              <div className="p-4">
                <h3 className="font-semibold mb-2">Custom Sidebar</h3>
                <ul className="space-y-2">
                  <li><a href="/page1" className="text-blue-600 hover:underline">Page 1</a></li>
                  <li><a href="/page2" className="text-blue-600 hover:underline">Page 2</a></li>
                </ul>
              </div>
            )
          }}
          footerProps={{
            children: (
              <div className="text-center py-4 text-gray-600">
                <p>Custom Footer Content</p>
              </div>
            )
          }}
        >
          <div className="p-8">
            <h1 className="text-3xl font-bold mb-4">Welcome to My Custom App</h1>
            <p className="text-gray-600">
              This demonstrates how to use individual components from the AI-Core-Tools library
              to create a completely custom layout.
            </p>
          </div>
        </Layout>
      </AuthProvider>
    </ThemeProvider>
  );
};

// Example 3: Minimal usage with just the base components
const MinimalApp: React.FC = () => {
  return (
    <Layout
      showSidebar={false}
      headerProps={{
        children: <h1 className="text-xl font-bold">Minimal App</h1>
      }}
    >
      <div className="p-8">
        <h2 className="text-2xl font-semibold mb-4">Minimal Setup</h2>
        <p>This shows the most basic usage of the library components.</p>
      </div>
    </Layout>
  );
};

export { MyApp, CustomLayoutApp, MinimalApp };
