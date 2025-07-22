import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import AppLayout from './components/layout/AppLayout';
import AppsPage from './pages/AppsPage';
import AppDashboard from './pages/AppDashboard';
import AgentsPage from './pages/AgentsPage';

function App() {
  return (
    <Router>
      <Routes>
        {/* Global Routes (no sidebar context) */}
        <Route path="/" element={<Navigate to="/apps" replace />} />
        
        {/* Apps List (uses layout but no app context) */}
        <Route path="/apps" element={
          <AppLayout>
            <AppsPage />
          </AppLayout>
        } />

        {/* App-specific routes (with app context in sidebar) */}
        <Route path="/apps/:appId" element={
          <AppLayout>
            <AppDashboard />
          </AppLayout>
        } />
        
        <Route path="/apps/:appId/agents" element={
          <AppLayout>
            <AgentsPage />
          </AppLayout>
        } />

        {/* Placeholder routes for other features */}
        <Route path="/apps/:appId/repositories" element={
          <AppLayout>
            <div className="text-center py-12">
              <div className="text-6xl mb-4">📁</div>
              <h2 className="text-xl font-semibold mb-2">Repositories</h2>
              <p className="text-gray-600">Coming soon!</p>
            </div>
          </AppLayout>
        } />

        <Route path="/apps/:appId/silos" element={
          <AppLayout>
            <div className="text-center py-12">
              <div className="text-6xl mb-4">🗄️</div>
              <h2 className="text-xl font-semibold mb-2">Silos</h2>
              <p className="text-gray-600">Coming soon!</p>
            </div>
          </AppLayout>
        } />

        <Route path="/apps/:appId/domains" element={
          <AppLayout>
            <div className="text-center py-12">
              <div className="text-6xl mb-4">🌐</div>
              <h2 className="text-xl font-semibold mb-2">Domains</h2>
              <p className="text-gray-600">Coming soon!</p>
            </div>
          </AppLayout>
        } />

        <Route path="/apps/:appId/settings/*" element={
          <AppLayout>
            <div className="text-center py-12">
              <div className="text-6xl mb-4">⚙️</div>
              <h2 className="text-xl font-semibold mb-2">App Settings</h2>
              <p className="text-gray-600">Coming soon!</p>
            </div>
          </AppLayout>
        } />

        {/* About page */}
        <Route path="/about" element={
          <AppLayout>
            <div className="text-center py-12">
              <div className="text-6xl mb-4">ℹ️</div>
              <h2 className="text-xl font-semibold mb-2">About Mattin AI</h2>
              <p className="text-gray-600">Your AI platform dashboard</p>
            </div>
          </AppLayout>
        } />

        {/* Catch all - redirect to apps */}
        <Route path="*" element={<Navigate to="/apps" replace />} />
      </Routes>
    </Router>
  )
}

export default App
