import { useState, useEffect, useMemo, useRef, type ChangeEvent } from 'react';
import { useParams } from 'react-router-dom';
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
import { MESSAGES, errorMessage } from '../../constants/messages';
import { LoadingState } from '../../components/ui/LoadingState';
import { ButtonApp } from '../../components/ui/ButtonApp';
import { Spinner } from '../../components/ui/Spinner';
import Title from '../../components/ui/Title';
import BackgroundImage from '../../components/ui/BackgroundImage';

function SkillsPage() {
  const { appId } = useParams();
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
      setError(err instanceof Error ? err.message : 'Failed to load skills');
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
      setError(err instanceof Error ? err.message : 'Failed to load skills');
      console.error('Error loading skills:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(skillId: number) {
    if (!appId) return;

    const target = skills.find((s) => s.skill_id === skillId);
    const ok = await confirm({
      title: MESSAGES.CONFIRM_DELETE_TITLE('skill'),
      message: target
        ? `Are you sure you want to delete "${target.name}"? Agents using it will lose this specialization.`
        : MESSAGES.CONFIRM_DELETE_MESSAGE('skill'),
      variant: 'danger',
      confirmLabel: 'Delete',
    });
    if (!ok) return;

    const result = await mutate(
      () => apiService.deleteSkill(Number.parseInt(appId), skillId),
      {
        loading: MESSAGES.DELETING('skill'),
        success: MESSAGES.DELETED('skill'),
        error: (err) => errorMessage(err, MESSAGES.DELETE_FAILED('skill')),
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
      setError(err instanceof Error ? err.message : 'Failed to load skill details');
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
        loading: isUpdate ? MESSAGES.UPDATING('skill') : MESSAGES.CREATING('skill'),
        success: isUpdate ? MESSAGES.UPDATED('skill') : MESSAGES.CREATED('skill'),
        error: (err) => errorMessage(err, MESSAGES.SAVE_FAILED('skill')),
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
      setImportError('Please select a valid skill package (.zip file).');
      return;
    }

    setImporting(true);
    setImportError(null);
    try {
      const created = await apiService.importSkill(Number.parseInt(appId), file);
      const updatedSkills = [...skills, created];
      setSkills(updatedSkills);
      settingsCache.setSkills(appId, updatedSkills);
      toast.success(MESSAGES.IMPORTED('skill'));
    } catch (err) {
      // Surface the backend's actual 400/409 reason (duplicate name, archive limits, etc.)
      const message = errorMessage(err, MESSAGES.IMPORT_FAILED('skill'));
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

      toast.success(MESSAGES.EXPORTED('skill'));
    } catch (err) {
      toast.error(errorMessage(err, MESSAGES.EXPORT_FAILED('skill')));
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
      toast.success(nextEnabled ? 'Skill enabled' : 'Skill disabled');
    } catch (err) {
      toast.error(errorMessage(err, 'Failed to update skill status'));
      console.error('Error toggling skill enabled state:', err);
    } finally {
      setTogglingSkillId(null);
    }
  }

  const columns = useMemo(
    () => [
      {
        header: 'Name',
        render: (skill: Skill) => {
          const canManageSkill = canEdit && !skill.is_system;
          return (
            <div className="flex items-center">
              <BackgroundImage icon={Target} iconSize={20} size={40} className="mr-2" />
              <button
                type="button"
                className="text-sm font-medium text-fg dark:text-fg-dark text-left"
                onClick={() => void handleEditSkill(skill.skill_id)}
                aria-label={canManageSkill ? `Edit skill ${skill.name}` : `View skill ${skill.name}`}
              >
                {skill.name}
              </button>
            </div>
          );
        }
      },
      {
        header: 'Description',
        render: (skill: Skill) => (
          <div className="text-xs text-secondary dark:text-secondary-dark max-w-xs truncate">
            {skill.description || <span className="text-secondary dark:text-secondary-dark italic">No description</span>}
          </div>
        ),
        className: 'px-6 py-4'
      },
      {
        header: 'Status',
        render: (skill: Skill) => {
          const isEnabled = skill.is_enabled !== false;
          return (
            <div className="flex flex-wrap items-center gap-1.5">
              {skill.is_system && (
                <Badge label="System" variant="default" />
              )}
              <StatusBadge
                status={isEnabled ? 'active' : 'inactive'}
                customLabel={isEnabled ? 'Enabled' : 'Disabled'}
              />
            </div>
          );
        },
        className: 'px-6 py-4 whitespace-nowrap'
      },
      {
        header: 'Created',
        render: (skill: Skill) => skill.created_at ? new Date(skill.created_at).toLocaleDateString() : 'N/A',
        className: 'px-6 py-4 whitespace-nowrap text-xs text-secondary dark:text-secondary-dark'
      },
      {
        header: 'Actions',
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
              label: 'Edit',
              onClick: () => { void handleEditSkill(skill.skill_id); },
              icon: <Pencil className="w-4 h-4" />,
              variant: 'primary'
            });
          }

          // Export is available to anyone who can view the skill — no edit permission required.
          actions.push({
            label: isExporting ? 'Exporting...' : 'Export',
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
            actions.push({
              label: isToggling ? 'Updating...' : (isEnabled ? 'Disable' : 'Enable'),
              onClick: () => { void handleToggleEnabled(skill); },
              icon: isToggling
                ? <Spinner size="sm" tone="current" />
                : (isEnabled ? <ToggleLeft className="w-4 h-4" aria-hidden="true" /> : <ToggleRight className="w-4 h-4" aria-hidden="true" />),
              disabled: isToggling,
              variant: isEnabled ? 'warning' : 'success'
            });
          }

          if (canManageSkill) {
            actions.push({
              label: 'Delete',
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
                triggerAriaLabel={`Actions for skill ${skill.name}`}
              />
              {(isExporting || isToggling) && (
                <span role="status" aria-live="polite" className="sr-only">
                  {isExporting ? `Exporting skill ${skill.name}…` : `Updating skill ${skill.name}…`}
                </span>
              )}
            </>
          );
        }
      }
    ],
    [canEdit, hasMinRole, exportingSkillId, togglingSkillId],
  );

  if (loading) {
    return (
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <Title variant="titPrincipal" titulo='Skills' subtitulo='Manage prompt-driven specializations for your agents' />
        </div>

        <LoadingState variant="page" message="Loading skills..." />
      </div>

    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <Title variant="titPrincipal" titulo='Skills' subtitulo='Manage prompt-driven specializations for your agents' />
        </div>

        <Alert type="error" message={error} onDismiss={() => loadSkills()} />
      </div>
    );
  }

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <Title variant="titPrincipal" titulo='Skills' subtitulo='Manage prompt-driven specializations for your agents' />
        {canEdit && (
          <div className="flex gap-2">
            <ButtonApp
              label={importing ? 'Importing…' : 'Import package'}
              onClick={handleImportClick}
              loading={importing}
              variant="secondary"
              icon={<Upload className="w-4 h-4" />}
            />
            <ButtonApp
              type="button"
              onClick={handleClaudePluginImportClick}
              label="Import Claude plugin"
              icon={<PackagePlus className="w-4 h-4" aria-hidden="true" />}
              variant="secondary"
              size="medium"
            />
            <ButtonApp
              onClick={handleCreateSkill}
              label="Add Skill"
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
        aria-label="Import skill package file"
      />

      {/* Import error */}
      {importError && (
        <Alert
          type="error"
          title="Import failed"
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
        emptyMessage="No Skills"
        emptySubMessage="Add your first skill to create specialized behaviors for your agents."
        loading={loading}
      />

      {skills.length === 0 && canEdit && (
        <div className="text-center py-6">
          <ButtonApp
            onClick={handleCreateSkill}
            label="Add First Skill"
            variant="primary"
            size="medium"
          />
        </div>
      )}

      <Alert
        type="info"
        title="About Skills"
        className="mt-6"
        message={(
          <>
            <p>
              Skills are prompt-driven specializations that agents can dynamically load on-demand.
              When an agent has skills assigned, it gains a <code className="px-1 rounded">load_skill</code> tool
              that allows it to activate specialized behavior when needed. Skills marked <strong>System</strong> are
              managed centrally and cannot be edited or deleted here.
            </p>
            <div className="mt-2">
              <span className="text-info dark:text-info-dark font-medium">Example Skills:</span>
              <ul className="list-disc list-inside mt-1 space-y-1">
                <li>Code Review Guidelines - Best practices for reviewing code</li>
                <li>Technical Writing - Formatting and style for documentation</li>
                <li>Data Analysis - Steps for analyzing datasets</li>
                <li>Customer Support - Tone and process for handling inquiries</li>
              </ul>
            </div>
          </>
        )}
      />

      {/* Create/Edit Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={handleCloseModal}
        title={editingSkill ? (editingSkillReadOnly ? 'View Skill' : 'Edit Skill') : 'Create New Skill'}
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
