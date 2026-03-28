import React, { useEffect, useState } from 'react';
import { apiService } from '../../services/api';
import EmbeddingServiceForm from '../../components/forms/EmbeddingServiceForm';
import type { ServiceFormData } from '../../components/forms/BaseServiceForm';

interface SystemEmbeddingService {
  service_id: number;
  name: string;
  provider: string;
  model_name: string;
  api_key: string;
  base_url: string;
  is_system: boolean;
}

interface AffectedSilo {
  silo_id: number;
  silo_name: string;
  app_id: number;
  app_name: string;
}

interface DeletionImpact {
  service_id: number;
  service_name: string;
  affected_silos_count: number;
  affected_apps_count: number;
  affected_silos: AffectedSilo[];
}

const SystemEmbeddingServicesPage: React.FC = () => {
  const [services, setServices] = useState<SystemEmbeddingService[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingService, setEditingService] = useState<SystemEmbeddingService | null>(null);

  // Deletion confirmation state
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deletionImpact, setDeletionImpact] = useState<DeletionImpact | null>(null);
  const [pendingDeleteId, setPendingDeleteId] = useState<number | null>(null);

  const fetchServices = async () => {
    try {
      const data = await apiService.getSystemEmbeddingServices();
      setServices(data as SystemEmbeddingService[]);
    } catch (err: any) {
      setError(err?.message || 'Failed to load services');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => { fetchServices(); }, []);

  const handleOpenCreate = () => {
    setEditingService(null);
    setShowForm(true);
  };

  const handleOpenEdit = (svc: SystemEmbeddingService) => {
    setEditingService(svc);
    setShowForm(true);
  };

  const handleCancel = () => {
    setShowForm(false);
    setEditingService(null);
  };

  const handleSave = async (data: ServiceFormData) => {
    if (editingService) {
      await apiService.updateSystemEmbeddingService(editingService.service_id, data);
    } else {
      await apiService.createSystemEmbeddingService(data);
    }
    handleCancel();
    await fetchServices();
  };

  const handleDelete = async (serviceId: number) => {
    try {
      const impact = await apiService.getSystemEmbeddingServiceImpact(serviceId) as DeletionImpact;
      setDeletionImpact(impact);
      setPendingDeleteId(serviceId);
      setShowDeleteConfirm(true);
    } catch (err: any) {
      alert(err?.message || 'Failed to check deletion impact');
    }
  };

  const handleConfirmDelete = async () => {
    if (pendingDeleteId === null) return;
    try {
      await apiService.deleteSystemEmbeddingService(pendingDeleteId);
      setShowDeleteConfirm(false);
      setDeletionImpact(null);
      setPendingDeleteId(null);
      await fetchServices();
    } catch (err: any) {
      alert(err?.message || 'Failed to delete service');
    }
  };

  const handleCancelDelete = () => {
    setShowDeleteConfirm(false);
    setDeletionImpact(null);
    setPendingDeleteId(null);
  };

  if (isLoading) return <div className="p-8 text-gray-500">Loading system embedding services...</div>;
  if (error) return <div className="p-8 text-red-600">{error}</div>;

  if (showForm) {
    const formService = editingService
      ? {
          service_id: editingService.service_id,
          name: editingService.name,
          provider: editingService.provider,
          model_name: editingService.model_name,
          api_key: '',
          base_url: '',
          created_at: '',
          available_providers: [],
        }
      : null;

    return (
      <div className="max-w-2xl mx-auto p-8">
        <EmbeddingServiceForm
          embeddingService={formService}
          onSubmit={handleSave}
          onCancel={handleCancel}
        />
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto p-8">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">System Embedding Services</h1>
        <button
          onClick={handleOpenCreate}
          className="bg-blue-600 text-white rounded px-4 py-2 text-sm font-medium hover:bg-blue-700"
        >
          Add service
        </button>
      </div>

      <div className="bg-white shadow rounded-lg overflow-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-500 uppercase text-xs">
            <tr>
              <th className="px-4 py-3 text-left">Name</th>
              <th className="px-4 py-3 text-left">Provider</th>
              <th className="px-4 py-3 text-left">Model</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {services.map(svc => (
              <tr key={svc.service_id} className="hover:bg-gray-50">
                <td className="px-4 py-3">{svc.name}</td>
                <td className="px-4 py-3">{svc.provider}</td>
                <td className="px-4 py-3">{svc.model_name}</td>
                <td className="px-4 py-3 text-right flex gap-3 justify-end">
                  <button
                    onClick={() => handleOpenEdit(svc)}
                    className="text-xs text-blue-600 hover:underline"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => handleDelete(svc.service_id)}
                    className="text-xs text-red-600 hover:underline"
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {services.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-6 text-center text-gray-400">No system embedding services configured.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Deletion confirmation dialog */}
      {showDeleteConfirm && deletionImpact && (
        <div className="fixed inset-0 bg-black bg-opacity-40 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full p-6">
            <h2 className="text-lg font-semibold mb-3">Delete System Embedding Service</h2>
            {deletionImpact.affected_silos_count > 0 ? (
              <div className="mb-4">
                <p className="text-sm text-gray-700 mb-2">
                  This embedding service is used by{' '}
                  <span className="font-semibold">{deletionImpact.affected_silos_count} silo{deletionImpact.affected_silos_count !== 1 ? 's' : ''}</span>{' '}
                  across{' '}
                  <span className="font-semibold">{deletionImpact.affected_apps_count} app{deletionImpact.affected_apps_count !== 1 ? 's' : ''}</span>.
                  Deleting it will leave those silos without an embedding service.
                </p>
                {deletionImpact.affected_silos.length < 20 && (
                  <ul className="text-xs text-gray-500 list-disc list-inside space-y-0.5">
                    {deletionImpact.affected_silos.map(s => (
                      <li key={s.silo_id}>{s.silo_name} ({s.app_name})</li>
                    ))}
                  </ul>
                )}
              </div>
            ) : (
              <p className="text-sm text-gray-700 mb-4">Delete this system embedding service?</p>
            )}
            <div className="flex gap-3 justify-end">
              <button
                onClick={handleCancelDelete}
                className="px-4 py-2 text-sm text-gray-600 border border-gray-300 rounded hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmDelete}
                className="px-4 py-2 text-sm text-white bg-red-600 rounded hover:bg-red-700"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default SystemEmbeddingServicesPage;
