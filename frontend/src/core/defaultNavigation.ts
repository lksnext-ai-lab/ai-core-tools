import type { NavigationConfig } from './types';

export const defaultNavigation: NavigationConfig = {
  mainFeatures: [
    {
      path: '/apps/:appId',
      name: 'Dashboard',
      icon: '🏠',
      section: 'mainFeatures'
    },
    {
      path: '/apps/:appId/agents',
      name: 'Agents',
      icon: '🤖',
      section: 'mainFeatures'
    },
    {
      path: '/apps/:appId/silos',
      name: 'Silos',
      icon: '🗄️',
      section: 'mainFeatures'
    },
    {
      path: '/apps/:appId/repositories',
      name: 'Repositories',
      icon: '📁',
      section: 'mainFeatures'
    },
    {
      path: '/apps/:appId/domains',
      name: 'Domains',
      icon: '🌐',
      section: 'mainFeatures'
    }
  ],
  settings: [
    {
      path: '/apps/:appId/settings',
      name: 'App Settings',
      icon: '⚙️',
      section: 'settings'
    }
  ],
  admin: [
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
    }
  ]
};
