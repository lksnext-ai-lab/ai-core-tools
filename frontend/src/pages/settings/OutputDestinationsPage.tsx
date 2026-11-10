import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
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
import { Spinner } from "../../components/ui/Spinner";
import { LoadingState } from "../../components/ui/LoadingState";
import Title from "../../components/ui/Title";
import { ButtonApp } from "../../components/ui/ButtonApp";
import BackgroundImage from "../../components/ui/BackgroundImage";

export default function OutputDestinationsPage() {
  const { t, i18n } = useTranslation("common");
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
              : t("outputDestinationsPage.loadFailed"),
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
          ? t("outputDestinationsPage.test.accepted", { status: result.http_status })
          : t("outputDestinationsPage.test.rejected", { status: result.http_status }),
      });
    } catch (error) {
      setTestResult({
        success: false,
        message:
          error instanceof Error
            ? error.message
            : t("outputDestinationsPage.test.sendFailed"),
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
      toast.success(t("outputDestinationsPage.deleted"));
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : t("outputDestinationsPage.deleteFailed"),
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
          titulo={t("outputDestinationsPage.title")}
          subtitulo={t("outputDestinationsPage.subtitle")}
        />
        {canEdit && (
          <ButtonApp
            label={t("outputDestinationsPage.add")}
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
                {t("outputDestinationsPage.retry")}
              </button>
            </>
          }
        />
      ) : (
        <Table<OutputDestination>
          data={destinations}
          stickyEdgeColumns
          loading={loading}
          keyExtractor={(destination) => destination.id}
          columns={[
            {
              header: t("outputDestinationsPage.columns.name"),
              render: (destination) => (
                <div className="flex items-center">
                  <BackgroundImage icon={Webhook} variant="marron" size={34} iconSize={17} className="mr-2" />
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
              header: t("outputDestinationsPage.columns.provider"),
              render: (destination) => (
                <Badge
                  label={destination.provider_key === "webhook"
                    ? t("outputDestinationsPage.providers.webhook")
                    : t("outputDestinationsPage.providers.teamsWorkflow")}
                  variant={destination.provider_key === "webhook" ? "default" : "info"}
                />
              ),
            },
            {
              header: t("outputDestinationsPage.columns.authentication"),
              render: (destination) => {
                let label = t("outputDestinationsPage.authentication.none");
                if (destination.provider_key === "teams_workflow") {
                  label = t("outputDestinationsPage.authentication.secretUrl");
                } else if (destination.public_config.auth_mode === "hmac_sha256") {
                  label = t("outputDestinationsPage.authentication.hmac");
                } else if (destination.public_config.auth_mode === "bearer") {
                  label = t("outputDestinationsPage.authentication.bearer");
                }
                return (
                  <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
                    {label}
                  </span>
                );
              },
            },
            {
              header: t("outputDestinationsPage.columns.attachments"),
              render: (destination) => {
                let label = t("outputDestinationsPage.attachments.links");
                if (destination.provider_key === "webhook") {
                  label = destination.public_config.include_attachments
                    ? t("outputDestinationsPage.attachments.included")
                    : t("outputDestinationsPage.attachments.disabled");
                }
                return (
                  <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
                    {label}
                  </span>
                );
              },
            },
            {
              header: t("outputDestinationsPage.columns.content"),
              render: (destination) => {
                const mode = destination.content_mode ?? "result";
                if (mode === "link_only") {
                  return (
                    <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
                      {t("outputDestinationsPage.contentModes.link_only")}
                    </span>
                  );
                }
                const limits = {
                  result: { webhook: 100000, teams: 5000 },
                  excerpt: { webhook: 4000, teams: 1200 },
                };
                const provider = destination.provider_key === "webhook" ? "webhook" : "teams";
                return (
                  <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
                    {t(`outputDestinationsPage.contentModes.${mode}`, {
                      maxCharacters: limits[mode][provider],
                    })}
                  </span>
                );
              },
            },
            {
              header: t("outputDestinationsPage.columns.created"),
              render: (destination) => (
                <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
                  {new Date(destination.created_at).toLocaleDateString(i18n.resolvedLanguage)}
                </span>
              ),
            },
            {
              header: t("outputDestinationsPage.columns.actions"),
              sticky: "right",
              className: "relative px-6 py-4 whitespace-nowrap",
              render: (destination) =>
                canEdit ? (
                  <ActionDropdown
                    size="sm"
                    triggerText={t("outputDestinationsPage.actions.menu")}
                    triggerAriaLabel={t("outputDestinationsPage.actions.menuFor", { name: destination.name })}
                    actions={[
                      {
                        label:
                          testingId === destination.id
                            ? t("outputDestinationsPage.actions.sending")
                            : t("outputDestinationsPage.actions.test"),
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
                        label: t("outputDestinationsPage.actions.edit"),
                        onClick: () => openWizard(destination),
                        icon: <Pencil className="h-4 w-4" />,
                      },
                      {
                        label: t("outputDestinationsPage.actions.delete"),
                        onClick: () => setDestinationToDelete(destination),
                        icon: <Trash2 className="h-4 w-4" />,
                        disabled: deletingId !== null,
                        variant: "danger",
                      },
                    ]}
                  />
                ) : (
                  <span className="text-sm text-gray-400">{t("outputDestinationsPage.viewOnly")}</span>
                ),
            },
          ]}
          emptyIcon={<BackgroundImage icon={Webhook} size={64} iconSize={32} />}
          emptyMessage={t("outputDestinationsPage.emptyTitle")}
          emptySubMessage={t("outputDestinationsPage.emptyDescription")}
        />
      )}
      {!loading && !loadError && destinations.length === 0 && canEdit && (
        <div className="text-center">
          <ButtonApp
            label={t("outputDestinationsPage.addFirst")}
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
              ? t("outputDestinationsPage.updated")
              : t("outputDestinationsPage.created"),
          );
        }}
      />
      <Modal
        isOpen={isTestModalOpen}
        onClose={() => setIsTestModalOpen(false)}
        title={t("outputDestinationsPage.test.title", { name: testDestinationName })}
        size="medium"
      >
        {testingId !== null ? (
          <LoadingState
            variant="section"
            message={t("outputDestinationsPage.test.sending")}
          />
        ) : (
          testResult && (
            <Alert
              type={testResult.success ? "success" : "error"}
              title={testResult.success
                ? t("outputDestinationsPage.test.successTitle")
                : t("outputDestinationsPage.test.errorTitle")}
              message={testResult.message}
              polite={testResult.success}
            />
          )
        )}
      </Modal>
      <ConfirmationModal
        isOpen={destinationToDelete !== null}
        title={t("outputDestinationsPage.confirmDeleteTitle")}
        message={
          destinationToDelete
            ? t("outputDestinationsPage.confirmDeleteMessage", { name: destinationToDelete.name })
            : ""
        }
        confirmLabel={t("outputDestinationsPage.confirmDelete")}
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
