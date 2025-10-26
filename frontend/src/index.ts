// Import base styles
import './index.css';

// Export core components
export { ExtensibleBaseApp } from './core/ExtensibleBaseApp';
// BaseApp and AppLayout have been deprecated - use ExtensibleBaseApp with Layout instead
export { configService } from './core/ConfigService';

// Export modular components
export { Header } from './components/Header/Header';
export { Sidebar } from './components/Sidebar/Sidebar';
export { Footer } from './components/Footer/Footer';
export { Layout } from './components/Layout/Layout';
export { ThemeSelector } from './components/Theme/ThemeSelector';

// Export contexts
export { UserProvider, useUser } from './contexts/UserContext';
export { SettingsCacheProvider } from './contexts/SettingsCacheContext';

// Export theme system
export { ThemeProvider } from './themes/ThemeProvider';
export { useTheme } from './themes/ThemeContext';

// Export auth
export { OIDCProvider } from './auth/OIDCProvider';
export { AuthProvider } from './auth/AuthConfig';
export { useAuth } from './auth/AuthContext';

// Export services
export { apiService } from './services/api';
export { authService } from './services/auth';

// Export types
export type { 
  ClientConfig, 
  ThemeConfig, 
  AuthConfig, 
  BrandingConfig,
  ApiConfig,
  ExtraRoute,
  FeatureConfig,
  CustomPage,
  LibraryConfig
} from './core/types';
export type { AuthProps } from './auth/AuthConfig';

// Export base pages (clients can reuse or override)
export { default as AppsPage } from './pages/AppsPage';
export { default as AppDashboard } from './pages/AppDashboard';
export { default as AgentsPage } from './pages/AgentsPage';
export { default as AgentFormPage } from './pages/AgentFormPage';
export { default as SilosPage } from './pages/SilosPage';
export { default as SiloFormPage } from './pages/SiloFormPage';
export { default as SiloPlaygroundPage } from './pages/SiloPlaygroundPage';
export { default as RepositoriesPage } from './pages/RepositoriesPage';
export { default as RepositoryFormPage } from './pages/RepositoryFormPage';
export { default as RepositoryDetailPage } from './pages/RepositoryDetailPage';
export { default as RepositoryPlaygroundPage } from './pages/RepositoryPlaygroundPage';
export { default as DomainsPage } from './pages/DomainsPage';
export { default as DomainFormPage } from './pages/DomainFormPage';
export { default as DomainDetailPage } from './pages/DomainDetailPage';
export { default as AgentPlaygroundPage } from './pages/AgentPlaygroundPage';
export { default as AIServicesPage } from './pages/settings/AIServicesPage';
export { default as APIKeysPage } from './pages/settings/APIKeysPage';
export { default as CollaborationPage } from './pages/settings/CollaborationPage';
export { default as EmbeddingServicesPage } from './pages/settings/EmbeddingServicesPage';
export { default as GeneralSettingsPage } from './pages/settings/GeneralSettingsPage';
export { default as MCPConfigsPage } from './pages/settings/MCPConfigsPage';
export { default as DataStructuresPage } from './pages/settings/DataStructuresPage';
export { default as UsersPage } from './pages/admin/UsersPage';
export { default as StatsPage } from './pages/admin/StatsPage';
export { default as LoginPage } from './pages/LoginPage';
export { default as AuthSuccessPage } from './pages/AuthSuccessPage';

// Export base theme
export { baseTheme } from './themes/baseTheme';
