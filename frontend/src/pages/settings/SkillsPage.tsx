import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
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

function SkillsPage() {
  const { appId } = useParams();
  const settingsCache = useSettingsCache();
  const { hasMinRole, userRole } = useAppRole(appId);
  const canEdit = hasMinRole(AppRole.ADMINISTRATOR);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingSkill, setEditingSkill] = useState<any>(null);

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
      const response = await apiService.getSkills(parseInt(appId));
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

  async function forceReloadSkills() {
    if (!appId) return;

    try {
      setLoading(true);
      setError(null);
      const response = await apiService.getSkills(parseInt(appId));
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
    if (!confirm('Are you sure you want to delete this skill?')) {
      return;
    }

    if (!appId) return;

    try {
      await apiService.deleteSkill(parseInt(appId), skillId);
      // Remove from local state
      const newSkills = skills.filter(s => s.skill_id !== skillId);
      setSkills(newSkills);
      // Update cache
      settingsCache.setSkills(appId, newSkills);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete skill');
      console.error('Error deleting skill:', err);
    }
  }

  function handleCreateSkill() {
    setEditingSkill(null);
    setIsModalOpen(true);
  }

  async function handleEditSkill(skillId: number) {
    if (!appId) return;

    try {
      const skill = await apiService.getSkill(parseInt(appId), skillId);
      setEditingSkill(skill);
      setIsModalOpen(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load skill details');
      console.error('Error loading skill:', err);
    }
  }

  async function handleSaveSkill(data: any) {
    if (!appId) return;

    try {
      if (editingSkill && editingSkill.skill_id !== 0) {
        // Update existing skill
        await apiService.updateSkill(parseInt(appId), editingSkill.skill_id, data);
        await loadSkills();
      } else {
        // Create new skill - invalidate cache and force reload
        await apiService.createSkill(parseInt(appId), data);
        settingsCache.invalidateSkills(appId);
        await forceReloadSkills();
      }

      setIsModalOpen(false);
      setEditingSkill(null);
    } catch (err) {
      throw new Error(err instanceof Error ? err.message : 'Failed to save skill');
    }
  }

  function handleCloseModal() {
    setIsModalOpen(false);
    setEditingSkill(null);
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
          <p className="text-gray-600">Manage prompt-driven specializations for your agents</p>
        </div>
        {canEdit && (
          <button
            onClick={handleCreateSkill}
            className="bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-lg flex items-center"
          >
            <span className="mr-2">+</span>
            {' '}Add Skill
          </button>
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
                <span className="text-purple-400 text-xl mr-3">🎯</span>
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
            header: 'Created',
            render: (skill) => skill.created_at ? new Date(skill.created_at).toLocaleDateString() : 'N/A',
            className: 'px-6 py-4 whitespace-nowrap text-sm text-gray-500'
          },
          {
            header: 'Actions',
            className: 'relative',
            render: (skill) => (
              canEdit ? (
                <ActionDropdown
                  actions={[
                    {
                      label: 'Edit',
                      onClick: () => { void handleEditSkill(skill.skill_id); },
                      icon: '✏️',
                      variant: 'primary'
                    },
                    {
                      label: 'Delete',
                      onClick: () => { void handleDelete(skill.skill_id); },
                      icon: '🗑️',
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
        emptyIcon="🎯"
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
            <span className="text-purple-400 text-xl">💡</span>
          </div>
          <div className="ml-3">
            <h3 className="text-sm font-medium text-purple-800">
              About Skills
            </h3>
            <div className="mt-2 text-sm text-purple-700">
              <p>
                Skills are prompt-driven specializations that agents can dynamically load on-demand.
                When an agent has skills assigned, it gains a <code className="bg-purple-100 px-1 rounded">load_skill</code> tool
                that allows it to activate specialized behavior when needed.
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
