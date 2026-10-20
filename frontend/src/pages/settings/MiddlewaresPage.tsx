import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { Layers, Pencil, Trash2, Upload, ArrowDownToLine, Plus } from 'lucide-react';
import { toast } from 'sonner';
import Modal from '../../components/ui/Modal';
import MiddlewareForm from '../../components/forms/MiddlewareForm';
import { apiService } from '../../services/api';
import ActionDropdown from '../../components/ui/ActionDropdown';
import { useAppRole } from '../../hooks/useAppRole';
import ReadOnlyBanner from '../../components/ui/ReadOnlyBanner';
import type { Middleware, MiddlewarePayload } from '../../core/types';
import { MIDDLEWARE_TYPES, MIDDLEWARE_TYPE_INFO, middlewareTypeLabel } from '../../constants/middlewares';
import Alert from '../../components/ui/Alert';
import { Badge } from '../../components/ui/Badge';
import Table from '../../components/ui/Table';
import ButtonApp from '../../components/ui/ButtonApp';
import ImportModal, { type ConflictMode, type ImportResponse } from '../../components/ui/ImportModal';
import { AppRole } from '../../types/roles';
import { useConfirm } from '../../contexts/ConfirmContext';
import { useApiMutation } from '../../hooks/useApiMutation';
import { MESSAGES, errorMessage } from '../../constants/messages';
import { BackgroundImage, LoadingState } from '../..';
import Title from '../../components/ui/Title';

