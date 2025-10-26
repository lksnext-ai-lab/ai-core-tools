import React, { useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider } from '../themes/ThemeProvider';
import { AuthProvider } from '../auth/AuthConfig';
import { UserProvider } from '../contexts/UserContext';
import { SettingsCacheProvider } from '../contexts/SettingsCacheContext';
import { Layout } from '../components/Layout/Layout';
import ProtectedRoute from '../components/ProtectedRoute';
import { configService } from './ConfigService';
import type { LibraryConfig, ExtraRoute } from './types';
import { baseTheme } from '../themes/baseTheme';

// Import base pages
import HomePage from '../pages/HomePage';
import AppsPage from '../pages/AppsPage';
import AppDashboard from '../pages/AppDashboard';
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
                      navigationConfig={config.navigationConfig}
                      headerProps={config.headerProps}
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
                      navigationConfig={config.navigationConfig}
                      headerProps={config.headerProps}
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
                      navigationConfig={config.navigationConfig}
                      headerProps={config.headerProps}
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

                {/* All other existing routes... */}
                {/* (Keeping the same structure as original BaseApp for now) */}

                {/* Client-specific extra routes */}
                {extraRoutes.map(route => (
                  <Route 
                    key={route.path} 
                    path={route.path} 
                    element={
                      route.protected ? (
                        <ProtectedRoute>
                          <Layout
                            navigationConfig={config.navigationConfig}
                            headerProps={config.headerProps}
                            footerProps={config.footerProps}
                            layoutProps={config.layoutProps}
                            navigationProps={config.navigationProps}
                            showSidebar={features.showSidebar !== false}
                            showHeader={features.showHeader !== false}
                            showFooter={features.showFooter !== false}
                          >
                            {route.element}
                          </Layout>
                        </ProtectedRoute>
                      ) : (
                        <Layout
                          navigationConfig={config.navigationConfig}
                          headerProps={config.headerProps}
                          footerProps={config.footerProps}
                          layoutProps={config.layoutProps}
                          navigationProps={config.navigationProps}
                          showSidebar={features.showSidebar !== false}
                          showHeader={features.showHeader !== false}
                          showFooter={features.showFooter !== false}
                        >
                          {route.element}
                        </Layout>
                      )
                    } 
                  />
                ))}

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
