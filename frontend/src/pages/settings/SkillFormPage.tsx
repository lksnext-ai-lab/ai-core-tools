import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import SkillForm, { type SkillFormSubmitData } from '../../components/forms/SkillForm';
import { apiService } from '../../services/api';
import { useSettingsCache } from '../../contexts/SettingsCacheContext';
import { useAppRole } from '../../hooks/useAppRole';
import { useApiMutation } from '../../hooks/useApiMutation';
import { errorMessage } from '../../constants/messages';
import { AppRole } from '../../types/roles';
import type { Skill } from '../../core/types';
import { LoadingState } from '../../components/ui/LoadingState';
import Alert from '../../components/ui/Alert';
import Title from '../../components/ui/Title';

/** Create / edit (or view, when read-only) an app-scoped skill as a full page. */
function SkillFormPage() {
  const { appId, skillId } = useParams();
  const navigate = useNavigate();
  const { t } = useTranslation('common');
  const settingsCache = useSettingsCache();
  const { hasMinRole, userRole } = useAppRole(appId);
  const canEdit = hasMinRole(AppRole.ADMINISTRATOR);
  const mutate = useApiMutation();

  const isEditing = skillId !== undefined;
  const [skill, setSkill] = useState<Skill | null>(null);
  const [loading, setLoading] = useState(isEditing);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!appId || !skillId) {
      setSkill(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    apiService
      .getSkill(Number.parseInt(appId), Number.parseInt(skillId))
      .then((detail: Skill) => {
        if (!cancelled) setSkill(detail);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(errorMessage(err, t('skillsPage.loadDetailsFailed')));
        console.error('Error loading skill:', err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [appId, skillId, t]);

  // Same rule the list used for the modal: every visible skill can be opened, but only
  // skills the viewer can actually manage render editable.
  const isReadOnly = Boolean(skill) && !(canEdit && !skill?.is_system);

  let pageTitle = t('skillsPage.modal.createSkill');
  if (isEditing) {
    pageTitle = isReadOnly ? t('skillsPage.modal.viewSkill') : t('skillsPage.modal.editSkill');
  }

  function goBackToList() {
    navigate(`/apps/${appId}/skills`);
  }

  async function handleSave(data: SkillFormSubmitData) {
    if (!appId) return;

    const isUpdate = Boolean(skill && skill.skill_id !== 0);
    const result = await mutate<Skill>(
      () =>
        isUpdate && skill
          ? apiService.updateSkill(Number.parseInt(appId), skill.skill_id, data)
          : apiService.createSkill(Number.parseInt(appId), data),
      {
        loading: t(isUpdate ? 'skillsPage.notifications.updating' : 'skillsPage.notifications.creating'),
        success: t(isUpdate ? 'skillsPage.notifications.updated' : 'skillsPage.notifications.created'),
        error: (err) => errorMessage(err, t('skillsPage.notifications.saveFailed')),
      },
    );
    if (result === undefined) return;

    // The list reads from the settings cache first — drop it so it reloads fresh data.
    settingsCache.invalidateSkills(appId);
    goBackToList();
  }

  const header = (
    <div className="flex items-center justify-between">
      <Title variant="titPrincipal" titulo={pageTitle} subtitulo={t('skillsPage.formSubtitle')} />
    </div>
  );

  if (loading) {
    return (
      <div className="space-y-6">
        {header}
        <LoadingState variant="page" message={t('skillsPage.loading')} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        {header}
        <Alert type="error" message={error} onDismiss={goBackToList} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      {header}
      <SkillForm
        skill={skill}
        readOnly={isReadOnly}
        userRole={userRole}
        onSubmit={handleSave}
        onCancel={goBackToList}
      />
    </div>
  );
}

export default SkillFormPage;
