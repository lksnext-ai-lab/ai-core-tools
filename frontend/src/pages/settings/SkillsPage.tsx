import { useState, useEffect, useMemo, useRef, type ChangeEvent } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import {
  Target,
  Pencil,
  Trash2,
  Upload,
  ArrowDownToLine,
  ToggleLeft,
  ToggleRight,
  PackagePlus,
  Plus,
} from 'lucide-react';
import Modal from '../../components/ui/Modal';
import SkillForm from '../../components/forms/SkillForm';
import ClaudePluginImportModal from '../../components/forms/ClaudePluginImportModal';
import { apiService } from '../../services/api';
import ActionDropdown, { type ActionItem } from '../../components/ui/ActionDropdown';
import { useSettingsCache } from '../../contexts/SettingsCacheContext';
import { useAppRole } from '../../hooks/useAppRole';
import ReadOnlyBanner from '../../components/ui/ReadOnlyBanner';
import type { Skill } from '../../core/types';
import Alert from '../../components/ui/Alert';
import Table from '../../components/ui/Table';
import { Badge, StatusBadge } from '../../components/ui/Badge';
import { AppRole } from '../../types/roles';
import { useConfirm } from '../../contexts/ConfirmContext';
import { useApiMutation } from '../../hooks/useApiMutation';
import { errorMessage } from '../../constants/messages';
import { LoadingState } from '../../components/ui/LoadingState';
import { ButtonApp } from '../../components/ui/ButtonApp';
import { Spinner } from '../../components/ui/Spinner';
import Title from '../../components/ui/Title';
import BackgroundImage from '../../components/ui/BackgroundImage';

