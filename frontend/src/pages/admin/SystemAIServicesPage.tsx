import React, { useEffect, useState } from 'react';
import { apiService } from '../../services/api';

interface SystemAIService {
  id: number;
  name: string;
  provider: string;
  model: string;
  is_active: boolean;
}

const SystemAIServicesPage: React.FC = () => {
  const [services, setServices] = useState<SystemAIService[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: '', provider: '', model: '', api_key_encrypted: '', is_active: true });
  const [saving, setSaving] = useState(false);

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

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await apiService.createSystemAIService(form);
      setShowForm(false);
      setForm({ name: '', provider: '', model: '', api_key_encrypted: '', is_active: true });
      await fetchServices();
    } catch (err: any) {
      alert(err?.message || 'Failed to create service');
    } finally {
      setSaving(false);
    }
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

  const handleToggle = async (service: SystemAIService) => {
    try {
      await apiService.updateSystemAIService(service.id, { is_active: !service.is_active });
      await fetchServices();
    } catch (err: any) {
      alert(err?.message || 'Failed to update service');
    }
  };

  if (isLoading) return <div className="p-8 text-gray-500">Loading system AI services...</div>;
  if (error) return <div className="p-8 text-red-600">{error}</div>;

  return (
    <div className="max-w-4xl mx-auto p-8">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">System AI Services</h1>
        <button
          onClick={() => setShowForm(!showForm)}
          className="bg-blue-600 text-white rounded px-4 py-2 text-sm font-medium hover:bg-blue-700"
        >
          {showForm ? 'Cancel' : 'Add service'}
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} className="bg-white border rounded-lg p-5 mb-6 shadow-sm space-y-3">
          <h2 className="font-semibold">New system AI service</h2>
          {(['name', 'provider', 'model', 'api_key_encrypted'] as const).map(field => (
            <div key={field}>
              <label className="block text-sm font-medium text-gray-700 mb-0.5 capitalize">
                {field.replace(/_/g, ' ')}
              </label>
              <input
                type={field === 'api_key_encrypted' ? 'password' : 'text'}
                value={form[field]}
                onChange={e => setForm(prev => ({ ...prev, [field]: e.target.value }))}
                required={field !== 'api_key_encrypted'}
                className="w-full border rounded px-3 py-1.5 text-sm"
              />
            </div>
          ))}
          <button
            type="submit"
            disabled={saving}
            className="bg-blue-600 text-white rounded px-4 py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
          >
            {saving ? 'Creating...' : 'Create'}
          </button>
        </form>
      )}

      <div className="bg-white shadow rounded-lg overflow-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-500 uppercase text-xs">
            <tr>
              <th className="px-4 py-3 text-left">Name</th>
              <th className="px-4 py-3 text-left">Provider</th>
              <th className="px-4 py-3 text-left">Model</th>
              <th className="px-4 py-3 text-center">Active</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {services.map(svc => (
              <tr key={svc.id} className="hover:bg-gray-50">
                <td className="px-4 py-3">{svc.name}</td>
                <td className="px-4 py-3">{svc.provider}</td>
                <td className="px-4 py-3">{svc.model}</td>
                <td className="px-4 py-3 text-center">
                  <button
                    onClick={() => handleToggle(svc)}
                    className={`text-xs rounded px-2 py-0.5 font-medium ${svc.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}
                  >
                    {svc.is_active ? 'Active' : 'Inactive'}
                  </button>
                </td>
                <td className="px-4 py-3 text-right">
                  <button
                    onClick={() => handleDelete(svc.id)}
                    className="text-xs text-red-600 hover:underline"
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {services.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-gray-400">No system AI services configured.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default SystemAIServicesPage;
