import { useCallback, useEffect, useRef, useState, type ChangeEvent } from 'react';
import { toast } from 'sonner';
import {
  Target,
  Pencil,
  Trash2,
  Upload,
  ArrowDownToLine,
  ToggleLeft,
  ToggleRight,
} from 'lucide-react';
import Modal from '../../components/ui/Modal';
import SkillForm, { type SkillFormSubmitData } from '../../components/forms/SkillForm';
import { apiService } from '../../services/api';
import ActionDropdown, { type ActionItem } from '../../components/ui/ActionDropdown';
import { LoadingState } from '../../components/ui/LoadingState';
import Alert from '../../components/ui/Alert';
import { Badge } from '../../components/ui/Badge';
import Table from '../../components/ui/Table';
import { useConfirm } from '../../contexts/ConfirmContext';
import { useApiMutation } from '../../hooks/useApiMutation';
import { MESSAGES, errorMessage } from '../../constants/messages';
import type { Skill } from '../../core/types';
import { ButtonApp } from '../../components/ui/ButtonApp';
import { Spinner } from '../../components/ui/Spinner';
import Title from '../../components/ui/Title';
import BackgroundImage from '../../components/ui/BackgroundImage';

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
    void fetchSkills();
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

  if (isLoading) return(
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <Title variant="titPrincipal" titulo="System Skills" subtitulo="Shared prompt-driven specializations, including disabled ones, available to every app." />
          </div>
          <LoadingState message="Loading system skills..." />
        </div>
      ) ;
  if (error) return;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Title variant="titPrincipal" titulo="System Skills" subtitulo="Shared prompt-driven specializations, including disabled ones, available to every app." />
        </div>
        <div className="flex gap-2">
          <ButtonApp
            label={importing ? 'Importing…' : 'Import package'}
            onClick={handleImportClick}
            loading={importing}
            variant="secondary"
            icon={<Upload className="w-4 h-4" />}
          />
          <ButtonApp
            label='Add service'
            onClick={handleOpenCreate}
            variant="primary"
            size="medium"
          />
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

      <div className="">
        <Table
          data={skills}
          keyExtractor={(skill) => skill.skill_id.toString()}
          columns={[
            {
              header: 'Name',
              render: (skill) => (
                <div className="flex items-center">
                  <BackgroundImage icon={Target} variant="marron" className="mr-2"/>
                  <button
                    type="button"
                    className="text-sm font-medium text-fg dark:text-fg-dark text-left"
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
                <div className="text-xs text-fg-secondary dark:text-fg-secondary-dark max-w-xs truncate">
                  {skill.description || "No description"}
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
                      <Badge label="Seeded" variant="default" />
                    )}
                    <Badge
                      label={isEnabled ? 'Enabled' : 'Disabled'}
                      variant={isEnabled ? 'success' : 'error'}
                    />
                  </div>
                );
              },
              className: 'px-6 py-4 whitespace-nowrap',
            },
            {
              header: 'Created',
              render: (skill) => (skill.created_at ? new Date(skill.created_at).toLocaleDateString() : 'N/A'),
              className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark',
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
                    icon: isExporting ? <Spinner size="sm" tone="current" /> : <ArrowDownToLine className="w-4 h-4" />,
                    disabled: isExporting,
                    variant: 'secondary',
                  },
                  {
                    label: isToggling ? 'Updating...' : (isEnabled ? 'Disable' : 'Enable'),
                    onClick: () => { void handleToggleEnabled(skill); },
                    icon: isToggling
                      ? <Spinner size="sm" tone="current" />
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

      <Alert
        type="info"
        title="About system skills"
        message={(
          <p>
            System skills are shared across every app. Skills marked <strong>Seeded</strong> come from
            <code className="px-1 rounded ml-1 font-mono">system_defaults.yaml</code> and are
            recreated on startup — they can&apos;t be deleted, only disabled.
          </p>
        )}
      />

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
