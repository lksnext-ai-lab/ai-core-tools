import type { LibraryConfig } from '@lksnext/ai-core-tools-base';
import { customTheme } from '../themes/customTheme';
import CustomHomePage from '../pages/CustomHomePage';

export const libraryConfig: LibraryConfig = {
  // Basic configuration
  name: 'CLIENT_NAME_HERE',
  logo: '/mattin-small.png',
  favicon: '/favicon.ico',
  homePage: CustomHomePage,
  
  // Theme configuration
  themeProps: {
    defaultTheme: 'client-custom',
    customThemes: {
      'client-custom': customTheme,
      'corporate': {
        name: 'corporate',
        colors: {
          primary: '#1e40af',    // blue-800
          secondary: '#dc2626',  // red-600
          accent: '#059669',     // emerald-600
          background: '#f8fafc', // slate-50
          surface: '#ffffff',    // white
          text: '#0f172a'        // slate-900
        }
      }
    },
    showThemeSelector: true
  },
  
  // Header configuration
  headerProps: {
    title: 'CLIENT_HEADER_TITLE',  // This will show in the header
    // logoUrl: '/mattin-small.png',  // Uses main logo by default
    className: 'bg-white shadow-sm border-b'
  },
  
  // Sidebar configuration (optional - will use headerProps if not specified)
  sidebarProps: {
    title: 'CLIENT_HEADER_TITLE',  // This will show in the sidebar top-left
    // logoUrl: '/mattin-small.png',  // Uses main logo by default
    className: 'bg-white shadow-sm'
  },
  
  // Footer configuration
  footerProps: {
    copyright: '© 2024 CLIENT_COMPANY_NAME. All rights reserved.',
    showVersion: true,
    className: 'bg-gray-50 border-t'
  },
  
  // Layout configuration
  layoutProps: {
    mainClassName: 'min-h-screen bg-gray-50',
    className: 'flex flex-col'
  },
  
  // Navigation configuration
  navigationProps: {
    showIcons: true,
    className: 'bg-white shadow-sm'
  },
  
  // Extensible navigation configuration (much simpler!)
  navigation: {
    // Add custom navigation items
    add: {
      custom: [
        {
          path: '/extensibility-demo',
          name: 'Extensibility Demo',
          icon: '🚀',
          section: 'demo'
        },
        {
          path: '/theme-customization',
          name: 'Theme Customization',
          icon: '🎨',
          section: 'demo'
        },
        {
          path: '/component-usage',
          name: 'Component Usage',
          icon: '🧩',
          section: 'demo'
        },
        {
          path: '/interactive-demo',
          name: 'Interactive Builder',
          icon: '🛠️',
          section: 'demo'
        },
        {
          path: '/custom-page',
          name: 'Custom Page',
          icon: '📄',
          section: 'custom'
        },
        {
          path: '/custom-feature',
          name: 'Custom Feature',
          icon: '⭐',
          section: 'custom'
        }
      ]
    },
    // Override existing navigation items (optional)
    override: [
      {
        path: '/',  // Override the home page
        name: 'CLIENT_NAME_HERE Dashboard',
        icon: '🏠'
      },
      {
        path: '/about',
        name: 'About CLIENT_NAME_HERE',
        icon: 'ℹ️'
      }
    ],
    // Remove navigation items (optional)
    // remove: ['/admin/stats'] // Hide statistics if not needed
  },
  
  // Authentication configuration
  authProps: {
    enabled: true,
    oidc: {
      authority: 'https://your-oidc-provider.com',
      client_id: 'CLIENT_ID_HERE',
      callbackPath: '/callback',
      scope: 'openid profile email'
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
