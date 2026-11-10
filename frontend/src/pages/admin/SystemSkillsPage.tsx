import { useCallback, useEffect, useRef, useState, type ChangeEvent } from 'react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import {
  Target,
  Pencil,
  Trash2,
  Upload,
  ArrowDownToLine,
  ToggleLeft,
  ToggleRight,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { apiService } from '../../services/api';
import ActionDropdown, { type ActionItem } from '../../components/ui/ActionDropdown';
import { LoadingState } from '../../components/ui/LoadingState';
import { ErrorState } from '../../components/ui/ErrorState';
import Alert from '../../components/ui/Alert';
import { Badge } from '../../components/ui/Badge';
import Table from '../../components/ui/Table';
import { useConfirm } from '../../contexts/ConfirmContext';
import { useApiMutation } from '../../hooks/useApiMutation';
import { errorMessage } from '../../constants/messages';
import type { Skill } from '../../core/types';
import { ButtonApp } from '../../components/ui/ButtonApp';
import { Spinner } from '../../components/ui/Spinner';
import Title from '../../components/ui/Title';
import BackgroundImage from '../../components/ui/BackgroundImage';

function SystemSkillsPage() {
  const { t, i18n } = useTranslation('common');
  const confirm = useConfirm();
  const mutate = useApiMutation();

  const [skills, setSkills] = useState<Skill[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

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
      setError(errorMessage(err, t('systemSkillsPage.loadFailed')));
    } finally {
      setIsLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void fetchSkills();
  }, [fetchSkills]);

  function handleOpenCreate() {
    navigate('/admin/system-skills/new');
  }

  function handleOpenEdit(skill: Skill) {
    navigate(`/admin/system-skills/${skill.skill_id}/edit`);
  }

  async function handleDelete(skill: Skill) {
    const ok = await confirm({
      title: t('skillsPage.confirmDeleteTitle'),
      message: t('skillsPage.confirmDeleteMessage', { name: skill.name }),
      variant: 'danger',
      confirmLabel: t('skillsPage.actions.delete'),
    });
    if (!ok) return;

    // The backend rejects deletion of yaml-seeded/frozen/in-use skills with a 409 whose
    // `detail` is a human-readable explanation (e.g. "seeded from system_defaults.yaml —
    // disable it instead"). errorMessage() surfaces that ApiError message verbatim, so the
    // toast below never shows a raw dump — it shows exactly what the backend explains.
    const result = await mutate(
      () => apiService.deleteSystemSkill(skill.skill_id),
      {
        loading: t('skillsPage.notifications.deleting'),
        success: t('skillsPage.notifications.deleted'),
        error: (err) => errorMessage(err, t('skillsPage.notifications.deleteFailed')),
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
      setImportError(t('skillsPage.import.invalidFile'));
      return;
    }

    setImporting(true);
    setImportError(null);
    try {
      await apiService.importSystemSkill(file);
      await fetchSkills();
      toast.success(t('skillsPage.notifications.imported'));
    } catch (err) {
      // Surface the backend's actual 400/409 reason (duplicate name, archive limits, etc.)
      const message = errorMessage(err, t('skillsPage.import.failed'));
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

      toast.success(t('skillsPage.notifications.exported'));
    } catch (err) {
      toast.error(errorMessage(err, t('skillsPage.notifications.exportFailed')));
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
      toast.success(nextEnabled ? t('skillsPage.notifications.enabled') : t('skillsPage.notifications.disabled'));
    } catch (err) {
      toast.error(errorMessage(err, t('skillsPage.notifications.statusUpdateFailed')));
    } finally {
      setTogglingSkillId(null);
    }
  }

  if (isLoading) return(
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <Title variant="titPrincipal" titulo={t('systemSkillsPage.title')} subtitulo={t('systemSkillsPage.subtitle')} />
          </div>
          <LoadingState message={t('systemSkillsPage.loading')} />
        </div>
      ) ;
  if (error) return <ErrorState error={error} onRetry={fetchSkills} />;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Title variant="titPrincipal" titulo={t('systemSkillsPage.title')} subtitulo={t('systemSkillsPage.subtitle')} />
        </div>
        <div className="flex gap-2">
          <ButtonApp
            label={importing ? t('skillsPage.actions.importing') : t('skillsPage.actions.importPackage')}
            onClick={handleImportClick}
            loading={importing}
            variant="secondary"
            icon={<Upload className="w-4 h-4" />}
          />
          <ButtonApp
            label={t('systemSkillsPage.addSkill')}
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
        aria-label={t('skillsPage.import.fileInputLabel')}
      />

      {importError && (
        <Alert
          type="error"
          title={t('skillsPage.import.failedTitle')}
          message={importError}
          onDismiss={() => setImportError(null)}
        />
      )}

      <div className="">
        <Table
          data={skills}
          stickyEdgeColumns
          keyExtractor={(skill) => skill.skill_id.toString()}
          columns={[
            {
              header: t('skillsPage.columns.name'),
              render: (skill) => (
                <div className="flex items-center">
                  <BackgroundImage icon={Target} variant="marron" className="mr-2" size={34} iconSize={17} />
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
              header: t('skillsPage.columns.description'),
              render: (skill) => (
                <div className="text-xs text-fg-secondary dark:text-fg-secondary-dark max-w-xs truncate">
                  {skill.description || t('skillsPage.noDescription')}
                </div>
              ),
              className: 'px-6 py-4',
            },
            {
              header: t('skillsPage.columns.status'),
              render: (skill) => {
                const isEnabled = skill.is_enabled !== false;
                return (
                  <div className="flex flex-wrap items-center gap-1.5">
                    {skill.source === 'yaml' && (
                      <Badge label={t('systemSkillsPage.seeded')} variant="default" />
                    )}
                    <Badge
                      label={isEnabled ? t('skillsPage.statuses.enabled') : t('skillsPage.statuses.disabled')}
                      variant={isEnabled ? 'success' : 'error'}
                    />
                  </div>
                );
              },
              className: 'px-6 py-4 whitespace-nowrap',
            },
            {
              header: t('skillsPage.columns.created'),
              render: (skill) => (skill.created_at ? new Date(skill.created_at).toLocaleDateString(i18n.language) : t('skillsPage.notAvailable')),
              className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark',
            },
            {
              header: t('skillsPage.columns.actions'),
              sticky: 'right' as const,
              className: 'relative',
              render: (skill) => {
                const isExporting = exportingSkillId === skill.skill_id;
                const isToggling = togglingSkillId === skill.skill_id;
                const isEnabled = skill.is_enabled !== false;

                const actions: ActionItem[] = [
                  {
                    label: t('skillsPage.actions.edit'),
                    onClick: () => { void handleOpenEdit(skill); },
                    icon: <Pencil className="w-4 h-4" />,
                    variant: 'primary',
                  },
                  {
                    label: isExporting ? t('skillsPage.actions.exporting') : t('skillsPage.actions.export'),
                    onClick: () => { void handleExport(skill); },
                    icon: isExporting ? <Spinner size="sm" tone="current" /> : <ArrowDownToLine className="w-4 h-4" />,
                    disabled: isExporting,
                    variant: 'secondary',
                  },
                  {
                    label: isToggling
                      ? t('skillsPage.actions.updating')
                      : (isEnabled ? t('skillsPage.actions.disable') : t('skillsPage.actions.enable')),
                    onClick: () => { void handleToggleEnabled(skill); },
                    icon: isToggling
                      ? <Spinner size="sm" tone="current" />
                      : (isEnabled ? <ToggleLeft className="w-4 h-4" /> : <ToggleRight className="w-4 h-4" />),
                    disabled: isToggling,
                    variant: isEnabled ? 'warning' : 'success',
                  },
                  {
                    label: t('skillsPage.actions.delete'),
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
                      triggerAriaLabel={t('skillsPage.actions.forSkill', { name: skill.name })}
                    />
                    {(isExporting || isToggling) && (
                      <span role="status" aria-live="polite" className="sr-only">
                        {isExporting
                          ? t('skillsPage.actions.exportingSkill', { name: skill.name })
                          : t('skillsPage.actions.updatingSkill', { name: skill.name })}
                      </span>
                    )}
                  </>
                );
              },
            },
          ]}
          emptyIcon={<BackgroundImage icon={Target} size={64} iconSize={32} />}
          emptyMessage={t('systemSkillsPage.emptyTitle')}
          emptySubMessage={t('systemSkillsPage.emptyDescription')}
          loading={isLoading}
        />
      </div>

      {!isLoading && skills.length === 0 && (
        <div className="text-center py-6">
          <ButtonApp
            label={t('systemSkillsPage.addFirstSkill')}
            onClick={handleOpenCreate}
            variant="primary"
            size="medium"
          />
        </div>
      )}

      <Alert
        type="info"
        title={t('systemSkillsPage.aboutTitle')}
        message={(
          <p>
            {t('systemSkillsPage.aboutIntro')} <strong>{t('systemSkillsPage.seeded')}</strong> {t('systemSkillsPage.aboutSource')}
            <code className="px-1 rounded ml-1 font-mono">system_defaults.yaml</code> {t('systemSkillsPage.aboutOutro')}
          </p>
        )}
      />
    </div>
  );
}

export default SystemSkillsPage;
