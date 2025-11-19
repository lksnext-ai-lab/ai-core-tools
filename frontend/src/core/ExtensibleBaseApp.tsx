import React, { useEffect, useMemo } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider } from '../themes/ThemeProvider';
import { AuthProvider } from '../auth/AuthConfig';
import { UserProvider } from '../contexts/UserContext';
import { SettingsCacheProvider } from '../contexts/SettingsCacheContext';
import { Layout } from '../components/layout/Layout';
import SettingsLayout from '../components/layout/SettingsLayout';
import ProtectedRoute from '../components/ProtectedRoute';
import AdminRoute from '../components/AdminRoute';
import { ProtectedLayoutRoute } from '../components/ProtectedLayoutRoute';
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
import DataStructuresPage from '../pages/settings/DataStructuresPage';
import UsersPage from '../pages/admin/UsersPage';
import StatsPage from '../pages/admin/StatsPage';
import LoginPage from '../pages/LoginPage';
import AuthSuccessPage from '../pages/AuthSuccessPage';

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
        redirectUri: `${window.location.origin}${config.authProps.oidc.callbackPath || '/callback'}`,
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
                <Route path="/login/success" element={<AuthSuccessPage />} />

                {/* Protected routes with Layout */}
                <Route path="/" element={
                  <ProtectedRoute>
                    <Layout
                      navigationConfig={mergedNavigationConfig}
                      headerProps={{
                        ...config.headerProps,
                        title: config.headerProps?.title || config.name,
                        logoUrl: config.headerProps?.logoUrl || config.logo
                      }}
                      footerProps={config.footerProps}
                      layoutProps={config.layoutProps}
                      navigationProps={config.navigationProps}
                      showSidebar={features.showSidebar !== false}
                      showHeader={features.showHeader !== false}
                      showFooter={features.showFooter !== false}
                    >
                      {config.homePage ? <config.homePage /> : <HomePage />}
                    </Layout>
                  </ProtectedRoute>
                } />

                <Route path="/apps" element={
                  <ProtectedRoute>
                    <Layout
                      navigationConfig={mergedNavigationConfig}
                      headerProps={{
                        ...config.headerProps,
                        title: config.headerProps?.title || config.name,
                        logoUrl: config.headerProps?.logoUrl || config.logo
                      }}
                      footerProps={config.footerProps}
                      layoutProps={config.layoutProps}
                      navigationProps={config.navigationProps}
                      showSidebar={features.showSidebar !== false}
                      showHeader={features.showHeader !== false}
                      showFooter={features.showFooter !== false}
                    >
                      <AppsPage />
                    </Layout>
                  </ProtectedRoute>
                } />

                {/* App-specific routes */}
                <Route path="/apps/:appId" element={
                  <ProtectedRoute>
                    <Layout
                      navigationConfig={mergedNavigationConfig}
                      headerProps={{
                        ...config.headerProps,
                        title: config.headerProps?.title || config.name,
                        logoUrl: config.headerProps?.logoUrl || config.logo
                      }}
                      footerProps={config.footerProps}
                      layoutProps={config.layoutProps}
                      navigationProps={config.navigationProps}
                      showSidebar={features.showSidebar !== false}
                      showHeader={features.showHeader !== false}
                      showFooter={features.showFooter !== false}
                    >
                      <AppDashboard />
                    </Layout>
                  </ProtectedRoute>
                } />

                {/* App-specific routes */}
                <Route path="/apps/:appId/agents" element={
                  <ProtectedRoute>
                    <Layout
                      navigationConfig={mergedNavigationConfig}
                      headerProps={{
                        ...config.headerProps,
                        title: config.headerProps?.title || config.name,
                        logoUrl: config.headerProps?.logoUrl || config.logo
                      }}
                      footerProps={config.footerProps}
                      layoutProps={config.layoutProps}
                      navigationProps={config.navigationProps}
                      showSidebar={features.showSidebar !== false}
                      showHeader={features.showHeader !== false}
                      showFooter={features.showFooter !== false}
                    >
                      <AgentsPage />
                    </Layout>
                  </ProtectedRoute>
                } />

                <Route path="/apps/:appId/agents/:agentId" element={
                  <ProtectedRoute>
                    <Layout
                      navigationConfig={mergedNavigationConfig}
                      headerProps={{
                        ...config.headerProps,
                        title: config.headerProps?.title || config.name,
                        logoUrl: config.headerProps?.logoUrl || config.logo
                      }}
                      footerProps={config.footerProps}
                      layoutProps={config.layoutProps}
                      navigationProps={config.navigationProps}
                      showSidebar={features.showSidebar !== false}
                      showHeader={features.showHeader !== false}
                      showFooter={features.showFooter !== false}
                    >
                      <AgentFormPage />
                    </Layout>
                  </ProtectedRoute>
                } />

                <Route path="/apps/:appId/agents/:agentId/playground" element={
                  <ProtectedRoute>
                    <Layout
                      navigationConfig={mergedNavigationConfig}
                      headerProps={{
                        ...config.headerProps,
                        title: config.headerProps?.title || config.name,
                        logoUrl: config.headerProps?.logoUrl || config.logo
                      }}
                      footerProps={config.footerProps}
                      layoutProps={config.layoutProps}
                      navigationProps={config.navigationProps}
                      showSidebar={features.showSidebar !== false}
                      showHeader={features.showHeader !== false}
                      showFooter={features.showFooter !== false}
                    >
                      <AgentPlaygroundPage />
                    </Layout>
                  </ProtectedRoute>
                } />

                <Route path="/apps/:appId/silos" element={
                  <ProtectedRoute>
                    <Layout
                      navigationConfig={mergedNavigationConfig}
                      headerProps={{
                        ...config.headerProps,
                        title: config.headerProps?.title || config.name,
                        logoUrl: config.headerProps?.logoUrl || config.logo
                      }}
                      footerProps={config.footerProps}
                      layoutProps={config.layoutProps}
                      navigationProps={config.navigationProps}
                      showSidebar={features.showSidebar !== false}
                      showHeader={features.showHeader !== false}
                      showFooter={features.showFooter !== false}
                    >
                      <SilosPage />
                    </Layout>
                  </ProtectedRoute>
                } />

                <Route path="/apps/:appId/silos/:siloId" element={
                  <ProtectedRoute>
                    <Layout
                      navigationConfig={mergedNavigationConfig}
                      headerProps={{
                        ...config.headerProps,
                        title: config.headerProps?.title || config.name,
                        logoUrl: config.headerProps?.logoUrl || config.logo
                      }}
                      footerProps={config.footerProps}
                      layoutProps={config.layoutProps}
                      navigationProps={config.navigationProps}
                      showSidebar={features.showSidebar !== false}
                      showHeader={features.showHeader !== false}
                      showFooter={features.showFooter !== false}
                    >
                      <SiloFormPage />
                    </Layout>
                  </ProtectedRoute>
                } />

                <Route path="/apps/:appId/silos/:siloId/playground" element={
                  <ProtectedRoute>
                    <Layout
                      navigationConfig={mergedNavigationConfig}
                      headerProps={{
                        ...config.headerProps,
                        title: config.headerProps?.title || config.name,
                        logoUrl: config.headerProps?.logoUrl || config.logo
                      }}
                      footerProps={config.footerProps}
                      layoutProps={config.layoutProps}
                      navigationProps={config.navigationProps}
                      showSidebar={features.showSidebar !== false}
                      showHeader={features.showHeader !== false}
                      showFooter={features.showFooter !== false}
                    >
                      <SiloPlaygroundPage />
                    </Layout>
                  </ProtectedRoute>
                } />

                <Route path="/apps/:appId/repositories" element={
                  <ProtectedRoute>
                    <Layout
                      navigationConfig={mergedNavigationConfig}
                      headerProps={{
                        ...config.headerProps,
                        title: config.headerProps?.title || config.name,
                        logoUrl: config.headerProps?.logoUrl || config.logo
                      }}
                      footerProps={config.footerProps}
                      layoutProps={config.layoutProps}
                      navigationProps={config.navigationProps}
                      showSidebar={features.showSidebar !== false}
                      showHeader={features.showHeader !== false}
                      showFooter={features.showFooter !== false}
                    >
                      <RepositoriesPage />
                    </Layout>
                  </ProtectedRoute>
                } />

                <Route path="/apps/:appId/repositories/:repositoryId" element={
                  <ProtectedRoute>
                    <Layout
                      navigationConfig={mergedNavigationConfig}
                      headerProps={{
                        ...config.headerProps,
                        title: config.headerProps?.title || config.name,
                        logoUrl: config.headerProps?.logoUrl || config.logo
                      }}
                      footerProps={config.footerProps}
                      layoutProps={config.layoutProps}
                      navigationProps={config.navigationProps}
                      showSidebar={features.showSidebar !== false}
                      showHeader={features.showHeader !== false}
                      showFooter={features.showFooter !== false}
                    >
                      <RepositoryFormPage />
                    </Layout>
                  </ProtectedRoute>
                } />

                <Route path="/apps/:appId/repositories/:repositoryId/detail" element={
                  <ProtectedRoute>
                    <Layout
                      navigationConfig={mergedNavigationConfig}
                      headerProps={{
                        ...config.headerProps,
                        title: config.headerProps?.title || config.name,
                        logoUrl: config.headerProps?.logoUrl || config.logo
                      }}
                      footerProps={config.footerProps}
                      layoutProps={config.layoutProps}
                      navigationProps={config.navigationProps}
                      showSidebar={features.showSidebar !== false}
                      showHeader={features.showHeader !== false}
                      showFooter={features.showFooter !== false}
                    >
                      <RepositoryDetailPage />
                    </Layout>
                  </ProtectedRoute>
                } />

                <Route path="/apps/:appId/repositories/:repositoryId/playground" element={
                  <ProtectedRoute>
                    <Layout
                      navigationConfig={mergedNavigationConfig}
                      headerProps={{
                        ...config.headerProps,
                        title: config.headerProps?.title || config.name,
                        logoUrl: config.headerProps?.logoUrl || config.logo
                      }}
                      footerProps={config.footerProps}
                      layoutProps={config.layoutProps}
                      navigationProps={config.navigationProps}
                      showSidebar={features.showSidebar !== false}
                      showHeader={features.showHeader !== false}
                      showFooter={features.showFooter !== false}
                    >
                      <RepositoryPlaygroundPage />
                    </Layout>
                  </ProtectedRoute>
                } />

                <Route path="/apps/:appId/domains" element={
                  <ProtectedRoute>
                    <Layout
                      navigationConfig={mergedNavigationConfig}
                      headerProps={{
                        ...config.headerProps,
                        title: config.headerProps?.title || config.name,
                        logoUrl: config.headerProps?.logoUrl || config.logo
                      }}
                      footerProps={config.footerProps}
                      layoutProps={config.layoutProps}
                      navigationProps={config.navigationProps}
                      showSidebar={features.showSidebar !== false}
                      showHeader={features.showHeader !== false}
                      showFooter={features.showFooter !== false}
                    >
                      <DomainsPage />
                    </Layout>
                  </ProtectedRoute>
                } />

                <Route path="/apps/:appId/domains/:domainId" element={
                  <ProtectedRoute>
                    <Layout
                      navigationConfig={mergedNavigationConfig}
                      headerProps={{
                        ...config.headerProps,
                        title: config.headerProps?.title || config.name,
                        logoUrl: config.headerProps?.logoUrl || config.logo
                      }}
                      footerProps={config.footerProps}
                      layoutProps={config.layoutProps}
                      navigationProps={config.navigationProps}
                      showSidebar={features.showSidebar !== false}
                      showHeader={features.showHeader !== false}
                      showFooter={features.showFooter !== false}
                    >
                      <DomainFormPage />
                    </Layout>
                  </ProtectedRoute>
                } />

                <Route path="/apps/:appId/domains/:domainId/detail" element={
                  <ProtectedRoute>
                    <Layout
                      navigationConfig={mergedNavigationConfig}
                      headerProps={{
                        ...config.headerProps,
                        title: config.headerProps?.title || config.name,
                        logoUrl: config.headerProps?.logoUrl || config.logo
                      }}
                      footerProps={config.footerProps}
                      layoutProps={config.layoutProps}
                      navigationProps={config.navigationProps}
                      showSidebar={features.showSidebar !== false}
                      showHeader={features.showHeader !== false}
                      showFooter={features.showFooter !== false}
                    >
                      <DomainDetailPage />
                    </Layout>
                  </ProtectedRoute>
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
                  <ProtectedRoute>
                    <Layout
                      navigationConfig={mergedNavigationConfig}
                      headerProps={{
                        ...config.headerProps,
                        title: config.headerProps?.title || config.name,
                        logoUrl: config.headerProps?.logoUrl || config.logo
                      }}
                      footerProps={config.footerProps}
                      layoutProps={config.layoutProps}
                      navigationProps={config.navigationProps}
                      showSidebar={features.showSidebar !== false}
                      showHeader={features.showHeader !== false}
                      showFooter={features.showFooter !== false}
                    >
                      <SettingsLayout><EmbeddingServicesPage /></SettingsLayout>
                    </Layout>
                  </ProtectedRoute>
                } />

                <Route path="/apps/:appId/settings/mcp-configs" element={
                  <ProtectedRoute>
                    <Layout
                      navigationConfig={mergedNavigationConfig}
                      headerProps={{
                        ...config.headerProps,
                        title: config.headerProps?.title || config.name,
                        logoUrl: config.headerProps?.logoUrl || config.logo
                      }}
                      footerProps={config.footerProps}
                      layoutProps={config.layoutProps}
                      navigationProps={config.navigationProps}
                      showSidebar={features.showSidebar !== false}
                      showHeader={features.showHeader !== false}
                      showFooter={features.showFooter !== false}
                    >
                      <SettingsLayout><MCPConfigsPage /></SettingsLayout>
                    </Layout>
                  </ProtectedRoute>
                } />

                <Route path="/apps/:appId/settings/api-keys" element={
                  <ProtectedRoute>
                    <Layout
                      navigationConfig={mergedNavigationConfig}
                      headerProps={{
                        ...config.headerProps,
                        title: config.headerProps?.title || config.name,
                        logoUrl: config.headerProps?.logoUrl || config.logo
                      }}
                      footerProps={config.footerProps}
                      layoutProps={config.layoutProps}
                      navigationProps={config.navigationProps}
                      showSidebar={features.showSidebar !== false}
                      showHeader={features.showHeader !== false}
                      showFooter={features.showFooter !== false}
                    >
                      <SettingsLayout><APIKeysPage /></SettingsLayout>
                    </Layout>
                  </ProtectedRoute>
                } />

                <Route path="/apps/:appId/settings/data-structures" element={
                  <ProtectedRoute>
                    <Layout
                      navigationConfig={mergedNavigationConfig}
                      headerProps={{
                        ...config.headerProps,
                        title: config.headerProps?.title || config.name,
                        logoUrl: config.headerProps?.logoUrl || config.logo
                      }}
                      footerProps={config.footerProps}
                      layoutProps={config.layoutProps}
                      navigationProps={config.navigationProps}
                      showSidebar={features.showSidebar !== false}
                      showHeader={features.showHeader !== false}
                      showFooter={features.showFooter !== false}
                    >
                      <SettingsLayout><DataStructuresPage /></SettingsLayout>
                    </Layout>
                  </ProtectedRoute>
                } />

                <Route path="/apps/:appId/settings/collaboration" element={
                  <ProtectedRoute>
                    <Layout
                      navigationConfig={mergedNavigationConfig}
                      headerProps={{
                        ...config.headerProps,
                        title: config.headerProps?.title || config.name,
                        logoUrl: config.headerProps?.logoUrl || config.logo
                      }}
                      footerProps={config.footerProps}
                      layoutProps={config.layoutProps}
                      navigationProps={config.navigationProps}
                      showSidebar={features.showSidebar !== false}
                      showHeader={features.showHeader !== false}
                      showFooter={features.showFooter !== false}
                    >
                      <SettingsLayout><CollaborationPage /></SettingsLayout>
                    </Layout>
                  </ProtectedRoute>
                } />

                {/* Global settings routes */}
                <Route path="/settings/ai-services" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                    <SettingsLayout><AIServicesPage /></SettingsLayout>
                  </ProtectedLayoutRoute>
                } />

                <Route path="/settings/api-keys" element={
                  <ProtectedRoute>
                    <Layout
                      navigationConfig={mergedNavigationConfig}
                      headerProps={{
                        ...config.headerProps,
                        title: config.headerProps?.title || config.name,
                        logoUrl: config.headerProps?.logoUrl || config.logo
                      }}
                      footerProps={config.footerProps}
                      layoutProps={config.layoutProps}
                      navigationProps={config.navigationProps}
                      showSidebar={features.showSidebar !== false}
                      showHeader={features.showHeader !== false}
                      showFooter={features.showFooter !== false}
                    >
                      <SettingsLayout><APIKeysPage /></SettingsLayout>
                    </Layout>
                  </ProtectedRoute>
                } />

                <Route path="/settings/collaboration" element={
                  <ProtectedRoute>
                    <Layout
                      navigationConfig={mergedNavigationConfig}
                      headerProps={{
                        ...config.headerProps,
                        title: config.headerProps?.title || config.name,
                        logoUrl: config.headerProps?.logoUrl || config.logo
                      }}
                      footerProps={config.footerProps}
                      layoutProps={config.layoutProps}
                      navigationProps={config.navigationProps}
                      showSidebar={features.showSidebar !== false}
                      showHeader={features.showHeader !== false}
                      showFooter={features.showFooter !== false}
                    >
                      <SettingsLayout><CollaborationPage /></SettingsLayout>
                    </Layout>
                  </ProtectedRoute>
                } />

                <Route path="/settings/embedding-services" element={
                  <ProtectedRoute>
                    <Layout
                      navigationConfig={mergedNavigationConfig}
                      headerProps={{
                        ...config.headerProps,
                        title: config.headerProps?.title || config.name,
                        logoUrl: config.headerProps?.logoUrl || config.logo
                      }}
                      footerProps={config.footerProps}
                      layoutProps={config.layoutProps}
                      navigationProps={config.navigationProps}
                      showSidebar={features.showSidebar !== false}
                      showHeader={features.showHeader !== false}
                      showFooter={features.showFooter !== false}
                    >
                      <SettingsLayout><EmbeddingServicesPage /></SettingsLayout>
                    </Layout>
                  </ProtectedRoute>
                } />

                <Route path="/settings/general" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                    <SettingsLayout><GeneralSettingsPage /></SettingsLayout>
                  </ProtectedLayoutRoute>
                } />

                <Route path="/settings/mcp-configs" element={
                  <ProtectedRoute>
                    <Layout
                      navigationConfig={mergedNavigationConfig}
                      headerProps={{
                        ...config.headerProps,
                        title: config.headerProps?.title || config.name,
                        logoUrl: config.headerProps?.logoUrl || config.logo
                      }}
                      footerProps={config.footerProps}
                      layoutProps={config.layoutProps}
                      navigationProps={config.navigationProps}
                      showSidebar={features.showSidebar !== false}
                      showHeader={features.showHeader !== false}
                      showFooter={features.showFooter !== false}
                    >
                      <SettingsLayout><MCPConfigsPage /></SettingsLayout>
                    </Layout>
                  </ProtectedRoute>
                } />

                <Route path="/settings/data-structures" element={
                  <ProtectedRoute>
                    <Layout
                      navigationConfig={mergedNavigationConfig}
                      headerProps={{
                        ...config.headerProps,
                        title: config.headerProps?.title || config.name,
                        logoUrl: config.headerProps?.logoUrl || config.logo
                      }}
                      footerProps={config.footerProps}
                      layoutProps={config.layoutProps}
                      navigationProps={config.navigationProps}
                      showSidebar={features.showSidebar !== false}
                      showHeader={features.showHeader !== false}
                      showFooter={features.showFooter !== false}
                    >
                      <SettingsLayout><DataStructuresPage /></SettingsLayout>
                    </Layout>
                  </ProtectedRoute>
                } />

                {/* Admin routes */}
                <Route path="/admin/users" element={
                  <AdminRoute>
                    <Layout
                      navigationConfig={mergedNavigationConfig}
                      headerProps={{
                        ...config.headerProps,
                        title: config.headerProps?.title || config.name,
                        logoUrl: config.headerProps?.logoUrl || config.logo
                      }}
                      footerProps={config.footerProps}
                      layoutProps={config.layoutProps}
                      navigationProps={config.navigationProps}
                      showSidebar={features.showSidebar !== false}
                      showHeader={features.showHeader !== false}
                      showFooter={features.showFooter !== false}
                    >
                      <UsersPage />
                    </Layout>
                  </AdminRoute>
                } />

                <Route path="/admin/stats" element={
                  <AdminRoute>
                    <Layout
                      navigationConfig={mergedNavigationConfig}
                      headerProps={{
                        ...config.headerProps,
                        title: config.headerProps?.title || config.name,
                        logoUrl: config.headerProps?.logoUrl || config.logo
                      }}
                      footerProps={config.footerProps}
                      layoutProps={config.layoutProps}
                      navigationProps={config.navigationProps}
                      showSidebar={features.showSidebar !== false}
                      showHeader={features.showHeader !== false}
                      showFooter={features.showFooter !== false}
                    >
                      <StatsPage />
                    </Layout>
                  </AdminRoute>
                } />

                <Route path="/about" element={
                  <ProtectedRoute>
                    <Layout
                      navigationConfig={mergedNavigationConfig}
                      headerProps={{
                        ...config.headerProps,
                        title: config.headerProps?.title || config.name,
                        logoUrl: config.headerProps?.logoUrl || config.logo
                      }}
                      footerProps={config.footerProps}
                      layoutProps={config.layoutProps}
                      navigationProps={config.navigationProps}
                      showSidebar={features.showSidebar !== false}
                      showHeader={features.showHeader !== false}
                      showFooter={features.showFooter !== false}
                    >
                      <AboutPage />
                    </Layout>
                  </ProtectedRoute>
                } />

                {/* Client-specific extra routes */}
                {allExtraRoutes.map(route => {
                  const layoutContent = (
                    <Layout
                      navigationConfig={mergedNavigationConfig}
                      headerProps={{
                        ...config.headerProps,
                        title: config.headerProps?.title || config.name,
                        logoUrl: config.headerProps?.logoUrl || config.logo
                      }}
                      footerProps={config.footerProps}
                      layoutProps={config.layoutProps}
                      navigationProps={config.navigationProps}
                      showSidebar={features.showSidebar !== false}
                      showHeader={features.showHeader !== false}
                      showFooter={features.showFooter !== false}
                    >
                      {route.element}
                    </Layout>
                  );

                  // Determine which route protection to use
                  let element;
                  if (route.adminOnly) {
                    // Admin-only route (requires authentication AND admin privileges)
                    element = <AdminRoute>{layoutContent}</AdminRoute>;
                  } else if (route.protected) {
                    // Protected route (requires authentication only)
                    element = <ProtectedRoute>{layoutContent}</ProtectedRoute>;
                  } else {
                    // Public route
                    element = layoutContent;
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
