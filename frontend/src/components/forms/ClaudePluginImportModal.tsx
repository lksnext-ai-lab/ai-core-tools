import { useEffect, useId, useRef, useState, type ChangeEvent } from 'react';
import {
  ShieldAlert,
  Upload,
} from 'lucide-react';
import Modal from '../ui/Modal';
import Alert from '../ui/Alert';
import { apiService } from '../../services/api';
import { errorMessage } from '../../constants/messages';
import type { ClaudePluginImportResult, ClaudePluginSkillResult } from '../../core/types';
import { ButtonApp } from '../ui/ButtonApp';
import { FormField } from '../ui/FormField';
import { StatusBadge } from '../ui/Badge';
import { useTranslation } from 'react-i18next';

export interface ClaudePluginImportModalProps {
  readonly appId: number;
  readonly isOpen: boolean;
  readonly onClose: () => void;
  /** Called whenever the import produced at least one report — lets the caller refresh the skills list. */
  readonly onImported: () => void;
}

type Phase = 'idle' | 'submitting' | 'done';

function statusBadge(
  status: ClaudePluginSkillResult['status'],
  labels: Record<ClaudePluginSkillResult['status'], string>,
) {
  if (status === 'imported') return <StatusBadge status="success" customLabel={labels.imported} />;
  if (status === 'skipped') return <StatusBadge status="warning" customLabel={labels.skipped} />;
  return <StatusBadge status="error" customLabel={labels.failed} />;
}

/**
 * Uploads a Claude Code plugin (.zip) and renders a per-skill import report. Imported skills
 * land disabled (`is_enabled=False`) — this modal surfaces `has_bootstrap` prominently so an
 * admin reviewing the report knows which entries will run a bootstrap script once enabled,
 * before they flip the existing enable toggle on SkillsPage. `allowed_tools` is informational
 * metadata only and is never read/enforced here (AD-15).
 */
