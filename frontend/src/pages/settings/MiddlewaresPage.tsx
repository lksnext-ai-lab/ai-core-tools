import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { Layers, Pencil, Trash2, Lightbulb } from 'lucide-react';
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
import Table from '../../components/ui/Table';
import { AppRole } from '../../types/roles';
import { useConfirm } from '../../contexts/ConfirmContext';
import { useApiMutation } from '../../hooks/useApiMutation';
import { MESSAGES, errorMessage } from '../../constants/messages';

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

    useEffect(() => {
        loadMiddlewares();
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

    function handleCloseModal() {
        setIsModalOpen(false);
        setEditingMiddleware(null);
    }

    if (loading) {
        return (
            <div className="p-6 text-center">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600 mx-auto"></div>
                <p className="mt-2 text-gray-600">Loading middlewares...</p>
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
                <div>
                    <h2 className="text-xl font-semibold text-gray-900">Middlewares</h2>
                    <p className="text-gray-600">Reusable safety, approval and cost controls for your agents</p>
                </div>
                {canEdit && (
                    <button
                        onClick={handleCreateMiddleware}
                        className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg flex items-center"
                    >
                        <span className="mr-2">+</span>
                        {' '}Add Middleware
                    </button>
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
                                <Layers className="w-5 h-5 text-indigo-400 mr-3 shrink-0" />
                                {canEdit ? (
                                    <button
                                        type="button"
                                        className="text-sm font-medium text-gray-900 hover:text-blue-600 transition-colors text-left"
                                        onClick={() => void handleEditMiddleware(mw.middleware_id)}
                                    >
                                        {mw.name}
                                    </button>
                                ) : (
                                    <span className="text-sm font-medium text-gray-900">
                                        {mw.name}
                                    </span>
                                )}
                            </div>
                        )
                    },
                    {
                        header: 'Type',
                        render: (mw) => (
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-800">
                                {middlewareTypeLabel(mw.middleware_type)}
                            </span>
                        ),
                        className: 'px-6 py-4'
                    },
                    {
                        header: 'Description',
                        render: (mw) => (
                            <div className="text-sm text-gray-600 max-w-xs truncate">
                                {mw.description || <span className="text-gray-400 italic">No description</span>}
                            </div>
                        ),
                        className: 'px-6 py-4'
                    },
                    {
                        header: 'Created',
                        render: (mw) => mw.created_at ? new Date(mw.created_at).toLocaleDateString() : 'N/A',
                        className: 'px-6 py-4 whitespace-nowrap text-sm text-gray-500'
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

            {/* Info Box */}
            <div className="mt-6 bg-indigo-50 border border-indigo-200 rounded-lg p-4">
                <div className="flex">
                    <div className="flex-shrink-0">
                        <Lightbulb className="w-5 h-5 text-indigo-400" />
                    </div>
                    <div className="ml-3">
                        <h3 className="text-sm font-medium text-indigo-800">
                            About Middlewares
                        </h3>
                        <div className="mt-2 text-sm text-indigo-700">
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
                        </div>
                    </div>
                </div>
            </div>

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
        </div>
    );
}

export default MiddlewaresPage;
