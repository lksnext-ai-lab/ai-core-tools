import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { toast } from "sonner";
import { Pencil, Plug, Plus, Trash2, Webhook } from "lucide-react";
import Alert from "../../components/ui/Alert";
import { Badge } from "../../components/ui/Badge";
import { apiService, type OutputDestination } from "../../services/api";
import { AppRole } from "../../types/roles";
import { useAppRole } from "../../hooks/useAppRole";
import ActionDropdown from "../../components/ui/ActionDropdown";
import ConfirmationModal from "../../components/ui/ConfirmationModal";
import Modal from "../../components/ui/Modal";
import ReadOnlyBanner from "../../components/ui/ReadOnlyBanner";
import Table from "../../components/ui/Table";
import OutputChannelWizard from "../../components/output/OutputChannelWizard";
import { contentModeLabels } from "../../components/output/outputChannelForm";
import { Spinner } from "../../components/ui/Spinner";
import { LoadingState } from "../../components/ui/LoadingState";
import Title from "../../components/ui/Title";
import { ButtonApp } from "../../components/ui/ButtonApp";
import BackgroundImage from "../../components/ui/BackgroundImage";

export default function OutputDestinationsPage() {
  const { appId } = useParams();
  const appIdNumber = Number.parseInt(appId ?? "0", 10);
  const { hasMinRole, userRole } = useAppRole(appId);
  const canEdit = hasMinRole(AppRole.EDITOR);
  const [destinations, setDestinations] = useState<OutputDestination[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [isWizardOpen, setIsWizardOpen] = useState(false);
  const [editingDestination, setEditingDestination] =
    useState<OutputDestination | null>(null);
  const [testingId, setTestingId] = useState<number | null>(null);
  const [testDestinationName, setTestDestinationName] = useState("");
  const [isTestModalOpen, setIsTestModalOpen] = useState(false);
  const [testResult, setTestResult] = useState<{
    success: boolean;
    message: string;
  } | null>(null);
  const [destinationToDelete, setDestinationToDelete] =
    useState<OutputDestination | null>(null);
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
    void apiService
      .getOutputDestinations(appIdNumber)
      .then((items) => {
        if (active) setDestinations(items);
      })
      .catch((error: unknown) => {
        if (active)
          setLoadError(
            error instanceof Error
              ? error.message
              : "No se pudieron cargar los canales de salida",
          );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
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
      const result = await apiService.testOutputDestination(
        appIdNumber,
        destination.id,
      );
      setTestResult({
        success: result.accepted,
        message: result.accepted
          ? `El canal aceptó la notificación de prueba (HTTP ${result.http_status}).`
          : `El canal no aceptó la notificación de prueba (HTTP ${result.http_status}).`,
      });
    } catch (error) {
      setTestResult({
        success: false,
        message:
          error instanceof Error
            ? error.message
            : "No se pudo enviar la prueba",
      });
    } finally {
      setTestingId(null);
    }
  };

  const deleteDestination = async () => {
    if (!destinationToDelete || deletingId !== null) return;
    setDeletingId(destinationToDelete.id);
    try {
      await apiService.deleteOutputDestination(
        appIdNumber,
        destinationToDelete.id,
      );
      setDestinations((items) =>
        items.filter((item) => item.id !== destinationToDelete.id),
      );
      setDestinationToDelete(null);
      toast.success("Canal de salida eliminado");
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "No se pudo eliminar el canal",
      );
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <Title
          variant="titSecundario"
          titulo="Output Channels"
          subtitulo="Gestiona los canales de Teams y webhooks disponibles para las tareas programadas."
        />
        {canEdit && (
          <ButtonApp
            label="Añadir canal"
            type="button"
            onClick={() => openWizard()}
            disabled={loading || Boolean(loadError)}
            icon={<Plus className="h-4 w-4" aria-hidden="true" />}
            variant="primary"
            size="medium"
          />
        )}
      </div>
      {!canEdit && (
        <ReadOnlyBanner userRole={userRole} minRole={AppRole.EDITOR} />
      )}
      {loadError ? (
        <Alert
          type="error"
          message={
            <>
              {loadError}
              <button
                type="button"
                onClick={() => setReloadKey((value) => value + 1)}
                className="mt-2 block font-medium underline"
              >
                Reintentar
              </button>
            </>
          }
        />
      ) : (
        <Table<OutputDestination>
          data={destinations}
          loading={loading}
          keyExtractor={(destination) => destination.id}
          columns={[
            {
              header: "Nombre",
              render: (destination) => (
                <div className="flex items-center">
                  <BackgroundImage icon={Webhook} variant="marron" iconSize={20} className="mr-2" />
                  {canEdit ? (
                    <button
                      type="button"
                      onClick={() => openWizard(destination)}
                      className="text-left text-sm font-medium text-fg dark:text-fg-dark"
                    >
                      {destination.name}
                    </button>
                  ) : (
                    <span className="text-sm font-medium text-fg dark:text-fg-dark">
                      {destination.name}
                    </span>
                  )}
                </div>
              ),
            },
            {
              header: "Proveedor",
              render: (destination) => (
                <Badge
                  label={destination.provider_key === "webhook" ? "Webhook HTTP" : "Teams Workflow"}
                  variant={destination.provider_key === "webhook" ? "default" : "info"}
                />
              ),
            },
            {
              header: "Autenticación",
              render: (destination) => (
                <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
                  {destination.provider_key === "teams_workflow"
                    ? "URL secreta"
                    : destination.public_config.auth_mode === "hmac_sha256"
                      ? "HMAC-SHA256"
                      : destination.public_config.auth_mode === "bearer"
                        ? "Bearer token"
                        : "Sin autenticación"}
                </span>
              ),
            },
            {
              header: "Adjuntos",
              render: (destination) => (
                <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
                  {destination.provider_key !== "webhook"
                    ? "Enlaces"
                    : destination.public_config.include_attachments
                      ? "Archivos incluidos"
                      : "Desactivados"}
                </span>
              ),
            },
            {
              header: "Contenido",
              render: (destination) => (
                <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
                  {
                    contentModeLabels(
                      destination.provider_key === "webhook"
                        ? "webhook"
                        : "teams_workflow",
                    )[destination.content_mode ?? "result"]
                  }
                </span>
              ),
            },
            {
              header: "Creado",
              render: (destination) => (
                <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
                  {new Date(destination.created_at).toLocaleDateString()}
                </span>
              ),
            },
            {
              header: "Acciones",
              className: "relative px-6 py-4 whitespace-nowrap",
              render: (destination) =>
                canEdit ? (
                  <ActionDropdown
                    size="sm"
                    triggerText="Acciones"
                    triggerAriaLabel={`Acciones de ${destination.name}`}
                    actions={[
                      {
                        label:
                          testingId === destination.id
                            ? "Enviando…"
                            : "Probar destino",
                        onClick: () => {
                          void testDestination(destination);
                        },
                        icon:
                          testingId === destination.id ? (
                            <Spinner size="sm" tone="current" />
                          ) : (
                            <Plug className="h-4 w-4" />
                          ),
                        disabled: testingId !== null,
                        variant: "primary",
                      },
                      {
                        label: "Editar",
                        onClick: () => openWizard(destination),
                        icon: <Pencil className="h-4 w-4" />,
                      },
                      {
                        label: "Eliminar",
                        onClick: () => setDestinationToDelete(destination),
                        icon: <Trash2 className="h-4 w-4" />,
                        disabled: deletingId !== null,
                        variant: "danger",
                      },
                    ]}
                  />
                ) : (
                  <span className="text-sm text-gray-400">Solo lectura</span>
                ),
            },
          ]}
          emptyIcon={<Webhook className="mx-auto h-12 w-12 text-gray-300" />}
          emptyMessage="No hay canales de salida"
          emptySubMessage="Añade tu primer canal para enviar resultados a Teams o a un webhook."
        />
      )}
      {!loading && !loadError && destinations.length === 0 && canEdit && (
        <div className="text-center">
          <ButtonApp
            label="Añadir primer canal"
            type="button"
            onClick={() => openWizard()}
            icon={<Plus className="h-4 w-4" aria-hidden="true" />}
            variant="primary"
            size="medium"
            className="mx-auto"
          />
        </div>
      )}
      <OutputChannelWizard
        isOpen={isWizardOpen && canEdit}
        appId={appIdNumber}
        destination={editingDestination}
        destinations={destinations}
        onClose={() => setIsWizardOpen(false)}
        onSaved={(saved) => {
          setDestinations((items) =>
            editingDestination
              ? items.map((item) => (item.id === saved.id ? saved : item))
              : [...items, saved],
          );
          toast.success(
            editingDestination
              ? "Canal de salida actualizado"
              : "Canal de salida creado",
          );
        }}
      />
      <Modal
        isOpen={isTestModalOpen}
        onClose={() => setIsTestModalOpen(false)}
        title={`Prueba de conexión: ${testDestinationName}`}
        size="medium"
      >
        {testingId !== null ? (
          <LoadingState
            variant="section"
            message="Enviando notificación de prueba…"
          />
        ) : (
          testResult && (
            <Alert
              type={testResult.success ? "success" : "error"}
              title={testResult.success ? "Conexión correcta" : "Error de conexión"}
              message={testResult.message}
              polite={testResult.success}
            />
          )
        )}
      </Modal>
      <ConfirmationModal
        isOpen={destinationToDelete !== null}
        title="Eliminar canal de salida"
        message={
          destinationToDelete
            ? `Se eliminará «${destinationToDelete.name}» y dejará de enviar notificaciones en las tareas vinculadas. El historial de entregas se conservará.`
            : ""
        }
        confirmLabel="Eliminar canal"
        isLoading={deletingId !== null}
        onConfirm={() => {
          void deleteDestination();
        }}
        onCancel={() => {
          if (deletingId === null) setDestinationToDelete(null);
        }}
      />
    </div>
  );
}
