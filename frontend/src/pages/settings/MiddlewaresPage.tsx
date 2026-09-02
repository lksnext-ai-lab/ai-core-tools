import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { Layers, Pencil, Trash2, Lightbulb } from 'lucide-react';
import Modal from '../../components/ui/Modal';
import MiddlewareForm from '../../components/forms/MiddlewareForm';
import { apiService } from '../../services/api';
import ActionDropdown from '../../components/ui/ActionDropdown';
import { useAppRole } from '../../hooks/useAppRole';
import ReadOnlyBanner from '../../components/ui/ReadOnlyBanner';
import type { Middleware } from '../../core/types';
import Alert from '../../components/ui/Alert';
import Table from '../../components/ui/Table';
import { AppRole } from '../../types/roles';
import { useConfirm } from '../../contexts/ConfirmContext';
import { useApiMutation } from '../../hooks/useApiMutation';
import { MESSAGES, errorMessage } from '../../constants/messages';

const MIDDLEWARE_TYPE_LABELS: Record<string, string> = {
    monitoring: 'Monitoring',
    summarization: 'Summarization',
    model_call_limit: 'Model Call Limit',
    tool_call_limit: 'Tool Call Limit',
    pii: 'PII Detection',
    human_in_the_loop: 'Human in the Loop',
    guardrails: 'Guardrails',
    custom: 'Custom',
};

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
    const [editingMiddleware, setEditingMiddleware] = useState<any>(null);

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
            setError(err instanceof Error ? err.message : 'Failed to load middleware details');
            console.error('Error loading middleware:', err);
        }
    }

    async function handleSaveMiddleware(data: any) {
        if (!appId) return;

        const isUpdate = Boolean(editingMiddleware && editingMiddleware.middleware_id !== 0);

        const result = await mutate<Middleware>(
            () =>
                isUpdate
                    ? apiService.updateMiddleware(Number.parseInt(appId), editingMiddleware.middleware_id, data)
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
                    <p className="text-gray-600">Manage LangChain middlewares that can be attached to your agents</p>
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
                                {MIDDLEWARE_TYPE_LABELS[mw.middleware_type] || mw.middleware_type}
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
                emptySubMessage="Add your first middleware to extend agent capabilities with monitoring, logging, and more."
                loading={loading}
            />

            {middlewares.length === 0 && canEdit && (
                <div className="text-center py-6">
                    <button
                        onClick={handleCreateMiddleware}
                        className="bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-3 rounded-lg"
                    >
                        Add First Middleware
                    </button>
                </div>
            )}

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
                                Middlewares are LangChain components that intercept and process agent execution.
                                When attached to an agent, middlewares can monitor token usage, limit calls,
                                detect PII, and provide observability into agent behavior.
                            </p>
                            <div className="mt-2">
                                <strong>Available Types:</strong>
                                <ul className="list-disc list-inside mt-1 space-y-1">
                                    <li><strong>Monitoring</strong> — Tracks input/output tokens and LLM call count via callback</li>
                                    <li><strong>Summarization</strong> — Summarizes conversation history when token limits are exceeded</li>
                                    <li><strong>Model Call Limit</strong> — Caps LLM calls per run to prevent infinite loops (configurable)</li>
                                    <li><strong>Tool Call Limit</strong> — Caps tool invocations per run to prevent runaway execution (configurable)</li>
                                    <li><strong>PII Detection</strong> — Redacts personal data before the LLM and restores it in responses</li>
                                    <li><strong>Human in the Loop</strong> — Requires explicit human approval/edit/reject before selected tools run</li>
                                    <li><strong>Guardrails</strong> — Applies safety and policy checks on prompts and model responses</li>
                                </ul>
                            </div>
                            <p className="mt-2 text-xs text-indigo-600 italic">
                                Custom middleware upload (.py files with LangChain middleware classes) will be available in a future release.
                            </p>
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
                    appId={appId ? Number.parseInt(appId) : undefined}
                    onSubmit={handleSaveMiddleware}
                    onCancel={handleCloseModal}
                />
            </Modal>
        </div>
    );
}

export default MiddlewaresPage;
