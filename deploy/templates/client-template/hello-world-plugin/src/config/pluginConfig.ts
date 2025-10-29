import React from 'react';
import type { ExtraRoute } from '@lksnext/ai-core-tools-base';
import { HelloWorldPage } from '../pages/HelloWorldPage';
import { HelloWorldAdminPage } from '../pages/HelloWorldAdminPage';

export interface HelloWorldPluginConfig {
  /**
   * Custom title for the hello world page
   */
  pageTitle?: string;
  
  /**
   * Custom icon for navigation
   */
  navigationIcon?: string;
  
  /**
   * Whether to show in main navigation or custom section
   */
  navigationSection?: 'main' | 'tools' | 'custom' | 'admin';
  
  /**
   * Whether the hello world page requires authentication
   */
  requiresAuth?: boolean;
  
  /**
   * Custom path for the hello world page
   */
  customPath?: string;

  /**
   * Custom title for the admin page
   */
  adminPageTitle?: string;
  
  /**
   * Custom icon for admin navigation
   */
  adminNavigationIcon?: string;
  
  /**
   * Custom path for the admin page
   */
  adminPath?: string;

  /**
   * Whether to show the admin page
   */
  showAdminPage?: boolean;

  /**
   * Custom welcome message
   */
  welcomeMessage?: string;
}

export interface HelloWorldPluginModule {
  /**
   * Navigation items to add to the main app
   */
  navigation: Array<{
    path: string;
    name: string;
    icon: string;
    section: string;
    adminOnly?: boolean;  // Set to true to restrict to admin users only
  }>;
  
  /**
   * Routes to add to the main app
   */
  routes: ExtraRoute[];
  
  /**
   * Plugin metadata
   */
  metadata: {
    name: string;
    version: string;
    description: string;
  };
}

/**
 * Creates a hello world plugin module with the specified configuration
 * This is a sample plugin that demonstrates how to create plugins for the AI-Core-Tools framework
 */
export function createHelloWorldPlugin(config: HelloWorldPluginConfig = {}): HelloWorldPluginModule {
  const {
    pageTitle = 'Hello World',
    navigationIcon = '👋',
    navigationSection = 'custom',
    requiresAuth = false,
    customPath = '/hello-world',
    adminPageTitle = 'Hello World Admin',
    adminNavigationIcon = '⚙️',
    adminPath = '/admin/hello-world',
    showAdminPage = true,
    welcomeMessage = 'Welcome to the Hello World Plugin!'
  } = config;

  const navigation = [
    {
      path: customPath,
      name: pageTitle,
      icon: navigationIcon,
      section: navigationSection
    }
  ];

  const routes = [
    {
      path: customPath,
      element: React.createElement(HelloWorldPage, { welcomeMessage }),
      name: pageTitle,
      protected: requiresAuth
    }
  ];

  // Add admin page if enabled
  if (showAdminPage) {
    navigation.push({
      path: adminPath,
      name: adminPageTitle,
      icon: adminNavigationIcon,
      section: 'admin',
      adminOnly: true  // Only visible to admin users
    });

    routes.push({
      path: adminPath,
      element: React.createElement(HelloWorldAdminPage, { welcomeMessage }),
      name: adminPageTitle,
      protected: true // Admin pages always require auth
    });
  }

  return {
    navigation,
    routes,
    metadata: {
      name: '@lksnext/hello-world-plugin',
      version: '1.0.0',
      description: 'A sample Hello World plugin demonstrating the AI-Core-Tools plugin architecture'
    }
  };
}
