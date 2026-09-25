import { useEffect, useId, useRef, useState, type ChangeEvent } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  ShieldAlert,
  Upload,
  XCircle,
} from 'lucide-react';
import Modal from '../ui/Modal';
import { FormError } from '../ui/FormError';
import { apiService } from '../../services/api';
import { errorMessage } from '../../constants/messages';
import type { ClaudePluginImportResult, ClaudePluginSkillResult } from '../../core/types';

export interface ClaudePluginImportModalProps {
  readonly appId: number;
  readonly isOpen: boolean;
  readonly onClose: () => void;
  /** Called whenever the import produced at least one report — lets the caller refresh the skills list. */
  readonly onImported: () => void;
}

type Phase = 'idle' | 'submitting' | 'done';

function statusBadge(status: ClaudePluginSkillResult['status']) {
  if (status === 'imported') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-green-50 text-green-700 border border-green-200 dark:bg-green-900/30 dark:text-green-300 dark:border-green-800">
        <CheckCircle2 className="w-3.5 h-3.5" aria-hidden="true" />
        Imported
      </span>
    );
  }
  if (status === 'skipped') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200 dark:bg-amber-900/30 dark:text-amber-300 dark:border-amber-800">
        <AlertTriangle className="w-3.5 h-3.5" aria-hidden="true" />
        Skipped
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-red-50 text-red-700 border border-red-200 dark:bg-red-900/30 dark:text-red-300 dark:border-red-800">
      <XCircle className="w-3.5 h-3.5" aria-hidden="true" />
      Failed
    </span>
  );
}

/**
 * Uploads a Claude Code plugin (.zip) and renders a per-skill import report. Imported skills
 * land disabled (`is_enabled=False`) — this modal surfaces `has_bootstrap` prominently so an
 * admin reviewing the report knows which entries will run a bootstrap script once enabled,
 * before they flip the existing enable toggle on SkillsPage. `allowed_tools` is informational
 * metadata only and is never read/enforced here (AD-15).
 */
function ClaudePluginImportModal({ appId, isOpen, onClose, onImported }: ClaudePluginImportModalProps) {
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
      setError('Please select a valid Claude Code plugin package (.zip file).');
      setSelectedFile(null);
      return;
    }
    setSelectedFile(file);
  }

  async function handleSubmit() {
    if (!selectedFile) {
      setError('Please choose a .zip file to import.');
      return;
    }

    setPhase('submitting');
    setError(null);
    try {
      const response = await apiService.importClaudePlugin(appId, selectedFile);
      setResult(response);
      setPhase('done');
    } catch (err) {
      setError(errorMessage(err, 'Failed to import Claude Code plugin'));
      setPhase('idle');
    }
  }

  function handleRetry() {
    setResult(null);
    setError(null);
    setPhase('idle');
  }

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Import Claude Code Plugin" size="medium">
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
          className={result ? 'text-sm text-gray-700 dark:text-gray-300 outline-none' : 'sr-only'}
        >
          {result
            ? `${result.imported_count} imported, ${result.skipped_count} skipped, ${result.failed_count} failed.`
            : ''}
        </div>

        {!result && (
          <>
            <p ref={uploadIntroRef} tabIndex={-1} className="text-sm text-gray-600 dark:text-gray-400 outline-none">
              Upload a Claude Code plugin package (.zip). Each <code className="bg-gray-100 dark:bg-gray-700 px-1 rounded">skills/&lt;name&gt;/SKILL.md</code>{' '}
              found in the archive is imported as a disabled skill so an administrator can review
              it — including any bootstrap script it carries — before enabling it.
            </p>

            <FormError error={error} />

            <div>
              <label
                htmlFor={fileInputId}
                className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2"
              >
                Plugin package
              </label>
              <input
                ref={fileInputRef}
                id={fileInputId}
                type="file"
                accept=".zip,application/zip"
                onChange={handleFileChange}
                disabled={isSubmitting}
                aria-describedby={`${fileInputId}-help`}
                className="block w-full text-sm text-gray-700 dark:text-gray-200 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-purple-50 file:text-purple-700 hover:file:bg-purple-100 dark:file:bg-purple-900/40 dark:file:text-purple-200 dark:hover:file:bg-purple-900/60 disabled:opacity-50 disabled:cursor-not-allowed"
              />
              <p id={`${fileInputId}-help`} className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                Only a .zip archive is accepted.
              </p>
            </div>

            <div className="flex items-center justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
              <button
                type="button"
                onClick={handleClose}
                disabled={isSubmitting}
                className="px-4 py-2 text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => { void handleSubmit(); }}
                disabled={isSubmitting || !selectedFile}
                className="px-6 py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-purple-400 text-white rounded-lg flex items-center transition-colors disabled:cursor-not-allowed disabled:opacity-70"
              >
                {isSubmitting ? (
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" aria-hidden="true" />
                ) : (
                  <Upload className="w-4 h-4 mr-2" aria-hidden="true" />
                )}
                {isSubmitting ? 'Importing…' : 'Import'}
              </button>
              {/* A button label swap alone isn't reliably announced (WCAG 4.1.3) — mirror the
                  sr-only status pattern already used for async actions in SkillsPage. */}
              <span role="status" aria-live="polite" className="sr-only">
                {isSubmitting ? 'Importing plugin…' : ''}
              </span>
            </div>
          </>
        )}

        {result && (
          <div className="space-y-4">
            {result.skills.some((s) => s.has_bootstrap) && (
              <div
                role="alert"
                className="flex items-start gap-2 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg p-3"
              >
                <ShieldAlert className="w-5 h-5 text-red-500 dark:text-red-400 shrink-0" aria-hidden="true" />
                <p className="text-sm text-red-700 dark:text-red-300">
                  One or more imported skills carry a bootstrap script that will execute code once
                  enabled. Review each entry marked below carefully before enabling it.
                </p>
              </div>
            )}

            <ul className="divide-y divide-gray-200 dark:divide-gray-700 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
              {result.skills.map((skill) => (
                <li key={skill.name} className="p-3 bg-white dark:bg-gray-800">
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <span className="text-sm font-mono font-medium text-gray-900 dark:text-gray-100">
                      {skill.name}
                    </span>
                    <div className="flex items-center gap-1.5 flex-wrap">
                      {skill.has_bootstrap && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-red-50 text-red-700 border border-red-200 dark:bg-red-900/30 dark:text-red-300 dark:border-red-800">
                          <ShieldAlert className="w-3.5 h-3.5" aria-hidden="true" />
                          Runs bootstrap script
                        </span>
                      )}
                      {statusBadge(skill.status)}
                    </div>
                  </div>
                  {skill.reason && (skill.status === 'skipped' || skill.status === 'failed') && (
                    <p className="mt-1 text-xs text-gray-600 dark:text-gray-400">{skill.reason}</p>
                  )}
                  {skill.has_bootstrap && skill.bootstrap_script_path && (
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400 font-mono">
                      {skill.bootstrap_script_path}
                      {skill.runtime ? ` (${skill.runtime})` : ''}
                    </p>
                  )}
                </li>
              ))}
            </ul>

            <div className="flex items-center justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
              <button
                type="button"
                onClick={handleRetry}
                className="px-4 py-2 text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-lg transition-colors"
              >
                Import another
              </button>
              <button
                type="button"
                onClick={handleClose}
                className="px-6 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors"
              >
                Done
              </button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}

export default ClaudePluginImportModal;
