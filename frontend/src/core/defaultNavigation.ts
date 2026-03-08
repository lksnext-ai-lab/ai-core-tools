import type { NavigationConfig } from './types';

export const defaultNavigation: NavigationConfig = {
  // Sidebar navigation
  mainFeatures: [
    {
      path: '/home',
      name: 'Home',
      icon: '🏠',
      section: 'mainFeatures'
    },
    {
      path: '/marketplace',
      name: 'Marketplace',
      icon: '🏪',
      section: 'mainFeatures'
    }
  ],
  // App-specific horizontal navigation (when inside an app)
  appNavigation: [
    {
      path: '/apps/:appId',
      name: 'Dashboard',
      icon: '📊',
      section: 'appNavigation'
    },
    {
      path: '/apps/:appId/agents',
      name: 'Agents',
      icon: '🤖',
      section: 'appNavigation'
    },
    {
      path: '/apps/:appId/silos',
      name: 'Silos',
      icon: '🗄️',
      section: 'appNavigation'
    },
    {
      path: '/apps/:appId/repositories',
      name: 'Repositories',
      icon: '📁',
      section: 'appNavigation'
    },
    {
      path: '/apps/:appId/domains',
      name: 'Domains',
      icon: '🌐',
      section: 'appNavigation'
    },
    {
      path: '/apps/:appId/mcp-servers',
      name: 'MCP Servers',
      icon: '🔌',
      section: 'appNavigation'
    },
    {
      path: '/apps/:appId/skills',
      name: 'Skills',
      icon: '🎯',
      section: 'appNavigation'
    },
    {
      path: '/apps/:appId/settings',
      name: 'App Settings',
      icon: '⚙️',
      section: 'appNavigation'
    }
  ],
  // Administration section
  admin: [
    {
      path: '/apps',
      name: 'My Apps',
      icon: '📱',
      section: 'admin'
    },
    {
      path: '/admin/users',
      name: 'Users',
      icon: '👥',
      section: 'admin',
      adminOnly: true
    },
    {
      path: '/admin/stats',
      name: 'Statistics',
      icon: '📊',
      section: 'admin',
      adminOnly: true
    },
    {
      path: '/admin/settings',
      name: 'Settings',
      icon: '⚙️',
      section: 'admin',
      adminOnly: true
    },
    {
      path: '/about',
      name: 'About',
      icon: 'ℹ️',
      section: 'admin'
    }
  ]
};
