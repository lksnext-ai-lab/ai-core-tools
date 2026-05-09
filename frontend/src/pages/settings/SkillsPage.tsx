import { useRef, useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { Target, Pencil, Trash2, Lightbulb, Upload, Download, Package } from 'lucide-react';
import Modal from '../../components/ui/Modal';
import SkillForm from '../../components/forms/SkillForm';
import { apiService } from '../../services/api';
import ActionDropdown from '../../components/ui/ActionDropdown';
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
  const [isImporting, setIsImporting] = useState(false);
  const importInputRef = useRef<HTMLInputElement>(null);

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
    importInputRef.current?.click();
  }

  async function handleImportFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    if (!appId) return;

    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;

    try {
      setIsImporting(true);
      setError(null);
      await apiService.importSkillPackage(Number.parseInt(appId), file);
      await _forceReloadSkills();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to import skill package');
      console.error('Error importing skill package:', err);
    } finally {
      setIsImporting(false);
    }
  }

  async function handleExportSkill(skill: Skill) {
    if (!appId) return;

    try {
      const blob = await apiService.exportSkillPackage(Number.parseInt(appId), skill.skill_id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${skill.name || `skill-${skill.skill_id}`}.zip`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to export skill package');
      console.error('Error exporting skill package:', err);
    }
  }

  function getResourceCount(skill: Skill) {
    return skill.file_count ?? (skill as any).files?.length ?? 0;
  }

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
          <p className="text-gray-600">Manage portable Skill packages with SKILL.md and bundled resources</p>
        </div>
        {canEdit && (
          <div className="flex items-center gap-2">
            <input
              ref={importInputRef}
              type="file"
              accept=".zip,application/zip"
              className="hidden"
              onChange={(event) => { void handleImportFileChange(event); }}
            />
            <button
              onClick={handleImportClick}
              disabled={isImporting}
              className="border border-gray-300 bg-white hover:bg-gray-50 disabled:opacity-60 text-gray-700 px-4 py-2 rounded-lg flex items-center"
            >
              <Upload className="w-4 h-4 mr-2" />
              {isImporting ? 'Importing...' : 'Import ZIP'}
            </button>
            <button
              onClick={handleCreateSkill}
              className="bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-lg flex items-center"
            >
              <span className="mr-2">+</span>
              Add Skill
            </button>
          </div>
        )}
      </div>

      {/* Read-only banner for non-admins */}
      {!canEdit && <ReadOnlyBanner userRole={userRole} minRole={AppRole.ADMINISTRATOR} />}

      {/* Skills Table */}
      <Table
        data={skills}
        keyExtractor={(skill) => skill.skill_id.toString()}
        columns={[
          {
            header: 'Name',
            render: (skill) => (
              <div className="flex items-center">
                <Target className="w-5 h-5 text-purple-400 mr-3 shrink-0" />
                {canEdit ? (
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
            )
          },
          {
            header: 'Description',
            render: (skill) => (
              <div className="text-sm text-gray-600 max-w-xs truncate">
                {skill.description || <span className="text-gray-400 italic">No description</span>}
              </div>
            ),
            className: 'px-6 py-4'
          },
          {
            header: 'Package',
            render: (skill) => (
              <div className="flex items-center gap-2">
                {(skill as any).is_builtin && (
                  <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">builtin</span>
                )}
                {(skill as any).is_frozen && (
                  <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-gray-100 text-gray-700">frozen</span>
                )}
                {!(skill as any).is_builtin && !(skill as any).is_frozen && (
                  <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-green-100 text-green-700">package</span>
                )}
              </div>
            ),
            className: 'px-6 py-4'
          },
          {
            header: 'Resources',
            render: (skill) => {
              const count = getResourceCount(skill);
              return (
                <div className="flex items-center gap-2 text-sm text-gray-600">
                  <Package className="w-4 h-4 text-gray-400" />
                  {count === 0 ? 'SKILL.md only' : `${count} bundled ${count === 1 ? 'file' : 'files'}`}
                </div>
              );
            },
            className: 'px-6 py-4 whitespace-nowrap'
          },
          {
            header: 'Activation',
            render: (skill) => (
              <div className="text-sm text-gray-600">
                {(skill as any).bootstrap_script_path ? (
                  <span className="font-mono text-xs text-gray-700">{(skill as any).bootstrap_script_path}</span>
                ) : (
                  <span className="text-gray-400">no bootstrap</span>
                )}
              </div>
            ),
            className: 'px-6 py-4'
          },
          {
            header: 'Created',
            render: (skill) => skill.created_at ? new Date(skill.created_at).toLocaleDateString() : 'N/A',
            className: 'px-6 py-4 whitespace-nowrap text-sm text-gray-500'
          },
          {
            header: 'Actions',
            className: 'relative',
            render: (skill) => (
              <ActionDropdown
                actions={[
                  {
                    label: 'Export ZIP',
                    onClick: () => { void handleExportSkill(skill); },
                    icon: <Download className="w-4 h-4" />,
                    variant: 'secondary'
                  },
                  {
                    label: 'Edit',
                    onClick: () => { void handleEditSkill(skill.skill_id); },
                    icon: <Pencil className="w-4 h-4" />,
                    variant: 'primary',
                    disabled: !canEdit || Boolean((skill as any).is_builtin || (skill as any).is_frozen)
                  },
                  {
                    label: 'Delete',
                    onClick: () => { void handleDelete(skill.skill_id); },
                    icon: <Trash2 className="w-4 h-4" />,
                    variant: 'danger',
                    disabled: !canEdit || Boolean((skill as any).is_builtin || (skill as any).is_frozen)
                  }
                ]}
                size="sm"
              />
            )
          }
        ]}
        emptyIcon={<Target className="w-10 h-10 text-gray-300" />}
        emptyMessage="No Skills"
        emptySubMessage="Create or import a Skill package to add reusable agent capabilities."
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
                Skills are portable packages built around <code className="bg-purple-100 px-1 rounded">SKILL.md</code>.
                Agents see metadata first, load instructions when relevant, and copy bundled resources into the sandbox only when needed.
              </p>
              <div className="mt-2">
                <strong>Package structure:</strong>
                <ul className="list-disc list-inside mt-1 space-y-1">
                  <li>SKILL.md - metadata and activation instructions</li>
                  <li>scripts/ - optional reviewed setup or helper scripts</li>
                  <li>references/ - optional detailed documentation loaded on demand</li>
                  <li>assets/ - optional templates, images, or binary resources</li>
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
