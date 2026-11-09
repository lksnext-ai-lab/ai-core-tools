import { useState, useEffect, useRef } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Layers, Pencil, Trash2, Upload, ArrowDownToLine, Plus } from 'lucide-react';
import { toast } from 'sonner';
import { SidePanel } from '../../components/ui/SidePanel';
import MiddlewareForm from '../../components/forms/MiddlewareForm';
import { apiService } from '../../services/api';
import ActionDropdown from '../../components/ui/ActionDropdown';
import { useAppRole } from '../../hooks/useAppRole';
import ReadOnlyBanner from '../../components/ui/ReadOnlyBanner';
import type { Middleware, MiddlewarePayload } from '../../core/types';
import { MIDDLEWARE_TYPES } from '../../constants/middlewares';
import Alert from '../../components/ui/Alert';
import { Badge } from '../../components/ui/Badge';
import Table from '../../components/ui/Table';
import ButtonApp from '../../components/ui/ButtonApp';
import ImportModal, { type ConflictMode, type ImportResponse } from '../../components/ui/ImportModal';
import { AppRole } from '../../types/roles';
import { useConfirm } from '../../contexts/ConfirmContext';
import { useApiMutation } from '../../hooks/useApiMutation';
import { errorMessage } from '../../constants/messages';
import { BackgroundImage, LoadingState } from '../..';
import Title from '../../components/ui/Title';

