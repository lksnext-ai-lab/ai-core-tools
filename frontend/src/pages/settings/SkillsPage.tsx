import { useState, useEffect, useMemo, useRef, type ChangeEvent } from 'react';
import { useParams } from 'react-router-dom';
import { toast } from 'sonner';
import {
  Target,
  Pencil,
  Trash2,
  Lightbulb,
  Upload,
  ArrowDownToLine,
  Loader2,
  ToggleLeft,
  ToggleRight,
} from 'lucide-react';
import Modal from '../../components/ui/Modal';
import SkillForm from '../../components/forms/SkillForm';
import { apiService } from '../../services/api';
import ActionDropdown, { type ActionItem } from '../../components/ui/ActionDropdown';
import { useSettingsCache } from '../../contexts/SettingsCacheContext';
import { useAppRole } from '../../hooks/useAppRole';
import ReadOnlyBanner from '../../components/ui/ReadOnlyBanner';
import type { Skill } from '../../core/types';
import Alert from '../../components/ui/Alert';
import Table from '../../components/ui/Table';
import { AppRole } from '../../types/roles';
import { useConfirm } from '../../contexts/ConfirmContext';
import { useApiMutation } from '../../hooks/useApiMutation';
import { MESSAGES, errorMessage } from '../../constants/messages';

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

  // Import/export/enable state
  const importInputRef = useRef<HTMLInputElement>(null);
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [exportingSkillId, setExportingSkillId] = useState<number | null>(null);
  const [togglingSkillId, setTogglingSkillId] = useState<number | null>(null);

  // Load skills from cache or API
  useEffect(() => {
    loadSkills();
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
              <Target className="w-5 h-5 text-purple-400 mr-3 shrink-0" aria-hidden="true" />
              {canManageSkill ? (
                <button
                  type="button"
                  className="text-sm font-medium text-gray-900 hover:text-blue-600 transition-colors text-left"
                  onClick={() => void handleEditSkill(skill.skill_id)}
                >
                  {skill.name}
                </button>
              ) : (
                <span className="text-sm font-medium text-gray-900">
                  {skill.name}
                </span>
              )}
            </div>
          );
        }
      },
      {
        header: 'Description',
        render: (skill: Skill) => (
          <div className="text-sm text-gray-600 max-w-xs truncate">
            {skill.description || <span className="text-gray-400 italic">No description</span>}
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
                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-700 border border-gray-300">
                  System
                </span>
              )}
              <span
                className={
                  isEnabled
                    ? 'inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-50 text-green-700 border border-green-200'
                    : 'inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-50 text-red-700 border border-red-200'
                }
              >
                {isEnabled ? 'Enabled' : 'Disabled'}
              </span>
            </div>
          );
        },
        className: 'px-6 py-4 whitespace-nowrap'
      },
      {
        header: 'Created',
        render: (skill: Skill) => skill.created_at ? new Date(skill.created_at).toLocaleDateString() : 'N/A',
        className: 'px-6 py-4 whitespace-nowrap text-sm text-gray-500'
      },
      {
        header: 'Actions',
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
              ? <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
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
                ? <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
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
      <div className="p-6 text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-600 mx-auto"></div>
        <p className="mt-2 text-gray-600">Loading skills...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <Alert type="error" message={error} onDismiss={() => loadSkills()} />
      </div>
    );
  }

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-xl font-semibold text-gray-900">Skills</h2>
          <p className="text-gray-600">Manage prompt-driven specializations for your agents</p>
        </div>
        {canEdit && (
          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleImportClick}
              disabled={importing}
              className="border border-gray-300 hover:bg-gray-50 text-gray-700 px-4 py-2 rounded-lg flex items-center disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {importing ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Upload className="w-4 h-4 mr-2" />
              )}
              {importing ? 'Importing…' : 'Import package'}
            </button>
            <button
              onClick={handleCreateSkill}
              className="bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-lg flex items-center"
            >
              <span className="mr-2">+</span>
              {' '}Add Skill
            </button>
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
        keyExtractor={(skill) => skill.skill_id.toString()}
        rowClassName={(skill) => skill.is_enabled === false ? 'bg-gray-50 hover:bg-gray-100' : 'hover:bg-gray-50'}
        columns={columns}
        emptyIcon={<Target className="w-10 h-10 text-gray-300" />}
        emptyMessage="No Skills"
        emptySubMessage="Add your first skill to create specialized behaviors for your agents."
        loading={loading}
      />

      {skills.length === 0 && canEdit && (
        <div className="text-center py-6">
          <button
            onClick={handleCreateSkill}
            className="bg-purple-600 hover:bg-purple-700 text-white px-6 py-3 rounded-lg"
          >
            Add First Skill
          </button>
        </div>
      )}

      {/* Info Box */}
      <div className="mt-6 bg-purple-50 border border-purple-200 rounded-lg p-4">
        <div className="flex">
          <div className="flex-shrink-0">
            <Lightbulb className="w-5 h-5 text-purple-400" />
          </div>
          <div className="ml-3">
            <h3 className="text-sm font-medium text-purple-800">
              About Skills
            </h3>
            <div className="mt-2 text-sm text-purple-700">
              <p>
                Skills are prompt-driven specializations that agents can dynamically load on-demand.
                When an agent has skills assigned, it gains a <code className="bg-purple-100 px-1 rounded">load_skill</code> tool
                that allows it to activate specialized behavior when needed. Skills marked <strong>System</strong> are
                managed centrally and cannot be edited or deleted here.
              </p>
              <div className="mt-2">
                <strong>Example Skills:</strong>
                <ul className="list-disc list-inside mt-1 space-y-1">
                  <li>Code Review Guidelines - Best practices for reviewing code</li>
                  <li>Technical Writing - Formatting and style for documentation</li>
                  <li>Data Analysis - Steps for analyzing datasets</li>
                  <li>Customer Support - Tone and process for handling inquiries</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Create/Edit Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={handleCloseModal}
        title={editingSkill ? 'Edit Skill' : 'Create New Skill'}
        size="large"
      >
        <SkillForm
          skill={editingSkill}
          onSubmit={handleSaveSkill}
          onCancel={handleCloseModal}
        />
      </Modal>
    </div>
  );
}

export default SkillsPage;
