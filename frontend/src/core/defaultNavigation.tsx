import React from 'react';
import {
  Home,
  Store,
  LayoutDashboard,
  Bot,
  Brain,
  Database,
  FolderOpen,
  Globe,
  Plug,
  Zap,
  Settings,
  Layers,
  Users,
  BarChart2,
  Info,
  KeyRound,
  FileText,
  CreditCard,
  Sliders,
  Cpu
} from 'lucide-react';
import type { NavigationConfig } from './types';

export const defaultNavigation: NavigationConfig = {
  // Sidebar navigation
  mainFeatures: [
    {
      path: '/home',
      name: 'Home',
      icon: <Home size={16} />,
      section: 'mainFeatures'
    },
    {
      path: '/marketplace',
      name: 'Marketplace',
      icon: <Store size={16} />,
      section: 'mainFeatures'
    },
    {
      path: '/apps',
      name: 'My Apps',
      icon: <Layers size={16} />,
      section: 'mainFeatures'
    }
  ],
  // App-specific horizontal navigation (when inside an app)
  appNavigation: [
    {
      path: '/apps/:appId',
      name: 'Dashboard',
      icon: <LayoutDashboard size={16} />,
      section: 'appNavigation'
    },
    {
      path: '/apps/:appId/agents',
      name: 'Agents',
      icon: <Bot size={16} />,
      section: 'appNavigation'
    },
    {
      path: '/apps/:appId/silos',
      name: 'Silos',
      icon: <Database size={16} />,
      section: 'appNavigation'
    },
    {
      path: '/apps/:appId/repositories',
      name: 'Repositories',
      icon: <FolderOpen size={16} />,
      section: 'appNavigation'
    },
    {
      path: '/apps/:appId/domains',
      name: 'Domains',
      icon: <Globe size={16} />,
      section: 'appNavigation'
    },
    {
      path: '/apps/:appId/mcp-servers',
      name: 'MCP Servers',
      icon: <Plug size={16} />,
      section: 'appNavigation'
    },
    {
      path: '/apps/:appId/skills',
      name: 'Skills',
      icon: <Zap size={16} />,
      section: 'appNavigation'
    },
    {
      path: '/apps/:appId/settings',
      name: 'App Settings',
      icon: <Settings size={16} />,
      section: 'appNavigation'
    }
  ],
  // Settings sub-navigation (rendered inside collapsible in sidebar)
  settingsNavigation: [
    {
      path: '/apps/:appId/settings/ai-services',
      name: 'AI Services',
      icon: <Bot size={16} />,
      section: 'settings'
    },
    {
      path: '/apps/:appId/settings/embedding-services',
      name: 'Embedding Services',
      icon: <Brain size={16} />,
      section: 'settings'
    },
    {
      path: '/apps/:appId/settings/mcp-configs',
      name: 'MCP Configs',
      icon: <Plug size={16} />,
      section: 'settings'
    },
    {
      path: '/apps/:appId/settings/api-keys',
      name: 'API Keys',
      icon: <KeyRound size={16} />,
      section: 'settings'
    },
    {
      path: '/apps/:appId/settings/data-structures',
      name: 'Data Structures',
      icon: <FileText size={16} />,
      section: 'settings'
    },
    {
      path: '/apps/:appId/settings/collaboration',
      name: 'Collaboration',
      icon: <Users size={16} />,
      section: 'settings'
    },
    {
      path: '/apps/:appId/settings/general',
      name: 'General',
      icon: <Settings size={16} />,
      section: 'settings'
    }
  ],
  // Administration section
  admin: [
    {
      path: '/admin/users',
      name: 'Users',
      icon: <Users size={16} />,
      section: 'admin',
      adminOnly: true
    },
    {
      path: '/admin/stats',
      name: 'Statistics',
      icon: <BarChart2 size={16} />,
      section: 'admin',
      adminOnly: true
    },
    {
      path: '/admin/settings',
      name: 'Settings',
      icon: <Settings size={16} />,
      section: 'admin',
      adminOnly: true
    },
    {
      path: '/admin/saas-users',
      name: 'SaaS Users',
      icon: <CreditCard size={16} />,
      section: 'admin',
      adminOnly: true,
      saasOnly: true
    },
    {
      path: '/admin/system-ai-services',
      name: 'System AI Services',
      icon: <Cpu size={16} />,
      section: 'admin',
      adminOnly: true,
    },
    {
      path: '/admin/system-embedding-services',
      name: 'System Embedding Services',
      icon: <Brain size={16} />,
      section: 'admin',
      adminOnly: true,
    },
    {
      path: '/admin/tier-config',
      name: 'Tier Config',
      icon: <Sliders size={16} />,
      section: 'admin',
      adminOnly: true,
      saasOnly: true
    },
    {
      path: '/about',
      name: 'About',
      icon: <Info size={16} />,
      section: 'admin'
    }
  ]
};
