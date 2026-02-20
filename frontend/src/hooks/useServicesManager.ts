import { useState, useEffect } from 'react';

type ApiFns<T> = {
  getAll: (appId: number) => Promise<T[]>;
  getOne?: (appId: number, id: number) => Promise<any>;
  create: (appId: number, data: any) => Promise<any>;
  update?: (appId: number, id: number, data: any) => Promise<any>;
  delete: (appId: number, id: number) => Promise<any>;
  copy?: (appId: number, id: number) => Promise<any>;
};

type CacheFns<T> = {
  get: (appId: string) => T[] | null | undefined;
  set: (appId: string, data: T[]) => void;
  invalidate: (appId: string) => void;
};

export function useServicesManager<T = any>(appId: string | undefined, api: ApiFns<T>, cache: CacheFns<T>) {
  const [services, setServices] = useState<T[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingService, setEditingService] = useState<any>(null);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appId]);

  async function load() {
    if (!appId) return;

    const cached = cache.get(appId);
    if (cached) {
      setServices(cached);
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const response = await api.getAll(parseInt(appId));
      setServices(response || []);
      cache.set(appId, response || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load');
      // eslint-disable-next-line no-console
      console.error('Error loading services:', err);
    } finally {
      setLoading(false);
    }
  }

  async function forceReload() {
    if (!appId) return;
    try {
      setLoading(true);
      setError(null);
      const response = await api.getAll(parseInt(appId));
      setServices(response || []);
      cache.set(appId, response || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load');
      // eslint-disable-next-line no-console
      console.error('Error reloading services:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(id: number) {
    if (!confirm('Are you sure you want to delete this item?')) return;
    if (!appId) return;
    try {
      await api.delete(parseInt(appId), id);
      const newServices = services.filter((s: any) => s.service_id !== id);
      setServices(newServices);
      cache.set(appId, newServices);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete item');
      // eslint-disable-next-line no-console
      console.error('Error deleting item:', err);
    }
  }

  async function handleEdit(id: number) {
    if (!appId || !api.getOne) return;
    try {
      const item = await api.getOne(parseInt(appId), id);
      setEditingService(item);
      setIsModalOpen(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load item');
      // eslint-disable-next-line no-console
      console.error('Error loading item:', err);
    }
  }

  async function handleCopy(id: number) {
    if (!appId || !api.copy) return;
    try {
      await api.copy(parseInt(appId), id);
      cache.invalidate(appId);
      await forceReload();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to copy item');
      // eslint-disable-next-line no-console
      console.error('Error copying item:', err);
    }
  }

  async function handleSave(data: any) {
    if (!appId) return;
    try {
      if (editingService && editingService.service_id !== 0 && api.update) {
        await api.update(parseInt(appId), editingService.service_id, data);
        cache.invalidate(appId);
        await forceReload();
      } else {
        await api.create(parseInt(appId), data);
        cache.invalidate(appId);
        await forceReload();
      }
      setIsModalOpen(false);
      setEditingService(null);
    } catch (err) {
      throw new Error(err instanceof Error ? err.message : 'Failed to save item');
    }
  }

  function handleCreate() {
    setEditingService(null);
    setIsModalOpen(true);
  }

  function handleClose() {
    setIsModalOpen(false);
    setEditingService(null);
  }

  return {
    services,
    loading,
    error,
    isModalOpen,
    editingService,
    load,
    forceReload,
    handleDelete,
    handleEdit,
    handleCopy,
    handleSave,
    handleCreate,
    handleClose,
    setIsModalOpen,
    setEditingService,
  };
}