function MiddlewaresPage() {
    const { appId } = useParams();
    const { t, i18n } = useTranslation('common');
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
    const [isFormDirty, setIsFormDirty] = useState(false);
    const isConfirmingCloseRef = useRef(false);

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
            setError(err instanceof Error ? err.message : t('middlewaresPage.loadFailed'));
            console.error('Error loading middlewares:', err);
        } finally {
            setLoading(false);
        }
    }

    async function handleDelete(middlewareId: number) {
        if (!appId) return;

        const target = middlewares.find((m) => m.middleware_id === middlewareId);
        const ok = await confirm({
            title: t('middlewaresPage.confirmDeleteTitle'),
            message: target
                ? t('middlewaresPage.confirmDeleteMessage', { name: target.name })
                : t('middlewaresPage.confirmDeleteFallback'),
            variant: 'danger',
            confirmLabel: t('delete'),
        });
        if (!ok) return;

        const result = await mutate(
            () => apiService.deleteMiddleware(Number.parseInt(appId), middlewareId),
            {
                loading: t('middlewaresPage.deleting'),
                success: t('middlewaresPage.deleted'),
                error: (err) => errorMessage(err, t('middlewaresPage.deleteFailed')),
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
            toast.error(errorMessage(err, t('middlewaresPage.loadItemFailed')));
        }
    }

    async function handleSaveMiddleware(data: MiddlewarePayload) {
        if (!appId) return;

        const editing = editingMiddleware;
        const isUpdate = editing !== null;

        // useApiMutation shows the error toast but swallows the error; keep it so the form can
        // also show it as a banner inside the panel.
        let saveError: unknown = null;
        const result = await mutate<Middleware>(
            async () => {
                try {
                    return await (editing
                        ? apiService.updateMiddleware(Number.parseInt(appId), editing.middleware_id, data)
                        : apiService.createMiddleware(Number.parseInt(appId), data));
                } catch (err) {
                    saveError = err;
                    throw err;
                }
            },
            {
                loading: isUpdate ? t('middlewaresPage.updating') : t('middlewaresPage.creating'),
                success: isUpdate ? t('middlewaresPage.updated') : t('middlewaresPage.created'),
                error: (err) => errorMessage(err, t('middlewaresPage.saveFailed')),
            },
        );
        if (result === undefined) {
            // The panel stays open; the form turns this into the in-panel error banner.
            throw new Error(errorMessage(saveError, t('middlewaresPage.saveFailed')));
        }

        setIsModalOpen(false);
        setEditingMiddleware(null);
        setIsFormDirty(false);
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
            toast.success(t('middlewaresPage.exported'));
        } catch (err) {
            toast.error(errorMessage(err, t('middlewaresPage.exportFailed')));
        } finally {
            setExportingId(null);
        }
    }

    async function handleImport(file: File, conflictMode: ConflictMode, newName?: string): Promise<ImportResponse> {
        if (!appId) throw new Error(t('middlewaresPage.appIdMissing'));
        try {
            const result = await apiService.importMiddleware(Number.parseInt(appId), file, conflictMode, newName);
            if (result.success) {
                setShowImportModal(false);
                toast.success(result.message || t('middlewaresPage.imported'));
                // e.g. the AI service it used does not exist here: the user must act on it.
                for (const warning of result.summary?.warnings ?? []) {
                    toast.warning(warning);
                }
                await loadMiddlewares();
            }
            return result;
        } catch (err) {
            toast.error(errorMessage(err, t('middlewaresPage.importFailed')));
            throw err;
        }
    }

    function handleCloseModal() {
        setIsModalOpen(false);
        setEditingMiddleware(null);
        setIsFormDirty(false);
    }

    /**
     * Every way out of the edit panel (Cancel, X, Esc, backdrop) goes through here: with
     * unsaved changes it asks before discarding them.
     */
    async function requestClosePanel() {
        // Esc reaches both the confirm dialog and the panel; ignore the panel's close meanwhile.
        if (isConfirmingCloseRef.current) return;
        if (!isFormDirty) {
            handleCloseModal();
            return;
        }

        isConfirmingCloseRef.current = true;
        const discard = await confirm({
            title: t('middlewaresPage.discardTitle'),
            message: editingMiddleware
                ? t('middlewaresPage.discardMessage', { name: editingMiddleware.name })
                : t('middlewaresPage.discardMessageNew'),
            confirmLabel: t('middlewaresPage.discardConfirm'),
            cancelLabel: t('middlewaresPage.keepEditing'),
            variant: 'danger',
        });
        // Released on the next tick so the same Esc keypress can't reopen the question.
        setTimeout(() => { isConfirmingCloseRef.current = false; }, 0);
        if (discard) handleCloseModal();
    }

    if (loading) {
        return (
            <div className="space-y-6">
                <Title
                    variant="titPrincipal"
                    titulo={t('middlewaresPage.title')}
                    subtitulo={t('middlewaresPage.subtitle')}
                />
                <LoadingState variant="page" message={t('middlewaresPage.loading')} />
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
                <Title
                    variant="titPrincipal"
                    titulo={t('middlewaresPage.title')}
                    subtitulo={t('middlewaresPage.subtitle')}
                />
                {canEdit && (
                    <div className="flex gap-2">
                        <ButtonApp
                            label={t('middlewaresPage.import')}
                            onClick={() => setShowImportModal(true)}
                            variant="secondary"
                            size="medium"
                            icon={<Upload className="w-4 h-4" aria-hidden="true" />}
                        />
                        <ButtonApp
                            label={t('middlewaresPage.add')}
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
                stickyEdgeColumns
                keyExtractor={(mw) => mw.middleware_id.toString()}
                columns={[
                    {
                        header: t('middlewaresPage.columns.name'),
                        render: (mw) => (
                            <div className="flex min-w-0 items-center">
                                <BackgroundImage icon={Layers} variant='marron' className="mr-2 shrink-0" />
                                {canEdit ? (
                                    <button
                                        type="button"
                                        className="min-w-0 text-sm font-medium text-fg dark:text-fg-dark text-left [overflow-wrap:anywhere]"
                                        onClick={() => void handleEditMiddleware(mw.middleware_id)}
                                    >
                                        {mw.name}
                                    </button>
                                ) : (
                                    <span className="min-w-0 text-sm font-medium text-fg dark:text-fg-dark [overflow-wrap:anywhere]">
                                        {mw.name}
                                    </span>
                                )}
                            </div>
                        )
                    },
                    {
                        header: t('middlewaresPage.columns.type'),
                        render: (mw) => (
                            <Badge label={t(`middlewaresPage.types.${mw.middleware_type}.label`)} variant="info" />
                        ),
                        className: 'px-6 py-4'
                    },
                    {
                        header: t('middlewaresPage.columns.description'),
                        render: (mw) => (
                            <div className="text-xs text-fg-secondary dark:text-fg-secondary-dark max-w-xs truncate">
                                {mw.description || <span className="italic text-fg-tertiary dark:text-fg-tertiary-dark">{t('middlewaresPage.noDescription')}</span>}
                            </div>
                        ),
                        className: 'px-6 py-4'
                    },
                    {
                        header: t('middlewaresPage.columns.created'),
                        render: (mw) => mw.created_at
                            ? new Date(mw.created_at).toLocaleDateString(i18n.resolvedLanguage)
                            : t('middlewaresPage.notAvailable'),
                        className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark'
                    },
                    {
                        header: t('middlewaresPage.columns.actions'),
                        sticky: 'right',
                        className: 'relative',
                        render: (mw) => (
                            canEdit ? (
                                <ActionDropdown
                                    actions={[
                                        {
                                            label: t('middlewaresPage.edit'),
                                            onClick: () => { void handleEditMiddleware(mw.middleware_id); },
                                            icon: <Pencil className="w-4 h-4" />,
                                            variant: 'primary'
                                        },
                                        {
                                            label: t(exportingId === mw.middleware_id
                                                ? 'middlewaresPage.exporting'
                                                : 'middlewaresPage.export'),
                                            onClick: () => { void handleExport(mw); },
                                            icon: <ArrowDownToLine className="w-4 h-4" />,
                                            variant: 'primary'
                                        },
                                        {
                                            label: t('middlewaresPage.delete'),
                                            onClick: () => { void handleDelete(mw.middleware_id); },
                                            icon: <Trash2 className="w-4 h-4" />,
                                            variant: 'danger'
                                        }
                                    ]}
                                    size="sm"
                                />
                            ) : (
                                <span className="text-sm text-fg-tertiary dark:text-fg-tertiary-dark">{t('middlewaresPage.viewOnly')}</span>
                            )
                        )
                    }
                ]}
                emptyIcon={<BackgroundImage icon={Layers} size={64} iconSize={32} />}
                emptyMessage={t('middlewaresPage.emptyTitle')}
                emptySubMessage={t('middlewaresPage.emptyDescription')}
                loading={loading}
            />

            <Alert
                type="info"
                title={t('middlewaresPage.aboutTitle')}
                className="mt-6"
                message={(
                    <>
                        <p>
                            {t('middlewaresPage.aboutDescriptionBeforeAdvanced')}{' '}
                            <strong>{t('middlewaresPage.advancedTab')}</strong>{' '}
                            {t('middlewaresPage.aboutDescriptionAfterAdvanced')}
                        </p>
                        <ul className="list-disc list-inside mt-2 space-y-1">
                            {MIDDLEWARE_TYPES.map((type) => (
                                <li key={type}>
                                    <strong>{t(`middlewaresPage.types.${type}.label`)}</strong>{' '}
                                    {t(`middlewaresPage.types.${type}.description`)}
                                </li>
                            ))}
                        </ul>
                    </>
                )}
            />

            {/* Create/Edit side panel (edit panel, 640 px, fixed footer inside the form) */}
            <SidePanel
                open={isModalOpen}
                onClose={() => { void requestClosePanel(); }}
                side="right"
                title={t('middlewaresPage.title')}
                closeLabel={t('middlewaresPage.closePanel')}
                widthClassName="w-[640px] max-w-full"
            >
                <MiddlewareForm
                    middleware={editingMiddleware}
                    appId={Number.parseInt(appId ?? '0')}
                    onSubmit={handleSaveMiddleware}
                    onCancel={() => { void requestClosePanel(); }}
                    onDirtyChange={setIsFormDirty}
                />
            </SidePanel>

            <ImportModal
                isOpen={showImportModal}
                onClose={() => setShowImportModal(false)}
                onImport={handleImport}
                componentType="middleware"
                componentLabel={t('middlewaresPage.entity')}
            />
        </div>
    );
}

export default MiddlewaresPage;