function ClaudePluginImportModal({ appId, isOpen, onClose, onImported }: ClaudePluginImportModalProps) {
  const { t } = useTranslation('common');
  const [phase, setPhase] = useState<Phase>('idle');
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ClaudePluginImportResult | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const fileInputId = useId();

  // Focus targets for the phase transitions the `Modal` wrapper doesn't know about — its own
  // focus-management effect only re-runs on `isOpen`, not when this modal swaps its *internal*
  // phase (upload <-> report), so we move focus into the newly-rendered phase root ourselves.
  // Also doubles as the persistent aria-live host for the report summary (see below): keeping it
  // mounted for the whole modal lifetime and only mutating its text once the report exists means
  // screen readers see a content *update*, not an *insertion* of an already-populated live region.
  const summaryStatusRef = useRef<HTMLDivElement>(null);
  const uploadIntroRef = useRef<HTMLParagraphElement>(null);
  // Previous-value comparison rather than a boolean "first run" latch — a plain latch flips to
  // false on the first of React 18 StrictMode's two dev-mode mount invocations and then wrongly
  // fires focus-stealing logic on the second, overriding `Modal`'s own initial-focus placement.
  // Comparing against the last-seen phase is invocation-count-agnostic: it only acts on an actual
  // phase change, no matter how many times the effect itself re-runs for the same phase value.
  const prevPhaseRef = useRef(phase);

  const isSubmitting = phase === 'submitting';

  useEffect(() => {
    const prev = prevPhaseRef.current;
    prevPhaseRef.current = phase;
    if (prev === phase) return;
    if (phase === 'done') {
      summaryStatusRef.current?.focus();
    } else if (phase === 'idle') {
      uploadIntroRef.current?.focus();
    }
  }, [phase]);

  function reset() {
    setPhase('idle');
    setError(null);
    setResult(null);
    setSelectedFile(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  }

  function handleClose() {
    // A successful (even partial) report means at least one skill row may have changed —
    // refresh the caller's list on every close after a completed attempt, not just success.
    if (result) onImported();
    reset();
    onClose();
  }

  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null;
    setError(null);
    if (file && !file.name.toLowerCase().endsWith('.zip')) {
      setError(t('skillsPage.claudePluginImport.invalidFile'));
      setSelectedFile(null);
      return;
    }
    setSelectedFile(file);
  }

  async function handleSubmit() {
    if (!selectedFile) {
      setError(t('skillsPage.claudePluginImport.chooseFile'));
      return;
    }

    setPhase('submitting');
    setError(null);
    try {
      const response = await apiService.importClaudePlugin(appId, selectedFile);
      setResult(response);
      setPhase('done');
    } catch (err) {
      setError(errorMessage(err, t('skillsPage.claudePluginImport.failed')));
      setPhase('idle');
    }
  }

  function handleRetry() {
    setResult(null);
    setError(null);
    setPhase('idle');
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title={t('skillsPage.claudePluginImport.title')}
      size="medium"
    >
      <div className="space-y-4">
        {/* Persistent live region: always mounted (empty/hidden until a report exists) so the
            summary text change is announced as a mutation rather than relying on a freshly
            inserted, already-populated `role="status"` node — the latter is unreliable with
            screen readers. `tabIndex={-1}` also makes it the focus target when the report phase
            mounts (see the phase-transition effect above). */}
        <div
          ref={summaryStatusRef}
          role="status"
          aria-live="polite"
          tabIndex={-1}
          className={result ? 'text-sm text-fg dark:text-fg-dark outline-none' : 'sr-only'}
        >
          {result
            ? t('skillsPage.claudePluginImport.summary', {
                imported: result.imported_count,
                skipped: result.skipped_count,
                failed: result.failed_count,
              })
            : ''}
        </div>

        {!result && (
          <>
            <p ref={uploadIntroRef} tabIndex={-1} className="text-sm text-fg-secondary dark:text-fg-secondary-dark outline-none">
              {t('skillsPage.claudePluginImport.introBeforePath')}{' '}
              <code className="bg-fg-tertiary dark:bg-tertiary-dark px-1 rounded">skills/&lt;name&gt;/SKILL.md</code>{' '}
              {t('skillsPage.claudePluginImport.introAfterPath')}
            </p>

            {error && <Alert type="error" message={error} />}

            <FormField
              ref={fileInputRef}
              id={fileInputId}
              label={t('skillsPage.claudePluginImport.packageLabel')}
              type="file"
              accept=".zip,application/zip"
              onChange={handleFileChange}
              disabled={isSubmitting}
              helpText={t('skillsPage.claudePluginImport.packageHelp')}
            />

            <div className="flex items-center justify-end gap-3 pt-4 border-t border-line dark:border-line-dark bg-surface dark:bg-surface-dark">
              <ButtonApp
                label={t('cancel')}
                type="button"
                onClick={handleClose}
                disabled={isSubmitting}
                variant="secondary"
                size="medium"
              />
              <ButtonApp
                label={isSubmitting
                  ? t('skillsPage.claudePluginImport.importing')
                  : t('skillsPage.claudePluginImport.import')}
                onClick={() => { void handleSubmit(); }}
                disabled={!selectedFile}
                loading={isSubmitting}
                icon={<Upload className="w-4 h-4" aria-hidden="true" />}
              />
              {/* A button label swap alone isn't reliably announced (WCAG 4.1.3) — mirror the
                  sr-only status pattern already used for async actions in SkillsPage. */}
              <span role="status" aria-live="polite" className="sr-only">
                {isSubmitting ? t('skillsPage.claudePluginImport.importingStatus') : ''}
              </span>
            </div>
          </>
        )}

        {result && (
          <div className="space-y-4">
            {result.skills.some((s) => s.has_bootstrap) && (
              <Alert
                type="error"
                title={t('skillsPage.claudePluginImport.reviewTitle')}
                message={t('skillsPage.claudePluginImport.reviewMessage')}
              />
            )}

            <ul className="divide-y divide-line dark:divide-btCard-border-dark border dark:border-btCard-border-dark rounded-md overflow-hidden">
              {result.skills.map((skill) => (
                <li key={skill.name} className="p-3 bg-surface dark:bg-surface-dark">
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <span className="text-sm font-mono font-medium text-fg dark:text-fg-dark">
                      {skill.name}
                    </span>
                    <div className="flex items-center gap-1.5 flex-wrap">
                      {skill.has_bootstrap && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-red-50 text-red-700 border border-red-200 dark:bg-red-900/30 dark:text-red-300 dark:border-red-800">
                          <ShieldAlert className="w-3.5 h-3.5" aria-hidden="true" />
                          {t('skillsPage.claudePluginImport.runsBootstrap')}
                        </span>
                      )}
                      {statusBadge(skill.status, {
                        imported: t('skillsPage.claudePluginImport.status.imported'),
                        skipped: t('skillsPage.claudePluginImport.status.skipped'),
                        failed: t('skillsPage.claudePluginImport.status.failed'),
                      })}
                    </div>
                  </div>
                  {skill.reason && (skill.status === 'skipped' || skill.status === 'failed') && (
                    <p className="mt-1 text-xs text-fg-secondary dark:text-fg-secondary-dark">{skill.reason}</p>
                  )}
                  {skill.has_bootstrap && skill.bootstrap_script_path && (
                    <p className="mt-1 text-xs text-fg-secondary dark:text-fg-secondary-dark font-mono">
                      {skill.bootstrap_script_path}
                      {skill.runtime ? ` (${skill.runtime})` : ''}
                    </p>
                  )}
                </li>
              ))}
            </ul>

            <div className="flex items-center justify-end gap-3 pt-4 border-t border-line dark:border-line-dark ">
              <ButtonApp
                label={t('skillsPage.claudePluginImport.importAnother')}
                type="button"
                variant="secondary"
                size="control"
                onClick={handleRetry}
              />
              <ButtonApp
                label={t('skillsPage.claudePluginImport.done')}
                type="button"
                variant="primary"
                size="control"
                onClick={handleClose}
              />
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}

export default ClaudePluginImportModal;
