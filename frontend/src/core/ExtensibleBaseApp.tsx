import React, { useEffect, useMemo } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider } from '../themes/ThemeProvider';
import { AuthProvider } from '../auth/AuthConfig';
import { UserProvider } from '../contexts/UserContext';
import { SettingsCacheProvider } from '../contexts/SettingsCacheContext';
import { Layout } from '../components/layout/Layout';
import SettingsLayout from '../components/layout/SettingsLayout';
import { ProtectedLayoutRoute, AdminLayoutRoute } from '../components/ProtectedLayoutRoute';
import { configService } from './ConfigService';
import { mergeNavigationConfig } from './NavigationMerger';
import { defaultNavigation } from './defaultNavigation';
import type { LibraryConfig, ExtraRoute } from './types';
import { baseTheme } from '../themes/baseTheme';

// Import base pages
import HomePage from '../pages/HomePage';
import AppsPage from '../pages/AppsPage';
import AppDashboard from '../pages/AppDashboard';
import AgentsPage from '../pages/AgentsPage';
import AgentFormPage from '../pages/AgentFormPage';
import SilosPage from '../pages/SilosPage';
import SiloFormPage from '../pages/SiloFormPage';
import SiloPlaygroundPage from '../pages/SiloPlaygroundPage';
import RepositoriesPage from '../pages/RepositoriesPage';
import RepositoryFormPage from '../pages/RepositoryFormPage';
import RepositoryDetailPage from '../pages/RepositoryDetailPage';
import RepositoryPlaygroundPage from '../pages/RepositoryPlaygroundPage';
import DomainsPage from '../pages/DomainsPage';
import DomainFormPage from '../pages/DomainFormPage';
import DomainDetailPage from '../pages/DomainDetailPage';
import AgentPlaygroundPage from '../pages/AgentPlaygroundPage';
import AboutPage from '../pages/AboutPage';
import AIServicesPage from '../pages/settings/AIServicesPage';
import APIKeysPage from '../pages/settings/APIKeysPage';
import CollaborationPage from '../pages/settings/CollaborationPage';
import EmbeddingServicesPage from '../pages/settings/EmbeddingServicesPage';
import GeneralSettingsPage from '../pages/settings/GeneralSettingsPage';
import MCPConfigsPage from '../pages/settings/MCPConfigsPage';
import SkillsPage from '../pages/settings/SkillsPage';
import DataStructuresPage from '../pages/settings/DataStructuresPage';
import UsersPage from '../pages/admin/UsersPage';
import StatsPage from '../pages/admin/StatsPage';
import LoginPage from '../pages/LoginPage';
import AuthSuccessPage from '../pages/AuthSuccessPage';
import ProfilePage from '../pages/ProfilePage';
import MCPServersPage from '../pages/MCPServersPage';
import MCPServerFormPage from '../pages/MCPServerFormPage';
import MCPServerDetailPage from '../pages/MCPServerDetailPage';

interface ExtensibleBaseAppProps {
  config: LibraryConfig;
  extraRoutes?: ExtraRoute[];
  children?: React.ReactNode;
}

