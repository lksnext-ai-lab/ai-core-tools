import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Loader2, Pencil, Plug, Plus, Trash2, Webhook } from 'lucide-react';
import { apiService, type OutputDestination } from '../../services/api';
import { AppRole } from '../../types/roles';
import { useAppRole } from '../../hooks/useAppRole';
import ActionDropdown from '../../components/ui/ActionDropdown';
import ConfirmationModal from '../../components/ui/ConfirmationModal';
import Modal from '../../components/ui/Modal';
import ReadOnlyBanner from '../../components/ui/ReadOnlyBanner';
import Table from '../../components/ui/Table';
import OutputChannelWizard from '../../components/output/OutputChannelWizard';
import { contentModeLabels } from '../../components/output/outputChannelForm';

export default function OutputDestinationsPage() {
  const { appId } = useParams();
  const appIdNumber = Number.parseInt(appId ?? '0', 10);
  const { hasMinRole, userRole } = useAppRole(appId);
  const canEdit = hasMinRole(AppRole.EDITOR);
  const [destinations, setDestinations] = useState<OutputDestination[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [isWizardOpen, setIsWizardOpen] = useState(false);
  const [editingDestination, setEditingDestination] = useState<OutputDestination | null>(null);
  const [testingId, setTestingId] = useState<number | null>(null);
  const [testDestinationName, setTestDestinationName] = useState('');
  const [isTestModalOpen, setIsTestModalOpen] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [destinationToDelete, setDestinationToDelete] = useState<OutputDestination | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setDestinations([]);
    setLoadError(null);
    setIsWizardOpen(false);
    setIsTestModalOpen(false);
    setDestinationToDelete(null);
    if (!appIdNumber) {
      setLoading(false);
      return;
    }
    void apiService.getOutputDestinations(appIdNumber).then((items) => {
      if (active) setDestinations(items);
    }).catch((error: unknown) => {
      if (active) setLoadError(error instanceof Error ? error.message : 'No se pudieron cargar los canales de salida');
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [appIdNumber, reloadKey]);

  const openWizard = (destination: OutputDestination | null = null) => {
    setEditingDestination(destination);
    setIsWizardOpen(true);
  };

  const testDestination = async (destination: OutputDestination) => {
    if (testingId !== null) return;
    setTestingId(destination.id);
    setTestDestinationName(destination.name);
    setTestResult(null);
    setIsTestModalOpen(true);
    try {
      const result = await apiService.testOutputDestination(appIdNumber, destination.id);
      setTestResult({ success: result.accepted, message: result.accepted
        ? `El canal aceptó la notificación de prueba (HTTP ${result.http_status}).`
        : `El canal no aceptó la notificación de prueba (HTTP ${result.http_status}).` });
    } catch (error) {
      setTestResult({ success: false, message: error instanceof Error ? error.message : 'No se pudo enviar la prueba' });
    } finally { setTestingId(null); }
  };

  const deleteDestination = async () => {
    if (!destinationToDelete || deletingId !== null) return;
    setDeletingId(destinationToDelete.id);
    try {
      await apiService.deleteOutputDestination(appIdNumber, destinationToDelete.id);
      setDestinations((items) => items.filter((item) => item.id !== destinationToDelete.id));
      setDestinationToDelete(null);
      toast.success('Canal de salida eliminado');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'No se pudo eliminar el canal');
    } finally { setDeletingId(null); }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-gray-900">Output Channels</h2>
          <p className="mt-1 text-sm text-gray-600">Gestiona los canales de Teams y webhooks disponibles para las tareas programadas.</p>
        </div>
        {canEdit && <button type="button" onClick={() => openWizard()} disabled={loading || Boolean(loadError)} className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 disabled:opacity-50">
          <Plus className="h-4 w-4" />Añadir canal
        </button>}
      </div>
      {!canEdit && <ReadOnlyBanner userRole={userRole} minRole={AppRole.EDITOR} />}
      {loadError ? <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        <p>{loadError}</p><button type="button" onClick={() => setReloadKey((value) => value + 1)} className="mt-2 font-medium underline">Reintentar</button>
      </div> : <Table<OutputDestination>
        data={destinations} loading={loading} keyExtractor={(destination) => destination.id}
        columns={[
          { header: 'Nombre', render: (destination) => canEdit
            ? <button type="button" onClick={() => openWizard(destination)} className="text-left text-sm font-medium text-gray-900 transition-colors hover:text-blue-600">{destination.name}</button>
            : <span className="text-sm font-medium text-gray-900">{destination.name}</span> },
          { header: 'Proveedor', render: (destination) => <span className={`inline-flex rounded-full px-2 py-1 text-xs font-medium ${destination.provider_key === 'webhook' ? 'bg-purple-100 text-purple-800' : 'bg-blue-100 text-blue-800'}`}>{destination.provider_key === 'webhook' ? 'Webhook HTTP' : 'Teams Workflow'}</span> },
          { header: 'Autenticación', render: (destination) => <span className="text-sm text-gray-600">{destination.provider_key === 'teams_workflow' ? 'URL secreta' : destination.public_config.auth_mode === 'hmac_sha256' ? 'HMAC-SHA256' : destination.public_config.auth_mode === 'bearer' ? 'Bearer token' : 'Sin autenticación'}</span> },
          { header: 'Adjuntos', render: (destination) => <span className="text-sm text-gray-600">{destination.provider_key !== 'webhook' ? 'Enlaces' : destination.public_config.include_attachments ? 'Archivos incluidos' : 'Desactivados'}</span> },
          { header: 'Contenido', render: (destination) => <span className="text-sm text-gray-600">{contentModeLabels(destination.provider_key === 'webhook' ? 'webhook' : 'teams_workflow')[destination.content_mode ?? 'result']}</span> },
          { header: 'Creado', render: (destination) => <span className="text-sm text-gray-500">{new Date(destination.created_at).toLocaleDateString()}</span> },
          { header: 'Acciones', className: 'relative px-6 py-4 whitespace-nowrap', render: (destination) => canEdit ? <ActionDropdown size="sm" triggerText="Acciones" triggerAriaLabel={`Acciones de ${destination.name}`} actions={[
            { label: testingId === destination.id ? 'Enviando…' : 'Probar destino', onClick: () => { void testDestination(destination); }, icon: testingId === destination.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plug className="h-4 w-4" />, disabled: testingId !== null, variant: 'primary' },
            { label: 'Editar', onClick: () => openWizard(destination), icon: <Pencil className="h-4 w-4" /> },
            { label: 'Eliminar', onClick: () => setDestinationToDelete(destination), icon: <Trash2 className="h-4 w-4" />, disabled: deletingId !== null, variant: 'danger' },
          ]} /> : <span className="text-sm text-gray-400">Solo lectura</span> },
        ]}
        emptyIcon={<Webhook className="mx-auto h-12 w-12 text-gray-300" />}
        emptyMessage="No hay canales de salida"
        emptySubMessage="Añade tu primer canal para enviar resultados a Teams o a un webhook."
      />}
      {!loading && !loadError && destinations.length === 0 && canEdit && <div className="text-center"><button type="button" onClick={() => openWizard()} className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-white hover:bg-blue-700"><Plus className="h-4 w-4" />Añadir primer canal</button></div>}
      <OutputChannelWizard isOpen={isWizardOpen && canEdit} appId={appIdNumber} destination={editingDestination} destinations={destinations} onClose={() => setIsWizardOpen(false)} onSaved={(saved) => {
        setDestinations((items) => editingDestination ? items.map((item) => item.id === saved.id ? saved : item) : [...items, saved]);
        toast.success(editingDestination ? 'Canal de salida actualizado' : 'Canal de salida creado');
      }} />
      <Modal isOpen={isTestModalOpen} onClose={() => setIsTestModalOpen(false)} title={`Prueba de conexión: ${testDestinationName}`} size="medium">
        {testingId !== null ? <div role="status" className="flex items-center justify-center gap-3 py-8 text-gray-600"><Loader2 className="h-6 w-6 animate-spin text-blue-600" />Enviando notificación de prueba…</div>
          : testResult && <div role="status" className={`rounded-lg p-4 ${testResult.success ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'}`}><p className="font-medium">{testResult.success ? 'Conexión correcta' : 'Error de conexión'}</p><p className="mt-2 text-sm">{testResult.message}</p></div>}
      </Modal>
      <ConfirmationModal isOpen={destinationToDelete !== null} title="Eliminar canal de salida" message={destinationToDelete ? `Se eliminará «${destinationToDelete.name}» y dejará de enviar notificaciones en las tareas vinculadas. El historial de entregas se conservará.` : ''} confirmLabel="Eliminar canal" isLoading={deletingId !== null} onConfirm={() => { void deleteDestination(); }} onCancel={() => { if (deletingId === null) setDestinationToDelete(null); }} />
    </div>
  );
}
