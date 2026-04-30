import { useState, useEffect } from 'react';
import { toast } from 'sonner';
import { useConfirm } from '../contexts/ConfirmContext';
import { useApiMutation } from './useApiMutation';
import { MESSAGES, errorMessage } from '../constants/messages';

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

interface ServicesManagerOptions {
  /** Singular entity label used in toasts and confirmation dialogs (e.g. "AI service"). */
  readonly entity?: string;
}

export function useServicesManager<T = any>(
  appId: string | undefined,
  api: ApiFns<T>,
  cache: CacheFns<T>,
  options: ServicesManagerOptions = {},
) {
  const entity = options.entity ?? 'item';
  const confirm = useConfirm();
  const mutate = useApiMutation();
  const [services, setServices] = useState<T[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingService, setEditingService] = useState<any>(null);

  useEffect(() => {
    load();
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
      const response = await api.getAll(Number.parseInt(appId));
      setServices(response || []);
      cache.set(appId, response || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load');
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
      const response = await api.getAll(Number.parseInt(appId));
      setServices(response || []);
      cache.set(appId, response || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load');
      console.error('Error reloading services:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(id: number) {
    if (!appId) return;

    const ok = await confirm({
      title: MESSAGES.CONFIRM_DELETE_TITLE(entity),
      message: MESSAGES.CONFIRM_DELETE_MESSAGE(entity),
      variant: 'danger',
      confirmLabel: 'Delete',
    });
    if (!ok) return;

    const result = await mutate(
      () => api.delete(Number.parseInt(appId), id),
      {
        loading: MESSAGES.DELETING(entity),
        success: MESSAGES.DELETED(entity),
        error: (err) => errorMessage(err, MESSAGES.DELETE_FAILED(entity)),
      },
    );
    if (result === undefined) return;

    const newServices = services.filter((s: any) => s.service_id !== id);
    setServices(newServices);
    cache.set(appId, newServices);
  }

  async function handleEdit(id: number) {
    if (!appId || !api.getOne) return;
    try {
      const item = await api.getOne(Number.parseInt(appId), id);
      setEditingService(item);
      setIsModalOpen(true);
    } catch (err) {
      const message = errorMessage(err, MESSAGES.LOAD_FAILED(entity));
      toast.error(message);
      console.error(`Error loading ${entity}:`, err);
    }
  }

  async function handleCopy(id: number) {
    if (!appId || !api.copy) return;

    const result = await mutate(
      () => api.copy!(Number.parseInt(appId), id),
      {
        loading: MESSAGES.COPYING(entity),
        success: MESSAGES.COPIED(entity),
        error: (err) => errorMessage(err, MESSAGES.COPY_FAILED(entity)),
      },
    );
    if (result === undefined) return;

    cache.invalidate(appId);
    await forceReload();
  }

  async function handleSave(data: any) {
    if (!appId) return;

    const isUpdate = Boolean(editingService && editingService.service_id !== 0 && api.update);

    const result = await mutate(
      () =>
        isUpdate
          ? api.update!(Number.parseInt(appId), editingService.service_id, data)
          : api.create(Number.parseInt(appId), data),
      {
        loading: isUpdate ? MESSAGES.UPDATING(entity) : MESSAGES.CREATING(entity),
        success: isUpdate ? MESSAGES.UPDATED(entity) : MESSAGES.CREATED(entity),
        error: (err) => errorMessage(err, MESSAGES.SAVE_FAILED(entity)),
      },
    );
    if (result === undefined) return;

    cache.invalidate(appId);
    await forceReload();
    setIsModalOpen(false);
    setEditingService(null);
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