function SkillsPage() {
  const { appId } = useParams();
  const { t, i18n } = useTranslation('common');
  const settingsCache = useSettingsCache();
  const { hasMinRole, userRole } = useAppRole(appId);
  const canEdit = hasMinRole(AppRole.ADMINISTRATOR);
  const confirm = useConfirm();
  const mutate = useApiMutation();
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingSkill, setEditingSkill] = useState<any>(null);

  // The name-cell click-through (and the "View" affordance) must open every visible skill,
  // regardless of role — but only skills the viewer can actually manage should render editable.
  const editingSkillReadOnly = useMemo(
    () => Boolean(editingSkill) && !(canEdit && !editingSkill?.is_system),
    [editingSkill, canEdit],
  );

  // Import/export/enable state
  const importInputRef = useRef<HTMLInputElement>(null);
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [exportingSkillId, setExportingSkillId] = useState<number | null>(null);
  const [togglingSkillId, setTogglingSkillId] = useState<number | null>(null);
  const [isPluginImportOpen, setIsPluginImportOpen] = useState(false);

  // Load skills from cache or API
  useEffect(() => {
    void loadSkills();
  }, [appId]);

  async function loadSkills() {
    if (!appId) return;

    // Check if we have cached data first
    const cachedData = settingsCache.getSkills(appId);
    if (cachedData) {
      setSkills(cachedData);
      setLoading(false);
      return;
    }

    // If no cache, load from API
    try {
      setLoading(true);
      setError(null);
      const response = await apiService.getSkills(Number.parseInt(appId));
      setSkills(response);
      // Cache the response
      settingsCache.setSkills(appId, response);
    } catch (err) {
      setError(errorMessage(err, t('skillsPage.loadFailed')));
      console.error('Error loading skills:', err);
    } finally {
      setLoading(false);
    }
  }

  async function _forceReloadSkills() {
    if (!appId) return;

    try {
      setLoading(true);
      setError(null);
      const response = await apiService.getSkills(Number.parseInt(appId));
      setSkills(response);
      // Cache the response
      settingsCache.setSkills(appId, response);
    } catch (err) {
      setError(errorMessage(err, t('skillsPage.loadFailed')));
      console.error('Error loading skills:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(skillId: number) {
    if (!appId) return;

    const target = skills.find((s) => s.skill_id === skillId);
    const ok = await confirm({
      title: t('skillsPage.confirmDeleteTitle'),
      message: target
        ? t('skillsPage.confirmDeleteMessage', { name: target.name })
        : t('skillsPage.confirmDeleteFallback'),
      variant: 'danger',
      confirmLabel: t('skillsPage.actions.delete'),
    });
    if (!ok) return;

    const result = await mutate(
      () => apiService.deleteSkill(Number.parseInt(appId), skillId),
      {
        loading: t('skillsPage.notifications.deleting'),
        success: t('skillsPage.notifications.deleted'),
        error: (err) => errorMessage(err, t('skillsPage.notifications.deleteFailed')),
      },
    );
    if (result === undefined) return;

    const newSkills = skills.filter((s) => s.skill_id !== skillId);
    setSkills(newSkills);
    settingsCache.setSkills(appId, newSkills);
  }

  function handleCreateSkill() {
    setEditingSkill(null);
    setIsModalOpen(true);
  }

  async function handleEditSkill(skillId: number) {
    if (!appId) return;

    try {
      const skill = await apiService.getSkill(Number.parseInt(appId), skillId);
      setEditingSkill(skill);
      setIsModalOpen(true);
    } catch (err) {
      setError(errorMessage(err, t('skillsPage.loadDetailsFailed')));
      console.error('Error loading skill:', err);
    }
  }

  async function handleSaveSkill(data: any) {
    if (!appId) return;

    const isUpdate = Boolean(editingSkill && editingSkill.skill_id !== 0);

    const result = await mutate<Skill>(
      () =>
        isUpdate
          ? apiService.updateSkill(Number.parseInt(appId), editingSkill.skill_id, data)
          : apiService.createSkill(Number.parseInt(appId), data),
      {
        loading: t(isUpdate ? 'skillsPage.notifications.updating' : 'skillsPage.notifications.creating'),
        success: t(isUpdate ? 'skillsPage.notifications.updated' : 'skillsPage.notifications.created'),
        error: (err) => errorMessage(err, t('skillsPage.notifications.saveFailed')),
      },
    );
    if (result === undefined) return;

    setIsModalOpen(false);
    setEditingSkill(null);

    if (isUpdate) {
      try {
        await loadSkills();
      } catch (err) {
        console.error('Refetch after update failed:', err);
      }
    } else {
      const updatedSkills = [...skills, result];
      setSkills(updatedSkills);
      settingsCache.setSkills(appId, updatedSkills);
    }
  }

  function handleCloseModal() {
    setIsModalOpen(false);
    setEditingSkill(null);
  }

  function handleImportClick() {
    setImportError(null);
    importInputRef.current?.click();
  }

  async function handleImportFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    // Always reset the input value so selecting the same file again re-triggers onChange.
    if (importInputRef.current) {
      importInputRef.current.value = '';
    }
    if (!file || !appId) return;

    if (!file.name.toLowerCase().endsWith('.zip')) {
      setImportError(t('skillsPage.import.invalidFile'));
      return;
    }

    setImporting(true);
    setImportError(null);
    try {
      const created = await apiService.importSkill(Number.parseInt(appId), file);
      const updatedSkills = [...skills, created];
      setSkills(updatedSkills);
      settingsCache.setSkills(appId, updatedSkills);
      toast.success(t('skillsPage.notifications.imported'));
    } catch (err) {
      // Surface the backend's actual 400/409 reason (duplicate name, archive limits, etc.)
      const message = errorMessage(err, t('skillsPage.import.failed'));
      setImportError(message);
      toast.error(message);
      console.error('Error importing skill package:', err);
    } finally {
      setImporting(false);
    }
  }

  function handleClaudePluginImportClick() {
    setIsPluginImportOpen(true);
  }

  function handleClaudePluginImported() {
    if (!appId) return;
    // Reuses the same refetch mechanism as a regular import: invalidate the cached list so
    // `loadSkills` falls through to the API instead of serving stale entries.
    settingsCache.invalidateSkills(appId);
    void loadSkills();
  }

  async function handleExport(skill: Skill) {
    if (!appId) return;

    setExportingSkillId(skill.skill_id);
    try {
      const blob = await apiService.exportSkill(Number.parseInt(appId), skill.skill_id);
      const sanitizedName = (skill.name || 'skill').replaceAll(/[^a-z0-9]/gi, '-').toLowerCase();
      const filename = `skill-${sanitizedName || skill.skill_id}.zip`;

      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      // Revoke immediately after the download has been kicked off — never leak object URLs.
      URL.revokeObjectURL(url);

      toast.success(t('skillsPage.notifications.exported'));
    } catch (err) {
      toast.error(errorMessage(err, t('skillsPage.notifications.exportFailed')));
      console.error('Error exporting skill:', err);
    } finally {
      setExportingSkillId(null);
    }
  }

  async function handleToggleEnabled(skill: Skill) {
    if (!appId) return;

    const nextEnabled = skill.is_enabled === false;
    setTogglingSkillId(skill.skill_id);
    try {
      const updated = await apiService.setSkillEnabled(
        Number.parseInt(appId),
        skill.skill_id,
        nextEnabled,
      );
      const newSkills = skills.map((s) => (s.skill_id === skill.skill_id ? updated : s));
      setSkills(newSkills);
      settingsCache.setSkills(appId, newSkills);
      toast.success(t(nextEnabled ? 'skillsPage.notifications.enabled' : 'skillsPage.notifications.disabled'));
    } catch (err) {
      toast.error(errorMessage(err, t('skillsPage.notifications.statusUpdateFailed')));
      console.error('Error toggling skill enabled state:', err);
    } finally {
      setTogglingSkillId(null);
    }
  }

  const columns = useMemo(
    () => [
      {
        header: t('skillsPage.columns.name'),
        render: (skill: Skill) => {
          const canManageSkill = canEdit && !skill.is_system;
          return (
            <div className="flex items-center">
              <BackgroundImage icon={Target} iconSize={20} size={40} className="mr-2" />
              <button
                type="button"
                className="text-sm font-medium text-fg dark:text-fg-dark text-left"
                onClick={() => void handleEditSkill(skill.skill_id)}
                aria-label={t(canManageSkill ? 'skillsPage.actions.editSkill' : 'skillsPage.actions.viewSkill', { name: skill.name })}
              >
                {skill.name}
              </button>
            </div>
          );
        }
      },
      {
        header: t('skillsPage.columns.description'),
        render: (skill: Skill) => (
          <div className="text-xs text-secondary dark:text-secondary-dark max-w-xs truncate">
            {skill.description || <span className="text-secondary dark:text-secondary-dark italic">{t('skillsPage.noDescription')}</span>}
          </div>
        ),
        className: 'px-6 py-4'
      },
      {
        header: t('skillsPage.columns.status'),
        render: (skill: Skill) => {
          const isEnabled = skill.is_enabled !== false;
          return (
            <div className="flex flex-wrap items-center gap-1.5">
              {skill.is_system && (
                <Badge label={t('skillsPage.statuses.system')} variant="default" />
              )}
              <StatusBadge
                status={isEnabled ? 'active' : 'inactive'}
                customLabel={t(isEnabled ? 'skillsPage.statuses.enabled' : 'skillsPage.statuses.disabled')}
              />
            </div>
          );
        },
        className: 'px-6 py-4 whitespace-nowrap'
      },
      {
        header: t('skillsPage.columns.created'),
        render: (skill: Skill) => skill.created_at ? new Date(skill.created_at).toLocaleDateString(i18n.resolvedLanguage) : t('skillsPage.notAvailable'),
        className: 'px-6 py-4 whitespace-nowrap text-xs text-secondary dark:text-secondary-dark'
      },
      {
        header: t('skillsPage.columns.actions'),
        sticky: 'right' as const,
        className: 'relative',
        render: (skill: Skill) => {
          const canManageSkill = canEdit && !skill.is_system;
          const isExporting = exportingSkillId === skill.skill_id;
          const isToggling = togglingSkillId === skill.skill_id;
          const isEnabled = skill.is_enabled !== false;

          const actions: ActionItem[] = [];

          if (canManageSkill) {
            actions.push({
              label: t('skillsPage.actions.edit'),
              onClick: () => { void handleEditSkill(skill.skill_id); },
              icon: <Pencil className="w-4 h-4" />,
              variant: 'primary'
            });
          }

          // Export is available to anyone who can view the skill — no edit permission required.
          actions.push({
            label: t(isExporting ? 'skillsPage.actions.exporting' : 'skillsPage.actions.export'),
            onClick: () => { void handleExport(skill); },
            icon: isExporting
              ? <Spinner size="sm" tone="current" />
              : <ArrowDownToLine className="w-4 h-4" aria-hidden="true" />,
            disabled: isExporting,
            variant: 'secondary'
          });

          // FR-13: enable/disable control is hidden entirely for roles below ADMINISTRATOR, and
          // for system skills — those are enabled/disabled via the admin System Skills page
          // only; the app-scoped route rejects the request with a 403.
          if (hasMinRole(AppRole.ADMINISTRATOR) && !skill.is_system) {
            let toggleLabelKey = 'skillsPage.actions.enable';
            let toggleIcon = <ToggleRight className="w-4 h-4" aria-hidden="true" />;
            if (isToggling) {
              toggleLabelKey = 'skillsPage.actions.updating';
              toggleIcon = <Spinner size="sm" tone="current" />;
            } else if (isEnabled) {
              toggleLabelKey = 'skillsPage.actions.disable';
              toggleIcon = <ToggleLeft className="w-4 h-4" aria-hidden="true" />;
            }

            actions.push({
              label: t(toggleLabelKey),
              onClick: () => { void handleToggleEnabled(skill); },
              icon: toggleIcon,
              disabled: isToggling,
              variant: isEnabled ? 'warning' : 'success'
            });
          }

          if (canManageSkill) {
            actions.push({
              label: t('skillsPage.actions.delete'),
              onClick: () => { void handleDelete(skill.skill_id); },
              icon: <Trash2 className="w-4 h-4" />,
              variant: 'danger'
            });
          }

          return (
            <>
              <ActionDropdown
                actions={actions}
                size="sm"
                triggerAriaLabel={t('skillsPage.actions.forSkill', { name: skill.name })}
              />
              {(isExporting || isToggling) && (
                <span role="status" aria-live="polite" className="sr-only">
                  {t(isExporting ? 'skillsPage.actions.exportingSkill' : 'skillsPage.actions.updatingSkill', { name: skill.name })}
                </span>
              )}
            </>
          );
        }
      }
    ],
    [canEdit, hasMinRole, exportingSkillId, togglingSkillId, t, i18n.resolvedLanguage],
  );

  let modalTitle = t('skillsPage.modal.createSkill');
  if (editingSkill) {
    modalTitle = editingSkillReadOnly
      ? t('skillsPage.modal.viewSkill')
      : t('skillsPage.modal.editSkill');
  }

  if (loading) {
    return (
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <Title variant="titPrincipal" titulo={t('skillsPage.title')} subtitulo={t('skillsPage.subtitle')} />
        </div>

        <LoadingState variant="page" message={t('skillsPage.loading')} />
      </div>

    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <Title variant="titPrincipal" titulo={t('skillsPage.title')} subtitulo={t('skillsPage.subtitle')} />
        </div>

        <Alert type="error" message={error} onDismiss={() => loadSkills()} />
      </div>
    );
  }

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <Title variant="titPrincipal" titulo={t('skillsPage.title')} subtitulo={t('skillsPage.subtitle')} />
        {canEdit && (
          <div className="flex gap-2">
            <ButtonApp
              label={t(importing ? 'skillsPage.actions.importing' : 'skillsPage.actions.importPackage')}
              onClick={handleImportClick}
              loading={importing}
              variant="secondary"
              icon={<Upload className="w-4 h-4" />}
            />
            <ButtonApp
              type="button"
              onClick={handleClaudePluginImportClick}
              label={t('skillsPage.actions.importClaudePlugin')}
              icon={<PackagePlus className="w-4 h-4" aria-hidden="true" />}
              variant="secondary"
              size="medium"
            />
            <ButtonApp
              onClick={handleCreateSkill}
              label={t('skillsPage.actions.addSkill')}
              icon={<Plus className="w-4 h-4" aria-hidden="true" />}
              variant="primary"
              size="medium"
            />
          </div>
        )}
      </div>

      {/* Hidden file input for package import */}
      <input
        ref={importInputRef}
        type="file"
        accept=".zip,application/zip"
        onChange={(e) => { void handleImportFile(e); }}
        className="hidden"
        aria-label={t('skillsPage.import.fileInputLabel')}
      />

      {/* Import error */}
      {importError && (
        <Alert
          type="error"
          title={t('skillsPage.import.failedTitle')}
          message={importError}
          onDismiss={() => setImportError(null)}
          className="mb-4"
        />
      )}

      {/* Read-only banner for non-admins */}
      {!canEdit && <ReadOnlyBanner userRole={userRole} minRole={AppRole.ADMINISTRATOR} />}

      {/* Skills Table */}
      <Table
        data={skills}
        stickyEdgeColumns
        keyExtractor={(skill) => skill.skill_id.toString()}
        columns={columns}
        emptyIcon={<BackgroundImage icon={Target} size={64} iconSize={32} />}
        emptyMessage={t('skillsPage.emptyTitle')}
        emptySubMessage={t('skillsPage.emptyDescription')}
        loading={loading}
      />

      {skills.length === 0 && canEdit && (
        <div className="text-center py-6">
          <ButtonApp
            onClick={handleCreateSkill}
            label={t('skillsPage.actions.addFirstSkill')}
            variant="primary"
            size="medium"
          />
        </div>
      )}

      <Alert
        type="info"
        title={t('skillsPage.about.title')}
        className="mt-6"
        message={(
          <>
            <p>
              {t('skillsPage.about.descriptionBeforeTool')} <code className="px-1 rounded">load_skill</code> {t('skillsPage.about.descriptionAfterTool')}
            </p>
            <div className="mt-2">
              <span className="text-info dark:text-info-dark font-medium">{t('skillsPage.about.examplesTitle')}</span>
              <ul className="list-disc list-inside mt-1 space-y-1">
                <li>{t('skillsPage.about.examples.codeReview')}</li>
                <li>{t('skillsPage.about.examples.technicalWriting')}</li>
                <li>{t('skillsPage.about.examples.dataAnalysis')}</li>
                <li>{t('skillsPage.about.examples.customerSupport')}</li>
              </ul>
            </div>
          </>
        )}
      />

      {/* Create/Edit Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={handleCloseModal}
        title={modalTitle}
        size="large"
      >
        <SkillForm
          skill={editingSkill}
          readOnly={editingSkillReadOnly}
          userRole={userRole}
          onSubmit={handleSaveSkill}
          onCancel={handleCloseModal}
        />
      </Modal>

      {appId && (
        <ClaudePluginImportModal
          appId={Number.parseInt(appId)}
          isOpen={isPluginImportOpen}
          onClose={() => setIsPluginImportOpen(false)}
          onImported={handleClaudePluginImported}
        />
      )}
    </div>
  );
}

export default SkillsPage;
