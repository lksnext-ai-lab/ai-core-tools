import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { UserProvider } from './contexts/UserContext';
import ProtectedRoute from './components/ProtectedRoute';
import AppLayout from './components/layout/AppLayout';
// Pages
import AppsPage from './pages/AppsPage';
import AppDashboard from './pages/AppDashboard';
import AgentsPage from './pages/AgentsPage';
import AgentFormPage from './pages/AgentFormPage';
import SilosPage from './pages/SilosPage';
import SiloFormPage from './pages/SiloFormPage';
import SiloPlaygroundPage from './pages/SiloPlaygroundPage';
import RepositoriesPage from './pages/RepositoriesPage';
import RepositoryFormPage from './pages/RepositoryFormPage';
import RepositoryDetailPage from './pages/RepositoryDetailPage';
import RepositoryPlaygroundPage from './pages/RepositoryPlaygroundPage';
// Settings pages
import AIServicesPage from './pages/settings/AIServicesPage';
import APIKeysPage from './pages/settings/APIKeysPage';
import CollaborationPage from './pages/settings/CollaborationPage';
import EmbeddingServicesPage from './pages/settings/EmbeddingServicesPage';
import GeneralSettingsPage from './pages/settings/GeneralSettingsPage';
import MCPConfigsPage from './pages/settings/MCPConfigsPage';
import DataStructuresPage from './pages/settings/DataStructuresPage';
// Admin pages
import UsersPage from './pages/admin/UsersPage';
import StatsPage from './pages/admin/StatsPage';
// Auth pages
import LoginPage from './pages/LoginPage';
import AuthSuccessPage from './pages/AuthSuccessPage';

function AppContent() {
  return (
    <Router>
      <Routes>
        {/* Public routes */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/auth/success" element={<AuthSuccessPage />} />

        {/* Protected routes */}
        <Route path="/apps" element={
          <ProtectedRoute>
            <AppLayout>
              <AppsPage />
            </AppLayout>
          </ProtectedRoute>
        } />

        {/* App-specific routes */}
        <Route path="/apps/:appId" element={
          <ProtectedRoute>
            <AppLayout>
              <AppDashboard />
            </AppLayout>
          </ProtectedRoute>
        } />

        <Route path="/apps/:appId/agents" element={
          <ProtectedRoute>
            <AppLayout>
              <AgentsPage />
            </AppLayout>
          </ProtectedRoute>
        } />

        <Route path="/apps/:appId/agents/:agentId" element={
          <ProtectedRoute>
            <AppLayout>
              <AgentFormPage />
            </AppLayout>
          </ProtectedRoute>
        } />

        <Route path="/apps/:appId/silos" element={
          <ProtectedRoute>
            <AppLayout>
              <SilosPage />
            </AppLayout>
          </ProtectedRoute>
        } />

        <Route path="/apps/:appId/silos/new" element={
          <ProtectedRoute>
            <AppLayout>
              <SiloFormPage />
            </AppLayout>
          </ProtectedRoute>
        } />

        <Route path="/apps/:appId/silos/:siloId" element={
          <ProtectedRoute>
            <AppLayout>
              <SiloFormPage />
            </AppLayout>
          </ProtectedRoute>
        } />

        <Route path="/apps/:appId/silos/:siloId/playground" element={
          <ProtectedRoute>
            <AppLayout>
              <SiloPlaygroundPage />
            </AppLayout>
          </ProtectedRoute>
        } />

        {/* Repository routes */}
        <Route path="/apps/:appId/repositories" element={
          <ProtectedRoute>
            <AppLayout>
              <RepositoriesPage />
            </AppLayout>
          </ProtectedRoute>
        } />

        <Route path="/apps/:appId/repositories/:repositoryId" element={
          <ProtectedRoute>
            <AppLayout>
              <RepositoryFormPage />
            </AppLayout>
          </ProtectedRoute>
        } />

        <Route path="/apps/:appId/repositories/:repositoryId/detail" element={
          <ProtectedRoute>
            <AppLayout>
              <RepositoryDetailPage />
            </AppLayout>
          </ProtectedRoute>
        } />

        <Route path="/apps/:appId/repositories/:repositoryId/playground" element={
          <ProtectedRoute>
            <AppLayout>
              <RepositoryPlaygroundPage />
            </AppLayout>
          </ProtectedRoute>
        } />

        {/* Settings routes */}
        <Route path="/apps/:appId/settings" element={
          <ProtectedRoute>
            <AppLayout>
              <GeneralSettingsPage />
            </AppLayout>
          </ProtectedRoute>
        } />

        <Route path="/apps/:appId/settings/general" element={
          <ProtectedRoute>
            <AppLayout>
              <GeneralSettingsPage />
            </AppLayout>
          </ProtectedRoute>
        } />

        <Route path="/apps/:appId/settings/ai-services" element={
          <ProtectedRoute>
            <AppLayout>
              <AIServicesPage />
            </AppLayout>
          </ProtectedRoute>
        } />

        <Route path="/apps/:appId/settings/api-keys" element={
          <ProtectedRoute>
            <AppLayout>
              <APIKeysPage />
            </AppLayout>
          </ProtectedRoute>
        } />

        <Route path="/apps/:appId/settings/collaboration" element={
          <ProtectedRoute>
            <AppLayout>
              <CollaborationPage />
            </AppLayout>
          </ProtectedRoute>
        } />

        <Route path="/apps/:appId/settings/embedding-services" element={
          <ProtectedRoute>
            <AppLayout>
              <EmbeddingServicesPage />
            </AppLayout>
          </ProtectedRoute>
        } />

        <Route path="/apps/:appId/settings/mcp-configs" element={
          <ProtectedRoute>
            <AppLayout>
              <MCPConfigsPage />
            </AppLayout>
          </ProtectedRoute>
        } />

        <Route path="/apps/:appId/settings/data-structures" element={
          <ProtectedRoute>
            <AppLayout>
              <DataStructuresPage />
            </AppLayout>
          </ProtectedRoute>
        } />

        {/* Admin routes */}
        <Route path="/admin/users" element={
          <ProtectedRoute>
            <AppLayout>
              <UsersPage />
            </AppLayout>
          </ProtectedRoute>
        } />

        <Route path="/admin/stats" element={
          <ProtectedRoute>
            <AppLayout>
              <StatsPage />
            </AppLayout>
          </ProtectedRoute>
        } />

        {/* Default redirect */}
        <Route path="/" element={<Navigate to="/apps" replace />} />
      </Routes>
    </Router>
  );
}

function App() {
  return (
    <UserProvider>
      <AppContent />
    </UserProvider>
  );
}

export default App;
