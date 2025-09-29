/*
 * IA-Core-Tools - AI Toolbox Platform
 * Copyright (C) 2024 LKS Next
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { UserProvider } from './contexts/UserContext';
import { SettingsCacheProvider } from './contexts/SettingsCacheContext';
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
import DomainsPage from './pages/DomainsPage';
import DomainFormPage from './pages/DomainFormPage';
import DomainDetailPage from './pages/DomainDetailPage';
import AgentPlaygroundPage from './pages/AgentPlaygroundPage';
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
        <Route path="/auth/callback" element={<AuthSuccessPage />} />
        <Route path="/login/success" element={<AuthSuccessPage />} />

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

        <Route path="/apps/:appId/agents/:agentId/playground" element={
          <ProtectedRoute>
            <AppLayout>
              <AgentPlaygroundPage />
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

        {/* Domain routes */}
        <Route path="/apps/:appId/domains" element={
          <ProtectedRoute>
            <AppLayout>
              <DomainsPage />
            </AppLayout>
          </ProtectedRoute>
        } />

        <Route path="/apps/:appId/domains/new" element={
          <ProtectedRoute>
            <AppLayout>
              <DomainFormPage />
            </AppLayout>
          </ProtectedRoute>
        } />

        <Route path="/apps/:appId/domains/:domainId" element={
          <ProtectedRoute>
            <AppLayout>
              <DomainDetailPage />
            </AppLayout>
          </ProtectedRoute>
        } />

        <Route path="/apps/:appId/domains/:domainId/edit" element={
          <ProtectedRoute>
            <AppLayout>
              <DomainFormPage />
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
      <SettingsCacheProvider>
        <AppContent />
      </SettingsCacheProvider>
    </UserProvider>
  );
}

export default App;
