import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { apiService } from '../services/api';
import SiloForm from '../components/forms/SiloForm';

// Define the Silo type
interface Silo {
  silo_id: number;
  name: string;
  type?: string;
  created_at?: string;
  docs_count: number;
}

function SiloFormPage() {
  const { appId, siloId } = useParams();
  const navigate = useNavigate();
  const [silo, setSilo] = useState<Silo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const isEditing = siloId && siloId !== 'new';

  // Load silo data if editing
  useEffect(() => {
    if (isEditing && appId && siloId) {
      loadSilo();
    } else {
      setLoading(false);
    }
  }, [appId, siloId, isEditing]);

  async function loadSilo() {
    if (!appId || !siloId) return;
    
    try {
      setLoading(true);
      setError(null);
      const response = await apiService.getSilo(parseInt(appId), parseInt(siloId));
      setSilo(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load silo');
      console.error('Error loading silo:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(formData: any) {
    if (!appId) return;

    try {
      if (isEditing && siloId) {
        // Update existing silo
        await apiService.updateSilo(parseInt(appId), parseInt(siloId), formData);
      } else {
        // Create new silo
        await apiService.createSilo(parseInt(appId), formData);
      }
      
      // Navigate back to silos list
      navigate(`/apps/${appId}/silos`);
    } catch (err) {
      throw new Error(err instanceof Error ? err.message : 'Failed to save silo');
    }
  }

  function handleCancel() {
    navigate(`/apps/${appId}/silos`);
  }

  if (loading) {
    return (
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              {isEditing ? 'Edit Silo' : 'Create New Silo'}
            </h1>
            <p className="text-gray-600">Configure your silo settings</p>
          </div>
        </div>

        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-yellow-600"></div>
          <span className="ml-2">Loading silo...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              {isEditing ? 'Edit Silo' : 'Create New Silo'}
            </h1>
            <p className="text-gray-600">Configure your silo settings</p>
          </div>
        </div>

        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <div className="flex">
            <span className="text-red-400 text-xl mr-3">⚠️</span>
            <div>
              <h3 className="text-sm font-medium text-red-800">Error Loading Silo</h3>
              <p className="text-sm text-red-600 mt-1">{error}</p>
              <button 
                onClick={() => navigate(`/apps/${appId}/silos`)}
                className="mt-2 text-sm text-red-800 hover:text-red-900 underline"
              >
                Back to Silos
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            {isEditing ? 'Edit Silo' : 'Create New Silo'}
          </h1>
          <p className="text-gray-600">Configure your silo settings</p>
        </div>
        <button
          onClick={handleCancel}
          className="px-4 py-2 text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg"
        >
          ← Back to Silos
        </button>
      </div>

      {/* Silo Form */}
      <SiloForm
        silo={silo || undefined}
        onSubmit={handleSubmit}
        onCancel={handleCancel}
        loading={loading}
      />
    </div>
  );
}

export default SiloFormPage; 