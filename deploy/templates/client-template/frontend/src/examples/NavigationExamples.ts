import type { ExtensibleNavigationConfig } from '@lksnext/ai-core-tools-base';

/**
 * Examples of how to use the new extensible navigation system
 */

// Example 1: Simple addition - just add custom routes
export const simpleAddition: ExtensibleNavigationConfig = {
  add: {
    custom: [
      {
        path: '/my-feature',
        name: 'My Feature',
        icon: '⭐',
        section: 'custom'
      }
    ]
  }
};

// Example 2: Override existing navigation items
export const withOverrides: ExtensibleNavigationConfig = {
  add: {
    custom: [
      {
        path: '/dashboard',
        name: 'Custom Dashboard',
        icon: '📊',
        section: 'mainFeatures'
      }
    ]
  },
  override: [
    {
      path: '/about',
      name: 'About My Company',
      icon: '🏢'
    },
    {
      path: '/admin/users',
      name: 'Team Management',
      icon: '👥'
    }
  ]
};

// Example 3: Hide certain features
export const withRemovals: ExtensibleNavigationConfig = {
  add: {
    custom: [
      {
        path: '/analytics',
        name: 'Analytics',
        icon: '📈',
        section: 'custom'
      }
    ]
  },
  remove: [
    '/admin/stats',  // Hide statistics
    '/about'         // Hide about page
  ]
};

// Example 4: Complex customization
export const complexCustomization: ExtensibleNavigationConfig = {
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
      },
      {
        path: '/integrations',
        name: 'Integrations',
        icon: '🔗',
        section: 'custom'
      }
    ]
  },
  override: [
    {
      path: '/',
      name: 'Home Dashboard',
      icon: '🏠'
    },
    {
      path: '/apps',
      name: 'My Projects',
      icon: '📱'
    },
    {
      path: '/admin/users',
      name: 'User Management',
      icon: '👥',
      adminOnly: true
    }
  ],
  remove: [
    '/admin/stats'  // Hide statistics page
  ]
};

// Example 5: Minimal configuration - just add one custom route
export const minimalConfig: ExtensibleNavigationConfig = {
  add: {
    custom: [
      {
        path: '/help',
        name: 'Help & Support',
        icon: '❓',
        section: 'custom'
      }
    ]
  }
};

// Example 6: Hide admin features for non-admin users
export const hideAdminFeatures: ExtensibleNavigationConfig = {
  add: {
    custom: [
      {
        path: '/profile',
        name: 'My Profile',
        icon: '👤',
        section: 'custom'
      }
    ]
  },
  remove: [
    '/admin/users',
    '/admin/stats'
  ]
};

// Example 7: Add to different sections
export const multiSectionAddition: ExtensibleNavigationConfig = {
  add: {
    mainFeatures: [
      {
        path: '/quick-start',
        name: 'Quick Start',
        icon: '🚀',
        section: 'mainFeatures'
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
    ],
    custom: [
      {
        path: '/documentation',
        name: 'Documentation',
        icon: '📚',
        section: 'custom'
      }
    ]
  }
};