export const ExtensibleBaseApp: React.FC<ExtensibleBaseAppProps> = ({
  config,
  extraRoutes = [],
  children
}) => {
  // Merge routes from config and extraRoutes prop
  const allExtraRoutes = [...(config.routes || []), ...extraRoutes];
  // Convert LibraryConfig to ClientConfig for backward compatibility
  const clientConfig = {
    clientId: 'library-client',
    name: config.name || 'AI Core Tools',
    theme: config.themeProps?.customThemes?.[config.themeProps?.defaultTheme || 'default'] || baseTheme,
    auth: config.authProps ? {
      type: config.authProps.enabled ? 'oidc' as const : 'session' as const,
      oidc: config.authProps.oidc ? {
        enabled: true,
        authority: config.authProps.oidc.authority,
        clientId: config.authProps.oidc.client_id,
        redirectUri: `${globalThis.location.origin}${config.authProps.oidc.callbackPath || '/callback'}`,
        scope: config.authProps.oidc.scope || 'openid profile email'
      } : undefined
    } : { type: 'session' as const },
    branding: {
      companyName: config.name || 'AI Core Tools',
      logo: config.logo || '/mattin-small.png',
      favicon: config.favicon || '/favicon.ico',
      headerTitle: config.headerProps?.title || config.name || 'AI Core Tools'
    },
    api: config.apiConfig ? {
      baseUrl: config.apiConfig.baseUrl || 'http://localhost:8000',
      timeout: config.apiConfig.timeout || 30000,
      retries: config.apiConfig.retries || 3
    } : undefined,
    navigation: config.navigationConfig
  };

  // Initialize configuration service
  useEffect(() => {
    configService.setClientConfig(clientConfig);
  }, [clientConfig]);

  const features = config.features || {};
  
  // Merge navigation configuration
  const mergedNavigationConfig = config.navigation 
    ? mergeNavigationConfig(config.navigation)
    : (config.navigationConfig || defaultNavigation);

  // Common layout props used across all routes
  const commonLayoutProps = useMemo(() => ({
    navigationConfig: mergedNavigationConfig,
    headerProps: {
      ...config.headerProps,
      title: config.headerProps?.title || config.name,
      logoUrl: config.headerProps?.logoUrl || config.logo
    },
    footerProps: config.footerProps,
    layoutProps: config.layoutProps,
    navigationProps: config.navigationProps,
    showSidebar: features.showSidebar !== false,
    showHeader: features.showHeader !== false,
    showFooter: features.showFooter !== false,
  }), [mergedNavigationConfig, config, features]);

  return (
    <ThemeProvider theme={clientConfig.theme}>
      <AuthProvider config={config.authProps}>
        <UserProvider>
          <SettingsCacheProvider>
            <Router>
              <Routes>
                {/* Public routes */}
                <Route path="/login" element={<LoginPage />} />
                <Route path="/auth/success" element={<AuthSuccessPage />} />

                {/* Protected routes with Layout */}
                <Route path="/" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                      {config.homePage ? <config.homePage /> : <HomePage />}
                  </ProtectedLayoutRoute>
                } />

                <Route path="/apps" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                      <AppsPage />
                  </ProtectedLayoutRoute>
                } />

                <Route path="/profile" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                      <ProfilePage />
                  </ProtectedLayoutRoute>
                } />

                {/* App-specific routes */}
                <Route path="/apps/:appId" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                      <AppDashboard />                
                  </ProtectedLayoutRoute>
                } />

                {/* App-specific routes */}
                <Route path="/apps/:appId/agents" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                      <AgentsPage />
                  </ProtectedLayoutRoute>
                } />

                <Route path="/apps/:appId/agents/:agentId" element={
                    <ProtectedLayoutRoute {...commonLayoutProps}>
                      <AgentFormPage />
                    </ProtectedLayoutRoute>
                } />

                <Route path="/apps/:appId/agents/:agentId/playground" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                      <AgentPlaygroundPage />
                    </ProtectedLayoutRoute>
                } />

                <Route path="/apps/:appId/silos" element={
                    <ProtectedLayoutRoute {...commonLayoutProps}>
                      <SilosPage />
                    </ProtectedLayoutRoute>
                } />

                <Route path="/apps/:appId/silos/:siloId" element={
                    <ProtectedLayoutRoute {...commonLayoutProps}> 
                      <SiloFormPage />
                    </ProtectedLayoutRoute>
                } />

                <Route path="/apps/:appId/silos/:siloId/playground" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                      <SiloPlaygroundPage />
                    </ProtectedLayoutRoute>
                } />

                <Route path="/apps/:appId/repositories" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                      <RepositoriesPage />
                    </ProtectedLayoutRoute>
                } />

                <Route path="/apps/:appId/repositories/:repositoryId" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                      <RepositoryFormPage />
                    </ProtectedLayoutRoute>
                } />

                <Route path="/apps/:appId/repositories/:repositoryId/detail" element={
                    <ProtectedLayoutRoute {...commonLayoutProps}>
                     
                      <RepositoryDetailPage />
                    </ProtectedLayoutRoute>
                } />

                <Route path="/apps/:appId/repositories/:repositoryId/playground" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>            
                      <RepositoryPlaygroundPage />
                    </ProtectedLayoutRoute>
                } />

                <Route path="/apps/:appId/domains" element={
                    <ProtectedLayoutRoute {...commonLayoutProps}>
                      <DomainsPage />
                    </ProtectedLayoutRoute>
                } />

                <Route path="/apps/:appId/domains/:domainId" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>

                      <DomainFormPage />
                    </ProtectedLayoutRoute>
                } />

                <Route path="/apps/:appId/domains/:domainId/detail" element={
                    <ProtectedLayoutRoute {...commonLayoutProps}>
                      <DomainDetailPage />
                    </ProtectedLayoutRoute>
                } />

                {/* MCP Servers routes */}
                <Route path="/apps/:appId/mcp-servers" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                    <MCPServersPage />
                  </ProtectedLayoutRoute>
                } />

                <Route path="/apps/:appId/mcp-servers/new" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                    <MCPServerFormPage />
                  </ProtectedLayoutRoute>
                } />

                <Route path="/apps/:appId/mcp-servers/:serverId" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                    <MCPServerDetailPage />
                  </ProtectedLayoutRoute>
                } />

                <Route path="/apps/:appId/mcp-servers/:serverId/edit" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                    <MCPServerFormPage />
                  </ProtectedLayoutRoute>
                } />

                {/* Skills route */}
                <Route path="/apps/:appId/skills" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                    <SkillsPage />
                  </ProtectedLayoutRoute>
                } />

                {/* App-specific settings routes */}
                <Route path="/apps/:appId/settings" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                    <SettingsLayout><GeneralSettingsPage /></SettingsLayout>
                  </ProtectedLayoutRoute>
                } />

                <Route path="/apps/:appId/settings/general" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                    <SettingsLayout><GeneralSettingsPage /></SettingsLayout>
                  </ProtectedLayoutRoute>
                } />

                <Route path="/apps/:appId/settings/ai-services" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                    <SettingsLayout><AIServicesPage /></SettingsLayout>
                  </ProtectedLayoutRoute>
                } />

                <Route path="/apps/:appId/settings/embedding-services" element={
                    <ProtectedLayoutRoute {...commonLayoutProps}>
                      <SettingsLayout><EmbeddingServicesPage /></SettingsLayout>
                    </ProtectedLayoutRoute>
                } />

                <Route path="/apps/:appId/settings/mcp-configs" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                      <SettingsLayout><MCPConfigsPage /></SettingsLayout>
                    </ProtectedLayoutRoute>
                } />

                <Route path="/apps/:appId/settings/api-keys" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                      <SettingsLayout><APIKeysPage /></SettingsLayout>
                    </ProtectedLayoutRoute>
                } />

                <Route path="/apps/:appId/settings/data-structures" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                      <SettingsLayout><DataStructuresPage /></SettingsLayout>
                    </ProtectedLayoutRoute>
                } />

                <Route path="/apps/:appId/settings/collaboration" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                      <SettingsLayout><CollaborationPage /></SettingsLayout>
                    </ProtectedLayoutRoute>
                } />

                {/* Global settings routes */}
                <Route path="/settings/ai-services" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                    <SettingsLayout><AIServicesPage /></SettingsLayout>
                  </ProtectedLayoutRoute>
                } />

                <Route path="/settings/api-keys" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                      <SettingsLayout><APIKeysPage /></SettingsLayout>
                    </ProtectedLayoutRoute>
                } />

                <Route path="/settings/collaboration" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                      <SettingsLayout><CollaborationPage /></SettingsLayout>
                    </ProtectedLayoutRoute>
                } />

                <Route path="/settings/embedding-services" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                      <SettingsLayout><EmbeddingServicesPage /></SettingsLayout>
                    </ProtectedLayoutRoute>
                } />

                <Route path="/settings/general" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                    <SettingsLayout><GeneralSettingsPage /></SettingsLayout>
                  </ProtectedLayoutRoute>
                } />

                <Route path="/settings/mcp-configs" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                      <SettingsLayout><MCPConfigsPage /></SettingsLayout>
                    </ProtectedLayoutRoute>
                } />

                <Route path="/settings/data-structures" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                      <SettingsLayout><DataStructuresPage /></SettingsLayout>
                    </ProtectedLayoutRoute>
                } />

                {/* Admin routes */}
                <Route path="/admin/users" element={
                  <AdminLayoutRoute {...commonLayoutProps}>
                    <UsersPage />
                  </AdminLayoutRoute>
                } />

                <Route path="/admin/stats" element={
                  <AdminLayoutRoute {...commonLayoutProps}>
                    <StatsPage />
                  </AdminLayoutRoute>
                } />

                <Route path="/about" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                      <AboutPage />
                    </ProtectedLayoutRoute>
                } />

                {/* Client-specific extra routes */}
                {allExtraRoutes.map(route => {
                  // Determine which route protection to use
                  let element;
                  if (route.adminOnly) {
                    // Admin-only route (requires authentication AND admin privileges)
                    element = <AdminLayoutRoute {...commonLayoutProps}>{route.element}</AdminLayoutRoute>;
                  } else if (route.protected) {
                    // Protected route (requires authentication only)
                    element = <ProtectedLayoutRoute {...commonLayoutProps}>{route.element}</ProtectedLayoutRoute>;
                  } else {
                    // Public route
                    element = (
                      <Layout {...commonLayoutProps}>
                        {route.element}
                      </Layout>
                    );
                  }

                  return (
                    <Route 
                      key={route.path} 
                      path={route.path} 
                      element={element}
                    />
                  );
                })}

                {/* Default redirect */}
                <Route path="/" element={<Navigate to="/apps" replace />} />
              </Routes>
            </Router>
          </SettingsCacheProvider>
        </UserProvider>
      </AuthProvider>
    </ThemeProvider>
  );
};
