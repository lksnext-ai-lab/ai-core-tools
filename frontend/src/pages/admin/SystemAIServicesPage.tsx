import React, { useEffect, useState } from 'react';
import { apiService } from '../../services/api';
import AIServiceForm from '../../components/forms/AIServiceForm';
import type { ServiceFormData } from '../../components/forms/BaseServiceForm';

interface SystemAIService {
  service_id: number;
  name: string;
  provider: string;
  model_name: string;
  api_key: string;
  base_url: string;
  is_system: boolean;
}

const SystemAIServicesPage: React.FC = () => {
  const [services, setServices] = useState<SystemAIService[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingService, setEditingService] = useState<SystemAIService | null>(null);

  const fetchServices = async () => {
    try {
      const data = await apiService.getSystemAIServices();
      setServices(data as SystemAIService[]);
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

  const handleOpenEdit = (svc: SystemAIService) => {
    setEditingService(svc);
    setShowForm(true);
  };

  const handleCancel = () => {
    setShowForm(false);
    setEditingService(null);
  };

  const handleSave = async (data: ServiceFormData) => {
    if (editingService) {
      await apiService.updateSystemAIService(editingService.service_id, data);
    } else {
      await apiService.createSystemAIService(data);
    }
    handleCancel();
    await fetchServices();
  };

  const handleDelete = async (serviceId: number) => {
    if (!confirm('Delete this system AI service?')) return;
    try {
      await apiService.deleteSystemAIService(serviceId);
      await fetchServices();
    } catch (err: any) {
      alert(err?.message || 'Failed to delete service');
    }
  };

  if (isLoading) return <div className="p-8 text-gray-500">Loading system AI services...</div>;
  if (error) return <div className="p-8 text-red-600">{error}</div>;

  if (showForm) {
    return (
      <div className="max-w-2xl mx-auto p-8">
        <AIServiceForm
          aiService={editingService}
          onSubmit={handleSave}
          onCancel={handleCancel}
        />
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto p-8">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">System AI Services</h1>
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
                <td colSpan={4} className="px-4 py-6 text-center text-gray-400">No system AI services configured.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default SystemAIServicesPage;