function MiddlewaresPage() {
    const { appId } = useParams();
    const { hasMinRole, userRole } = useAppRole(appId);
    const canEdit = hasMinRole(AppRole.ADMINISTRATOR);
    const confirm = useConfirm();
    const mutate = useApiMutation();
    const [middlewares, setMiddlewares] = useState<Middleware[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [editingMiddleware, setEditingMiddleware] = useState<Middleware | null>(null);
    const [showImportModal, setShowImportModal] = useState(false);
    const [exportingId, setExportingId] = useState<number | null>(null);

    useEffect(() => {
        void loadMiddlewares();
    }, [appId]);

    async function loadMiddlewares() {
        if (!appId) return;

        try {
            setLoading(true);
            setError(null);
            const response = await apiService.getMiddlewares(Number.parseInt(appId));
            setMiddlewares(response);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load middlewares');
            console.error('Error loading middlewares:', err);
        } finally {
            setLoading(false);
        }
    }

    async function handleDelete(middlewareId: number) {
        if (!appId) return;

        const target = middlewares.find((m) => m.middleware_id === middlewareId);
        const ok = await confirm({
            title: MESSAGES.CONFIRM_DELETE_TITLE('middleware'),
            message: target
                ? `Are you sure you want to delete "${target.name}"? Agents using it will lose this middleware.`
                : MESSAGES.CONFIRM_DELETE_MESSAGE('middleware'),
            variant: 'danger',
            confirmLabel: 'Delete',
        });
        if (!ok) return;

        const result = await mutate(
            () => apiService.deleteMiddleware(Number.parseInt(appId), middlewareId),
            {
                loading: MESSAGES.DELETING('middleware'),
                success: MESSAGES.DELETED('middleware'),
                error: (err) => errorMessage(err, MESSAGES.DELETE_FAILED('middleware')),
            },
        );
        if (result === undefined) return;

        setMiddlewares(middlewares.filter((m) => m.middleware_id !== middlewareId));
    }

    function handleCreateMiddleware() {
        setEditingMiddleware(null);
        setIsModalOpen(true);
    }

    async function handleEditMiddleware(middlewareId: number) {
        if (!appId) return;

        try {
            const mw = await apiService.getMiddleware(Number.parseInt(appId), middlewareId);
            setEditingMiddleware(mw);
            setIsModalOpen(true);
        } catch (err) {
            toast.error(errorMessage(err, 'Failed to load middleware'));
        }
    }

    async function handleSaveMiddleware(data: MiddlewarePayload) {
        if (!appId) return;

        const editing = editingMiddleware;
        const isUpdate = editing !== null;

        const result = await mutate<Middleware>(
            () =>
                editing
                    ? apiService.updateMiddleware(Number.parseInt(appId), editing.middleware_id, data)
                    : apiService.createMiddleware(Number.parseInt(appId), data),
            {
                loading: isUpdate ? MESSAGES.UPDATING('middleware') : MESSAGES.CREATING('middleware'),
                success: isUpdate ? MESSAGES.UPDATED('middleware') : MESSAGES.CREATED('middleware'),
                error: (err) => errorMessage(err, MESSAGES.SAVE_FAILED('middleware')),
            },
        );
        if (result === undefined) return;

        setIsModalOpen(false);
        setEditingMiddleware(null);
        await loadMiddlewares();
    }

    async function handleExport(middleware: Middleware) {
        if (!appId) return;
        setExportingId(middleware.middleware_id);
        try {
            const blob = await apiService.exportMiddleware(Number.parseInt(appId), middleware.middleware_id);
            const sanitizedName = middleware.name.replaceAll(/[^a-z0-9]/gi, '-').toLowerCase();
            const timestamp = new Date().toISOString().split('T')[0];
            const url = globalThis.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `middleware-${sanitizedName}-${timestamp}.json`;
            document.body.appendChild(a);
            a.click();
            globalThis.URL.revokeObjectURL(url);
            a.remove();
            toast.success(MESSAGES.EXPORTED('middleware'));
        } catch (err) {
            toast.error(errorMessage(err, MESSAGES.EXPORT_FAILED('middleware')));
        } finally {
            setExportingId(null);
        }
    }

    async function handleImport(file: File, conflictMode: ConflictMode, newName?: string): Promise<ImportResponse> {
        if (!appId) throw new Error('App ID not found');
        try {
            const result = await apiService.importMiddleware(Number.parseInt(appId), file, conflictMode, newName);
            if (result.success) {
                setShowImportModal(false);
                toast.success(result.message || MESSAGES.IMPORTED('middleware'));
                // e.g. the AI service it used does not exist here: the user must act on it.
                for (const warning of result.summary?.warnings ?? []) {
                    toast.warning(warning);
                }
                await loadMiddlewares();
            }
            return result;
        } catch (err) {
            toast.error(errorMessage(err, MESSAGES.IMPORT_FAILED('middleware')));
            throw err;
        }
    }

    function handleCloseModal() {
        setIsModalOpen(false);
        setEditingMiddleware(null);
    }

    if (loading) {
        return (
                    <div className="space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <Title variant='titPrincipal' titulo='Middlewares' subtitulo='Reusable safety, approval and cost controls for your agents'></Title>
        </div>

        <LoadingState variant="page" message="Loading silos..." />
      </div>
        );
    }

    if (error) {
        return (
            <div className="p-6">
                <Alert type="error" message={error} onDismiss={() => loadMiddlewares()} />
            </div>
        );
    }

    return (
        <div className="p-6">
            {/* Header */}
            <div className="flex justify-between items-center mb-6">
               <Title variant='titPrincipal' titulo='Middlewares' subtitulo='Reusable safety, approval and cost controls for your agents'></Title>
                {canEdit && (
                    <div className="flex gap-2">
                        <ButtonApp
                            label="Import"
                            onClick={() => setShowImportModal(true)}
                            variant="secondary"
                            size="medium"
                            icon={<Upload className="w-4 h-4" aria-hidden="true" />}
                        />
                        <ButtonApp
                            label="Add Middleware"
                            onClick={handleCreateMiddleware}
                            variant="primary"
                            size="medium"
                            icon={<Plus className="w-4 h-4" aria-hidden="true" />}
                        />
                    </div>
                )}
            </div>

            {/* Read-only banner for non-admins */}
            {!canEdit && <ReadOnlyBanner userRole={userRole} minRole={AppRole.ADMINISTRATOR} />}

            {/* Middlewares Table */}
            <Table
                data={middlewares}
                keyExtractor={(mw) => mw.middleware_id.toString()}
                columns={[
                    {
                        header: 'Name',
                        render: (mw) => (
                            <div className="flex items-center">
                                <BackgroundImage icon={Layers} variant='marron' className="mr-2" />
                                {canEdit ? (
                                    <button
                                        type="button"
                                        className="text-sm font-medium text-fg dark:text-fg-dark text-left"
                                        onClick={() => void handleEditMiddleware(mw.middleware_id)}
                                    >
                                        {mw.name}
                                    </button>
                                ) : (
                                    <span className="text-sm font-medium text-fg dark:text-fg-dark">
                                        {mw.name}
                                    </span>
                                )}
                            </div>
                        )
                    },
                    {
                        header: 'Type',
                        render: (mw) => (
                            <Badge label={middlewareTypeLabel(mw.middleware_type)} variant="info" />
                        ),
                        className: 'px-6 py-4'
                    },
                    {
                        header: 'Description',
                        render: (mw) => (
                            <div className="text-xs text-fg-secondary dark:text-fg-secondary-dark max-w-xs truncate">
                                {mw.description || <span className="text-gray-400 italic">No description</span>}
                            </div>
                        ),
                        className: 'px-6 py-4'
                    },
                    {
                        header: 'Created',
                        render: (mw) => mw.created_at ? new Date(mw.created_at).toLocaleDateString() : 'N/A',
                        className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark'
                    },
                    {
                        header: 'Actions',
                        className: 'relative',
                        render: (mw) => (
                            canEdit ? (
                                <ActionDropdown
                                    actions={[
                                        {
                                            label: 'Edit',
                                            onClick: () => { void handleEditMiddleware(mw.middleware_id); },
                                            icon: <Pencil className="w-4 h-4" />,
                                            variant: 'primary'
                                        },
                                        {
                                            label: exportingId === mw.middleware_id ? 'Exporting...' : 'Export',
                                            onClick: () => { void handleExport(mw); },
                                            icon: <ArrowDownToLine className="w-4 h-4" />,
                                            variant: 'primary'
                                        },
                                        {
                                            label: 'Delete',
                                            onClick: () => { void handleDelete(mw.middleware_id); },
                                            icon: <Trash2 className="w-4 h-4" />,
                                            variant: 'danger'
                                        }
                                    ]}
                                    size="sm"
                                />
                            ) : (
                                <span className="text-gray-400 text-sm">View only</span>
                            )
                        )
                    }
                ]}
                emptyIcon={<Layers className="w-10 h-10 text-gray-300" />}
                emptyMessage="No Middlewares"
                emptySubMessage="Create one, then turn it on from an agent's Advanced tab."
                loading={loading}
            />

            <Alert
                type="info"
                title="About Middlewares"
                className="mt-6"
                message={(
                    <>
                        <p>
                            Middlewares run around every model and tool call of the agents that use them.
                            Create them here once, then select them in each agent&apos;s <strong>Advanced</strong> tab.
                            An agent can use one middleware of each type.
                        </p>
                        <ul className="list-disc list-inside mt-2 space-y-1">
                            {MIDDLEWARE_TYPES.map((type) => (
                                <li key={type}>
                                    <strong>{MIDDLEWARE_TYPE_INFO[type].label}</strong> — {MIDDLEWARE_TYPE_INFO[type].description}
                                </li>
                            ))}
                        </ul>
                    </>
                )}
            />

            {/* Create/Edit Modal */}
            <Modal
                isOpen={isModalOpen}
                onClose={handleCloseModal}
                title={editingMiddleware ? 'Edit Middleware' : 'Create New Middleware'}
                size="large"
            >
                <MiddlewareForm
                    middleware={editingMiddleware}
                    appId={Number.parseInt(appId ?? '0')}
                    onSubmit={handleSaveMiddleware}
                    onCancel={handleCloseModal}
                />
            </Modal>

            <ImportModal
                isOpen={showImportModal}
                onClose={() => setShowImportModal(false)}
                onImport={handleImport}
                componentType="middleware"
                componentLabel="Middleware"
            />
        </div>
    );
}

export default MiddlewaresPage;
