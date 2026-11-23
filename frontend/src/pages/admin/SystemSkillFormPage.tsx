import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import SkillForm, { type SkillFormSubmitData } from '../../components/forms/SkillForm';
import { apiService } from '../../services/api';
import { useApiMutation } from '../../hooks/useApiMutation';
import { errorMessage } from '../../constants/messages';
import type { Skill } from '../../core/types';
import { LoadingState } from '../../components/ui/LoadingState';
import Alert from '../../components/ui/Alert';
import Title from '../../components/ui/Title';

const LIST_PATH = '/admin/system-skills';

/** Create / edit a platform-wide (system) skill as a full page. */
function SystemSkillFormPage() {
  const { skillId } = useParams();
  const navigate = useNavigate();
  const { t } = useTranslation('common');
  const mutate = useApiMutation();

  const isEditing = skillId !== undefined;
  const [skill, setSkill] = useState<Skill | null>(null);
  const [loading, setLoading] = useState(isEditing);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!skillId) {
      setSkill(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    apiService
      .getSystemSkill(Number.parseInt(skillId))
      .then((detail: Skill) => {
        if (!cancelled) setSkill(detail);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(errorMessage(err, t('systemSkillsPage.loadFailed')));
        console.error('Error loading system skill:', err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [skillId, t]);

  const pageTitle = isEditing ? t('systemSkillsPage.editTitle') : t('systemSkillsPage.createTitle');

  function goBackToList() {
    navigate(LIST_PATH);
  }

  async function handleSave(data: SkillFormSubmitData) {
    const isUpdate = skill !== null;

    const result = await mutate(
      () =>
        isUpdate
          ? apiService.updateSystemSkill(skill.skill_id, data)
          : apiService.createSystemSkill(data),
      {
        loading: isUpdate ? t('skillsPage.notifications.updating') : t('skillsPage.notifications.creating'),
        success: isUpdate ? t('skillsPage.notifications.updated') : t('skillsPage.notifications.created'),
        error: (err) => errorMessage(err, t('skillsPage.notifications.saveFailed')),
      },
    );
    if (result === undefined) return;

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
      {/* Platform admins can edit system skills here, so the read-only gate is explicitly off. */}
      <SkillForm skill={skill} readOnly={false} onSubmit={handleSave} onCancel={goBackToList} />
    </div>
  );
}

export default SystemSkillFormPage;
