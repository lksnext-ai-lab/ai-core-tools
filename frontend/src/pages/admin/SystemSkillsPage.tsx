import { useCallback, useEffect, useRef, useState, type ChangeEvent } from 'react';
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
import SkillForm, { type SkillFormSubmitData } from '../../components/forms/SkillForm';
import { apiService } from '../../services/api';
import ActionDropdown, { type ActionItem } from '../../components/ui/ActionDropdown';
import { LoadingState } from '../../components/ui/LoadingState';
import { ErrorState } from '../../components/ui/ErrorState';
import Alert from '../../components/ui/Alert';
import Table from '../../components/ui/Table';
import { useConfirm } from '../../contexts/ConfirmContext';
import { useApiMutation } from '../../hooks/useApiMutation';
import { MESSAGES, errorMessage } from '../../constants/messages';
import type { Skill } from '../../core/types';

function SystemSkillsPage() {
  const confirm = useConfirm();
  const mutate = useApiMutation();

  const [skills, setSkills] = useState<Skill[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingSkill, setEditingSkill] = useState<Skill | null>(null);

  // Import/export/enable state
  const importInputRef = useRef<HTMLInputElement>(null);
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [exportingSkillId, setExportingSkillId] = useState<number | null>(null);
  const [togglingSkillId, setTogglingSkillId] = useState<number | null>(null);

  const fetchSkills = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      // Includes disabled skills on purpose — this admin view must show everything.
      const data = await apiService.getSystemSkills();
      setSkills(data);
    } catch (err) {
      setError(errorMessage(err, MESSAGES.LOAD_FAILED('system skills')));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSkills();
  }, [fetchSkills]);

  function handleOpenCreate() {
    setEditingSkill(null);
    setIsModalOpen(true);
  }

  async function handleOpenEdit(skill: Skill) {
    try {
      const detail = await apiService.getSystemSkill(skill.skill_id);
      setEditingSkill(detail);
    } catch {
      setEditingSkill(skill);
    }
    setIsModalOpen(true);
  }

  function handleCloseModal() {
    setIsModalOpen(false);
    setEditingSkill(null);
  }

  async function handleSave(data: SkillFormSubmitData) {
    const isUpdate = editingSkill !== null;

    const result = await mutate(
      () =>
        isUpdate
          ? apiService.updateSystemSkill(editingSkill.skill_id, data)
          : apiService.createSystemSkill(data),
      {
        loading: isUpdate ? MESSAGES.UPDATING('skill') : MESSAGES.CREATING('skill'),
        success: isUpdate ? MESSAGES.UPDATED('skill') : MESSAGES.CREATED('skill'),
        error: (err) =>
          errorMessage(err, isUpdate ? MESSAGES.UPDATE_FAILED('skill') : MESSAGES.CREATE_FAILED('skill')),
      },
    );
    if (result === undefined) return;

    handleCloseModal();
    await fetchSkills();
  }

  async function handleDelete(skill: Skill) {
    const ok = await confirm({
      title: MESSAGES.CONFIRM_DELETE_TITLE('system skill'),
      message: `Delete "${skill.name}"? Apps using it will lose this specialization.`,
      variant: 'danger',
      confirmLabel: 'Delete',
    });
    if (!ok) return;

    // The backend rejects deletion of yaml-seeded/frozen/in-use skills with a 409 whose
    // `detail` is a human-readable explanation (e.g. "seeded from system_defaults.yaml —
    // disable it instead"). errorMessage() surfaces that ApiError message verbatim, so the
    // toast below never shows a raw dump — it shows exactly what the backend explains.
    const result = await mutate(
      () => apiService.deleteSystemSkill(skill.skill_id),
      {
        loading: MESSAGES.DELETING('skill'),
        success: MESSAGES.DELETED('skill'),
        error: (err) => errorMessage(err, MESSAGES.DELETE_FAILED('skill')),
      },
    );
    if (result === undefined) return;

    await fetchSkills();
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
    if (!file) return;

    if (!file.name.toLowerCase().endsWith('.zip')) {
      setImportError('Please select a valid skill package (.zip file).');
      return;
    }

    setImporting(true);
    setImportError(null);
    try {
      await apiService.importSystemSkill(file);
      await fetchSkills();
      toast.success(MESSAGES.IMPORTED('skill'));
    } catch (err) {
      // Surface the backend's actual 400/409 reason (duplicate name, archive limits, etc.)
      const message = errorMessage(err, MESSAGES.IMPORT_FAILED('skill'));
      setImportError(message);
      toast.error(message);
    } finally {
      setImporting(false);
    }
  }

  async function handleExport(skill: Skill) {
    setExportingSkillId(skill.skill_id);
    try {
      const blob = await apiService.exportSystemSkill(skill.skill_id);
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
    } finally {
      setExportingSkillId(null);
    }
  }

  async function handleToggleEnabled(skill: Skill) {
    const nextEnabled = skill.is_enabled === false;
    setTogglingSkillId(skill.skill_id);
    try {
      const updated = await apiService.setSystemSkillEnabled(skill.skill_id, nextEnabled);
      setSkills((prev) => prev.map((s) => (s.skill_id === skill.skill_id ? updated : s)));
      toast.success(nextEnabled ? 'Skill enabled' : 'Skill disabled');
    } catch (err) {
      toast.error(errorMessage(err, 'Failed to update skill status'));
    } finally {
      setTogglingSkillId(null);
    }
  }

  if (isLoading) return <LoadingState message="Loading system skills..." />;
  if (error) return <ErrorState error={error} onRetry={fetchSkills} />;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">System Skills</h1>
          <p className="text-gray-600">
            Shared prompt-driven specializations, including disabled ones, available to every app.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={handleImportClick}
            disabled={importing}
            className="border border-gray-300 hover:bg-gray-50 text-gray-700 px-4 py-2 rounded-lg text-sm font-medium flex items-center disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {importing ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <Upload className="w-4 h-4 mr-2" />
            )}
            {importing ? 'Importing…' : 'Import package'}
          </button>
          <button
            type="button"
            onClick={handleOpenCreate}
            className="bg-blue-600 text-white rounded-lg px-4 py-2 text-sm font-medium hover:bg-blue-700"
          >
            Add skill
          </button>
        </div>
      </div>

      {/* Hidden file input for package import */}
      <input
        ref={importInputRef}
        type="file"
        accept=".zip,application/zip"
        onChange={(e) => { void handleImportFile(e); }}
        className="hidden"
        aria-label="Import system skill package file"
      />

      {importError && (
        <Alert
          type="error"
          title="Import failed"
          message={importError}
          onDismiss={() => setImportError(null)}
        />
      )}

      <div className="bg-white shadow rounded-lg overflow-x-auto overflow-visible">
        <Table
          data={skills}
          keyExtractor={(skill) => skill.skill_id.toString()}
          rowClassName={(skill) =>
            skill.is_enabled === false ? 'bg-gray-50 hover:bg-gray-100' : 'hover:bg-gray-50'
          }
          columns={[
            {
              header: 'Name',
              render: (skill) => (
                <div className="flex items-center">
                  <Target className="w-5 h-5 text-purple-400 mr-3 shrink-0" aria-hidden="true" />
                  <button
                    type="button"
                    className="text-sm font-medium text-gray-900 hover:text-blue-600 transition-colors text-left"
                    onClick={() => { void handleOpenEdit(skill); }}
                  >
                    {skill.name}
                  </button>
                </div>
              ),
            },
            {
              header: 'Description',
              render: (skill) => (
                <div className="text-sm text-gray-600 max-w-xs truncate">
                  {skill.description || <span className="text-gray-400 italic">No description</span>}
                </div>
              ),
              className: 'px-6 py-4',
            },
            {
              header: 'Status',
              render: (skill) => {
                const isEnabled = skill.is_enabled !== false;
                return (
                  <div className="flex flex-wrap items-center gap-1.5">
                    {skill.source === 'yaml' && (
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-700 border border-gray-300">
                        Seeded
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
              className: 'px-6 py-4 whitespace-nowrap',
            },
            {
              header: 'Created',
              render: (skill) => (skill.created_at ? new Date(skill.created_at).toLocaleDateString() : 'N/A'),
              className: 'px-6 py-4 whitespace-nowrap text-sm text-gray-500',
            },
            {
              header: 'Actions',
              className: 'relative',
              render: (skill) => {
                const isExporting = exportingSkillId === skill.skill_id;
                const isToggling = togglingSkillId === skill.skill_id;
                const isEnabled = skill.is_enabled !== false;

                const actions: ActionItem[] = [
                  {
                    label: 'Edit',
                    onClick: () => { void handleOpenEdit(skill); },
                    icon: <Pencil className="w-4 h-4" />,
                    variant: 'primary',
                  },
                  {
                    label: isExporting ? 'Exporting...' : 'Export',
                    onClick: () => { void handleExport(skill); },
                    icon: isExporting ? <Loader2 className="w-4 h-4 animate-spin" /> : <ArrowDownToLine className="w-4 h-4" />,
                    disabled: isExporting,
                    variant: 'secondary',
                  },
                  {
                    label: isToggling ? 'Updating...' : (isEnabled ? 'Disable' : 'Enable'),
                    onClick: () => { void handleToggleEnabled(skill); },
                    icon: isToggling
                      ? <Loader2 className="w-4 h-4 animate-spin" />
                      : (isEnabled ? <ToggleLeft className="w-4 h-4" /> : <ToggleRight className="w-4 h-4" />),
                    disabled: isToggling,
                    variant: isEnabled ? 'warning' : 'success',
                  },
                  {
                    label: 'Delete',
                    onClick: () => { void handleDelete(skill); },
                    icon: <Trash2 className="w-4 h-4" />,
                    variant: 'danger',
                  },
                ];

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
              },
            },
          ]}
          emptyIcon={<Target className="w-10 h-10 text-gray-300" />}
          emptyMessage="No system skills"
          emptySubMessage="Add the first system skill to make it available across every app."
          loading={isLoading}
        />
      </div>

      {/* Info Box */}
      <div className="bg-purple-50 border border-purple-200 rounded-lg p-4">
        <div className="flex">
          <div className="flex-shrink-0">
            <Lightbulb className="w-5 h-5 text-purple-400" aria-hidden="true" />
          </div>
          <div className="ml-3">
            <h2 className="text-sm font-medium text-purple-800">About system skills</h2>
            <div className="mt-2 text-sm text-purple-700">
              <p>
                System skills are shared across every app. Skills marked <strong>Seeded</strong> come from
                <code className="bg-purple-100 px-1 rounded ml-1">system_defaults.yaml</code> and are
                recreated on startup — they can&apos;t be deleted, only disabled.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Create/Edit Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={handleCloseModal}
        title={editingSkill ? 'Edit System Skill' : 'Create System Skill'}
        size="large"
      >
        <SkillForm
          skill={editingSkill}
          readOnly={false}
          onSubmit={handleSave}
          onCancel={handleCloseModal}
        />
      </Modal>
    </div>
  );
}

export default SystemSkillsPage;
