import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { apiService } from '../services/api';
import Modal from '../components/ui/Modal';
import AppForm from '../components/forms/AppForm';

// Define the App type (like your Pydantic models!)
interface App {
  app_id: number;
  name: string;
  created_at: string;
  owner_id: number;
}

// React Component = Function that returns HTML-like JSX
function AppsPage() {
  // State = variables that trigger re-renders when they change
  const [apps, setApps] = useState<App[]>([]);           // Like self.apps = []
  const [loading, setLoading] = useState(true);          // Like self.loading = True
  const [error, setError] = useState<string | null>(null); // Like self.error = None
  
  // Modal state
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingApp, setEditingApp] = useState<App | null>(null);

  // useEffect = runs code when component loads (like __init__ method)
  useEffect(() => {
    loadApps();
  }, []); // Empty array means "run once when component mounts"

  // Async function to load data (like your service methods)
  async function loadApps() {
    try {
      setLoading(true);
      const data = await apiService.getApps();
      setApps(data); // This triggers a re-render!
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load apps');
    } finally {
      setLoading(false);
    }
  }

  // Handle delete (like your delete endpoint)
  async function handleDelete(appId: number) {
    if (!confirm('Are you sure you want to delete this app?')) return;
    
    try {
      await apiService.deleteApp(appId);
      // Remove from state (optimistic update)
      setApps(apps.filter(app => app.app_id !== appId));
    } catch (err) {
      alert('Failed to delete app');
    }
  }

  // Handle create/edit app
  async function handleSaveApp(data: { name: string }) {
    try {
      if (editingApp) {
        // Update existing app
        const updatedApp = await apiService.updateApp(editingApp.app_id, data);
        setApps(apps.map(app => 
          app.app_id === editingApp.app_id ? updatedApp : app
        ));
      } else {
        // Create new app
        const newApp = await apiService.createApp(data);
        setApps([...apps, newApp]);
      }
      
      // Close modal and reset state
      setIsModalOpen(false);
      setEditingApp(null);
    } catch (err) {
      // Error handling is done in the form component
      throw err;
    }
  }

  // Open create modal
  function handleCreateApp() {
    setEditingApp(null);
    setIsModalOpen(true);
  }

  // Open edit modal
  function handleEditApp(app: App) {
    setEditingApp(app);
    setIsModalOpen(true);
  }

  // Close modal
  function handleCloseModal() {
    setIsModalOpen(false);
    setEditingApp(null);
  }

  // Render loading state
  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="text-lg">Loading apps...</div>
      </div>
    );
  }

  // Render error state
  if (error) {
    return (
      <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
        <strong>Error:</strong> {error}
        <button 
          onClick={loadApps}
          className="ml-4 bg-red-500 text-white px-3 py-1 rounded hover:bg-red-600"
        >
          Retry
        </button>
      </div>
    );
  }

  // Main render - JSX looks like HTML but it's JavaScript!
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold text-gray-900">Apps</h1>
        <button 
          onClick={handleCreateApp}
          className="bg-blue-500 hover:bg-blue-600 text-white px-4 py-2 rounded-lg"
        >
          Create App
        </button>
      </div>

      {/* Apps Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {apps.map(app => (
          <div key={app.app_id} className="bg-white rounded-lg shadow-md p-6 border">
            <div className="flex justify-between items-start mb-4">
              <h3 className="text-xl font-semibold text-gray-900">{app.name}</h3>
              <div className="flex space-x-2">
                <button 
                  onClick={() => handleEditApp(app)}
                  className="text-blue-600 hover:text-blue-800"
                >
                  Edit
                </button>
                <button 
                  onClick={() => handleDelete(app.app_id)}
                  className="text-red-600 hover:text-red-800"
                >
                  Delete
                </button>
              </div>
            </div>
            
            <div className="text-sm text-gray-600">
              <p>Created: {new Date(app.created_at).toLocaleDateString()}</p>
              <p>ID: {app.app_id}</p>
            </div>
            
            <div className="mt-4">
              <Link 
                to={`/apps/${app.app_id}`}
                className="block w-full bg-gray-100 hover:bg-gray-200 text-gray-800 py-2 px-4 rounded text-center"
              >
                Manage App
              </Link>
            </div>
          </div>
        ))}
      </div>

      {/* Empty State */}
      {apps.length === 0 && (
        <div className="text-center py-12">
          <div className="text-gray-500 text-lg mb-4">No apps found</div>
          <button 
            onClick={handleCreateApp}
            className="bg-blue-500 hover:bg-blue-600 text-white px-6 py-3 rounded-lg"
          >
            Create Your First App
          </button>
        </div>
      )}

      {/* Create/Edit Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={handleCloseModal}
        title={editingApp ? 'Edit App' : 'Create New App'}
      >
        <AppForm
          app={editingApp}
          onSubmit={handleSaveApp}
          onCancel={handleCloseModal}
        />
      </Modal>
    </div>
  );
}

export default AppsPage; 