import React, { useEffect, useMemo } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'sonner';
import { ThemeProvider } from '../themes/ThemeProvider';
import { AuthProvider } from '../auth/AuthConfig';
import { UserProvider } from '../contexts/UserContext';
import { SettingsCacheProvider } from '../contexts/SettingsCacheContext';
import { ConfirmProvider } from '../contexts/ConfirmContext';
import { Layout } from '../components/layout/Layout';
import SettingsLayout from '../components/layout/SettingsLayout';
import ScrollToTop from '../components/layout/ScrollToTop';
import { ProtectedLayoutRoute, AdminLayoutRoute, EditorLayoutRoute } from '../components/ProtectedLayoutRoute';
import { configService } from './ConfigService';
import { mergeNavigationConfig } from './NavigationMerger';
import { defaultNavigation } from './defaultNavigation';
import type { LibraryConfig, ExtraRoute } from './types';
import { baseTheme } from '../themes/baseTheme';

import LandingPage from '../pages/LandingPage';
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
import AppSettingsPage from '../pages/settings/AppSettingsPage';
import MCPConfigsPage from '../pages/settings/MCPConfigsPage';
import SkillsPage from '../pages/settings/SkillsPage';
import DataStructuresPage from '../pages/settings/DataStructuresPage';
import UsersPage from '../pages/admin/UsersPage';
import StatsPage from '../pages/admin/StatsPage';
import SystemSettingsPage from '../pages/admin/SystemSettingsPage';
import LoginPage from '../pages/LoginPage';
import AuthSuccessPage from '../pages/AuthSuccessPage';
import ProfilePage from '../pages/ProfilePage';
import RegisterPage from '../pages/RegisterPage';
import VerifyEmailPage from '../pages/VerifyEmailPage';
import PasswordResetRequestPage from '../pages/PasswordResetRequestPage';
import PasswordResetPage from '../pages/PasswordResetPage';
import SetPasswordPage from '../pages/SetPasswordPage';
import ChangePasswordPage from '../pages/ChangePasswordPage';
import SubscriptionPage from '../pages/SubscriptionPage';
import SaasUserListPage from '../pages/admin/SaasUserListPage';
import SystemAIServicesPage from '../pages/admin/SystemAIServicesPage';
import SystemEmbeddingServicesPage from '../pages/admin/SystemEmbeddingServicesPage';
import TierConfigPage from '../pages/admin/TierConfigPage';
import { DeploymentModeProvider } from '../contexts/DeploymentModeContext';
import { CapabilitiesProvider } from '../contexts/CapabilitiesContext';
import { PlatformChatbotProvider } from '../contexts/PlatformChatbotContext';
import PlatformChatbotWidget from '../components/platform-chatbot/PlatformChatbotWidget';
import MCPServersPage from '../pages/MCPServersPage';
import MCPServerFormPage from '../pages/MCPServerFormPage';
import MCPServerDetailPage from '../pages/MCPServerDetailPage';
import MarketplacePage from '../pages/MarketplacePage';
import MarketplaceAgentDetailPage from '../pages/MarketplaceAgentDetailPage';
import MarketplaceChatPage from '../pages/MarketplaceChatPage';
import MarketplaceHomePage from '../pages/MarketplaceHomePage';
import SharePointSourcesPage from '../pages/SharePointSourcesPage';
import SharePointWizardPage from '../pages/SharePointWizardPage';
import SharePointSourceDetailPage from '../pages/SharePointSourceDetailPage';
import EnterpriseFeaturePage from '../pages/EnterpriseFeaturePage';

interface ExtensibleBaseAppProps {
  config: LibraryConfig;
  extraRoutes?: ExtraRoute[];
  children?: React.ReactNode;
}

export const ExtensibleBaseApp: React.FC<ExtensibleBaseAppProps> = ({
  config,
  extraRoutes = [],
}) => {
  const allExtraRoutes = [...(config.routes || []), ...extraRoutes];
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
      baseUrl: config.apiConfig.baseUrl ?? 'http://localhost:8000',
      timeout: config.apiConfig.timeout || 30000,
      retries: config.apiConfig.retries || 3
    } : undefined,
    navigation: config.navigationConfig
  };

  useEffect(() => {
    configService.setClientConfig(clientConfig);
  }, [clientConfig]);

  const features = config.features || {};
  
  const mergedNavigationConfig = config.navigation
    ? mergeNavigationConfig(config.navigation)
    : (config.navigationConfig || defaultNavigation);

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
      <Toaster richColors closeButton position="top-right" />
      <AuthProvider config={config.authProps}>
        <UserProvider>
          <SettingsCacheProvider>
            <DeploymentModeProvider>
            <CapabilitiesProvider>
            <PlatformChatbotProvider>
            <Router>
              <ScrollToTop />
              <ConfirmProvider>
              <Routes>
                {/* Public routes */}
                <Route path="/login" element={<LoginPage />} />
                <Route path="/auth/success" element={<AuthSuccessPage />} />
                <Route path="/register" element={<RegisterPage />} />
                <Route path="/verify-email" element={<VerifyEmailPage />} />
                <Route path="/password-reset/request" element={<PasswordResetRequestPage />} />
                <Route path="/password-reset" element={<PasswordResetPage />} />
                <Route path="/set-password" element={<SetPasswordPage />} />
                <Route path="/change-password" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                    <ChangePasswordPage />
                  </ProtectedLayoutRoute>
                } />

                <Route path="/" element={<LandingPage />} />

                <Route path="/apps" element={
                  <EditorLayoutRoute {...commonLayoutProps}>
                      <AppsPage />
                  </EditorLayoutRoute>
                } />

                <Route path="/profile" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                      <ProfilePage />
                  </ProtectedLayoutRoute>
                } />

                <Route path="/marketplace" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                    <MarketplacePage />
                  </ProtectedLayoutRoute>
                } />

                <Route path="/marketplace/agents/:agentId" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                    <MarketplaceAgentDetailPage />
                  </ProtectedLayoutRoute>
                } />

                <Route path="/marketplace/chat/:conversationId" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                    <MarketplaceChatPage />
                  </ProtectedLayoutRoute>
                } />

                <Route path="/home" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                    <MarketplaceHomePage />
                  </ProtectedLayoutRoute>
                } />

                <Route path="/apps/:appId" element={
                  <EditorLayoutRoute {...commonLayoutProps}>
                      <AppDashboard />
                  </EditorLayoutRoute>
                } />

                <Route path="/apps/:appId/agents" element={
                  <EditorLayoutRoute {...commonLayoutProps}>
                      <AgentsPage />
                  </EditorLayoutRoute>
                } />

                <Route path="/apps/:appId/agents/:agentId" element={
                  <EditorLayoutRoute {...commonLayoutProps}>
                      <AgentFormPage />
                  </EditorLayoutRoute>
                } />

                <Route path="/apps/:appId/agents/:agentId/playground" element={
                  <EditorLayoutRoute {...commonLayoutProps}>
                      <AgentPlaygroundPage />
                  </EditorLayoutRoute>
                } />

                <Route path="/apps/:appId/silos" element={
                  <EditorLayoutRoute {...commonLayoutProps}>
                      <SilosPage />
                  </EditorLayoutRoute>
                } />

                <Route path="/apps/:appId/silos/:siloId" element={
                  <EditorLayoutRoute {...commonLayoutProps}>
                      <SiloFormPage />
                  </EditorLayoutRoute>
                } />

                <Route path="/apps/:appId/silos/:siloId/playground" element={
                  <EditorLayoutRoute {...commonLayoutProps}>
                      <SiloPlaygroundPage />
                  </EditorLayoutRoute>
                } />

                <Route path="/apps/:appId/repositories" element={
                  <EditorLayoutRoute {...commonLayoutProps}>
                      <RepositoriesPage />
                  </EditorLayoutRoute>
                } />

                <Route path="/apps/:appId/repositories/:repositoryId" element={
                  <EditorLayoutRoute {...commonLayoutProps}>
                      <RepositoryFormPage />
                  </EditorLayoutRoute>
                } />

                <Route path="/apps/:appId/repositories/:repositoryId/detail" element={
                  <EditorLayoutRoute {...commonLayoutProps}>
                      <RepositoryDetailPage />
                  </EditorLayoutRoute>
                } />

                <Route path="/apps/:appId/repositories/:repositoryId/playground" element={
                  <EditorLayoutRoute {...commonLayoutProps}>
                      <RepositoryPlaygroundPage />
                  </EditorLayoutRoute>
                } />

                <Route path="/apps/:appId/domains" element={
                  <EditorLayoutRoute {...commonLayoutProps}>
                      <DomainsPage />
                  </EditorLayoutRoute>
                } />

                <Route path="/apps/:appId/domains/:domainId" element={
                  <EditorLayoutRoute {...commonLayoutProps}>
                      <DomainFormPage />
                  </EditorLayoutRoute>
                } />

                <Route path="/apps/:appId/domains/:domainId/detail" element={
                  <EditorLayoutRoute {...commonLayoutProps}>
                      <DomainDetailPage />
                  </EditorLayoutRoute>
                } />

                <Route path="/apps/:appId/enterprise" element={
                  <EditorLayoutRoute {...commonLayoutProps}>
                      <EnterpriseFeaturePage />
                  </EditorLayoutRoute>
                } />

                <Route path="/apps/:appId/sharepoint" element={
                  <EditorLayoutRoute {...commonLayoutProps}>
                      <SharePointSourcesPage />
                  </EditorLayoutRoute>
                } />

                <Route path="/apps/:appId/sharepoint/new" element={
                  <EditorLayoutRoute {...commonLayoutProps}>
                      <SharePointWizardPage />
                  </EditorLayoutRoute>
                } />

                <Route path="/apps/:appId/sharepoint/:sourceId" element={
                  <EditorLayoutRoute {...commonLayoutProps}>
                      <SharePointSourceDetailPage />
                  </EditorLayoutRoute>
                } />

                <Route path="/apps/:appId/mcp-servers" element={
                  <EditorLayoutRoute {...commonLayoutProps}>
                      <MCPServersPage />
                  </EditorLayoutRoute>
                } />

                <Route path="/apps/:appId/mcp-servers/new" element={
                  <EditorLayoutRoute {...commonLayoutProps}>
                      <MCPServerFormPage />
                  </EditorLayoutRoute>
                } />

                <Route path="/apps/:appId/mcp-servers/:serverId" element={
                  <EditorLayoutRoute {...commonLayoutProps}>
                      <MCPServerDetailPage />
                  </EditorLayoutRoute>
                } />

                <Route path="/apps/:appId/mcp-servers/:serverId/edit" element={
                  <EditorLayoutRoute {...commonLayoutProps}>
                      <MCPServerFormPage />
                  </EditorLayoutRoute>
                } />

                <Route path="/apps/:appId/skills" element={
                  <EditorLayoutRoute {...commonLayoutProps}>
                      <SkillsPage />
                  </EditorLayoutRoute>
                } />

                <Route path="/apps/:appId/settings" element={
                  <EditorLayoutRoute {...commonLayoutProps}>
                      <SettingsLayout><AppSettingsPage /></SettingsLayout>
                  </EditorLayoutRoute>
                } />

                <Route path="/apps/:appId/settings/general" element={
                  <EditorLayoutRoute {...commonLayoutProps}>
                      <SettingsLayout><AppSettingsPage /></SettingsLayout>
                  </EditorLayoutRoute>
                } />

                <Route path="/apps/:appId/settings/ai-services" element={
                  <EditorLayoutRoute {...commonLayoutProps}>
                      <SettingsLayout><AIServicesPage /></SettingsLayout>
                  </EditorLayoutRoute>
                } />

                <Route path="/apps/:appId/settings/embedding-services" element={
                  <EditorLayoutRoute {...commonLayoutProps}>
                      <SettingsLayout><EmbeddingServicesPage /></SettingsLayout>
                  </EditorLayoutRoute>
                } />

                <Route path="/apps/:appId/settings/mcp-configs" element={
                  <EditorLayoutRoute {...commonLayoutProps}>
                      <SettingsLayout><MCPConfigsPage /></SettingsLayout>
                  </EditorLayoutRoute>
                } />

                <Route path="/apps/:appId/settings/api-keys" element={
                  <EditorLayoutRoute {...commonLayoutProps}>
                      <SettingsLayout><APIKeysPage /></SettingsLayout>
                  </EditorLayoutRoute>
                } />

                <Route path="/apps/:appId/settings/data-structures" element={
                  <EditorLayoutRoute {...commonLayoutProps}>
                      <SettingsLayout><DataStructuresPage /></SettingsLayout>
                  </EditorLayoutRoute>
                } />

                <Route path="/apps/:appId/settings/collaboration" element={
                  <EditorLayoutRoute {...commonLayoutProps}>
                      <SettingsLayout><CollaborationPage /></SettingsLayout>
                  </EditorLayoutRoute>
                } />

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

                <Route path="/admin/settings" element={
                  <AdminLayoutRoute {...commonLayoutProps}>
                    <SystemSettingsPage />
                  </AdminLayoutRoute>
                } />

                <Route path="/admin/saas-users" element={
                  <AdminLayoutRoute {...commonLayoutProps}>
                    <SaasUserListPage />
                  </AdminLayoutRoute>
                } />

                <Route path="/admin/system-ai-services" element={
                  <AdminLayoutRoute {...commonLayoutProps}>
                    <SystemAIServicesPage />
                  </AdminLayoutRoute>
                } />

                <Route path="/admin/system-embedding-services" element={
                  <AdminLayoutRoute {...commonLayoutProps}>
                    <SystemEmbeddingServicesPage />
                  </AdminLayoutRoute>
                } />

                <Route path="/admin/tier-config" element={
                  <AdminLayoutRoute {...commonLayoutProps}>
                    <TierConfigPage />
                  </AdminLayoutRoute>
                } />

                <Route path="/subscription" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                    <SubscriptionPage />
                  </ProtectedLayoutRoute>
                } />

                <Route path="/about" element={
                  <ProtectedLayoutRoute {...commonLayoutProps}>
                      <AboutPage />
                    </ProtectedLayoutRoute>
                } />

                {allExtraRoutes.map(route => {
                  let element;
                  if (route.adminOnly) {
                    element = <AdminLayoutRoute {...commonLayoutProps}>{route.element}</AdminLayoutRoute>;
                  } else if (route.protected) {
                    element = <ProtectedLayoutRoute {...commonLayoutProps}>{route.element}</ProtectedLayoutRoute>;
                  } else {
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

                <Route path="*" element={<Navigate to="/apps" replace />} />
              </Routes>
              <PlatformChatbotWidget />
              </ConfirmProvider>
            </Router>
            </PlatformChatbotProvider>
            </CapabilitiesProvider>
            </DeploymentModeProvider>
          </SettingsCacheProvider>
        </UserProvider>
      </AuthProvider>
    </ThemeProvider>
  );
};
