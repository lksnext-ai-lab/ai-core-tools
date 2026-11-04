import { useEffect, useRef, useState } from 'react';
import { Clock, ShieldAlert } from 'lucide-react';
import { useCountdown } from '../../hooks/useCountdown';
import { buildHitlDecisions, type HitlActionChoice } from './hitlApprovalDecisions';
import type { HitlDecision, HitlPendingApproval } from '../../types/streaming';

export interface HitlApprovalCardProps {
  readonly approval: HitlPendingApproval;
  readonly disabled?: boolean;
  readonly onDecide: (decisions: HitlDecision[]) => void;
  /** Reject the whole request; offered only when some tool does not allow Reject. */
  readonly onCancel: () => void;
  /** Called once when the deadline passes while the card is shown. */
  readonly onExpire?: () => void;
}

function formatRemaining(ms: number): string {
  const totalSeconds = Math.ceil(ms / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) return `${hours} h ${String(minutes).padStart(2, '0')} min`;
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

/**
 * Human-in-the-loop review of the tool calls an agent wants to run.
 *
 * Each tool gets its own decision. All decisions are submitted together because the paused
 * middleware resumes the complete batch; a single tool is decided with one click. Unanswered
 * requests expire and are rejected by the server.
 */
function HitlApprovalCard({ approval, disabled = false, onDecide, onCancel, onExpire }: HitlApprovalCardProps) {
  const { actions } = approval;
  const remainingMs = useCountdown(approval.expires_at);
  const expired = approval.status === 'expired' || remainingMs === 0;

  const [drafts, setDrafts] = useState<string[]>(() => actions.map((a) => JSON.stringify(a.args, null, 2)));
  const [errors, setErrors] = useState<(string | null)[]>(() => actions.map(() => null));
  const [choices, setChoices] = useState<(HitlActionChoice | null)[]>(() => actions.map(() => null));
  const expireNotified = useRef(false);

  useEffect(() => {
    setDrafts(actions.map((a) => JSON.stringify(a.args, null, 2)));
    setErrors(actions.map(() => null));
    setChoices(actions.map(() => null));
    expireNotified.current = false;
  }, [approval, actions]);

  useEffect(() => {
    if (expired && !expireNotified.current) {
      expireNotified.current = true;
      onExpire?.();
    }
  }, [expired, onExpire]);

  const locked = disabled || expired;
  const single = actions.length === 1;
  const canApprove = (a: HitlPendingApproval['actions'][number]) =>
    a.allowed_decisions.includes('approve') || a.allowed_decisions.includes('edit');
  const canReject = (a: HitlPendingApproval['actions'][number]) => a.allowed_decisions.includes('reject');

  const submit = (nextChoices: (HitlActionChoice | null)[]) => {
    const result = buildHitlDecisions(actions, drafts, nextChoices);
    setErrors(result.errors);
    if (result.decisions) onDecide(result.decisions);
  };

  const choose = (idx: number, choice: HitlActionChoice) => {
    const next = choices.map((c, i) => (i === idx ? choice : c));
    setChoices(next);
    setErrors((prev) => prev.map((error, i) => (i === idx ? null : error)));
    if (single) submit(next);
  };

  const chooseAll = (choice: HitlActionChoice) => {
    setChoices(actions.map(() => choice));
    setErrors(actions.map(() => null));
  };

  const toolsLabel = actions.length === 1 ? 'this tool' : 'these tools';
  const statusText = expired
    ? 'This request expired and the tool was not executed. The agent’s answer will appear shortly.'
    : actions.length > 1
      ? `The agent wants to run ${toolsLabel}. Choose for each tool, then submit your decisions.`
      : `The agent wants to run ${toolsLabel}. Nothing runs until you decide.`;

  return (
    <section className="flex justify-start mb-4" aria-label="Approval required">
      <div className="w-full max-w-[85%] min-w-0">
        <div className="bg-amber-50 dark:bg-amber-900/30 border border-amber-200 dark:border-amber-700 rounded-xl p-4 space-y-3">
          <div className="flex items-center gap-2 text-amber-800 dark:text-amber-200 text-sm font-medium">
            <ShieldAlert className="w-4 h-4 shrink-0" aria-hidden="true" />
            <span className="flex-1">Approval required</span>
            <span
              className={`flex items-center gap-1 text-xs font-normal tabular-nums ${
                expired ? 'text-red-700 dark:text-red-300' : 'text-amber-700 dark:text-amber-300'
              }`}
            >
              <Clock className="w-3.5 h-3.5" aria-hidden="true" />
              {expired ? 'Expired' : `Expires in ${formatRemaining(remainingMs)}`}
            </span>
          </div>
          <p className="text-xs text-amber-900/80 dark:text-amber-100/80" aria-live="polite">
            {statusText}
          </p>

          {actions.map((action, idx) => {
            const editable = action.allowed_decisions.includes('edit');
            const fieldId = `hitl-args-${approval.approval_id}-${idx}`;
            return (
              <div key={action.action_id} className="bg-white dark:bg-gray-800 rounded-lg p-3 border border-amber-100 dark:border-amber-800">
                <label htmlFor={fieldId} className="block text-sm font-mono text-gray-800 dark:text-gray-200 mb-1 break-all">
                  {action.name}
                </label>
                {editable ? (
                  <textarea
                    id={fieldId}
                    className="w-full text-xs text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-700 rounded p-2 font-mono border border-amber-300 dark:border-amber-600 focus:outline-none focus:ring-2 focus:ring-amber-500"
                    rows={Math.min(8, Math.max(3, drafts[idx]?.split('\n').length ?? 3))}
                    value={drafts[idx] ?? ''}
                    onChange={(e) => {
                      const value = e.target.value;
                      setDrafts((prev) => prev.map((d, i) => (i === idx ? value : d)));
                      setChoices((prev) => prev.map((choice, i) => (i === idx ? null : choice)));
                      setErrors((prev) => prev.map((error, i) => (i === idx ? null : error)));
                    }}
                    spellCheck={false}
                    disabled={locked}
                    aria-invalid={Boolean(errors[idx])}
                    aria-describedby={errors[idx] ? `${fieldId}-error` : undefined}
                  />
                ) : (
                  <pre id={fieldId} className="text-xs text-gray-800 dark:text-gray-200 bg-gray-50 dark:bg-gray-700 rounded p-2 font-mono overflow-x-auto">
                    {JSON.stringify(action.args, null, 2)}
                  </pre>
                )}
                {errors[idx] && (
                  <p id={`${fieldId}-error`} className="mt-1 text-xs text-red-600 dark:text-red-400">{errors[idx]}</p>
                )}
                <div className="flex flex-wrap items-center gap-2 mt-3">
                  {canApprove(action) && (
                    <button
                      type="button"
                      onClick={() => choose(idx, 'approve')}
                      disabled={locked}
                      aria-pressed={single ? undefined : choices[idx] === 'approve'}
                      className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                        choices[idx] === 'approve'
                          ? 'bg-green-700 text-white'
                          : 'bg-green-100 hover:bg-green-200 dark:bg-green-900/40 dark:hover:bg-green-900/70 text-green-800 dark:text-green-200'
                      }`}
                    >
                      Approve
                    </button>
                  )}
                  {canReject(action) && (
                    <button
                      type="button"
                      onClick={() => choose(idx, 'reject')}
                      disabled={locked}
                      aria-pressed={single ? undefined : choices[idx] === 'reject'}
                      className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                        choices[idx] === 'reject'
                          ? 'bg-red-700 text-white'
                          : 'bg-red-100 hover:bg-red-200 dark:bg-red-900/40 dark:hover:bg-red-900/70 text-red-800 dark:text-red-200'
                      }`}
                    >
                      Reject
                    </button>
                  )}
                </div>
              </div>
            );
          })}

          <div className="flex flex-wrap items-center gap-2 pt-1">
            {!single && (
              <>
                <button
                  type="button"
                  onClick={() => submit(choices)}
                  disabled={locked || choices.some((choice) => choice === null)}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
                >
                  Submit decisions
                </button>
                {actions.every(canApprove) && (
                  <button
                    type="button"
                    onClick={() => chooseAll('approve')}
                    disabled={locked}
                    className="px-3 py-2 text-sm font-medium text-green-800 dark:text-green-200 hover:underline disabled:opacity-50 disabled:cursor-not-allowed disabled:no-underline"
                  >
                    Approve all
                  </button>
                )}
                {actions.every(canReject) && (
                  <button
                    type="button"
                    onClick={() => chooseAll('reject')}
                    disabled={locked}
                    className="px-3 py-2 text-sm font-medium text-red-800 dark:text-red-200 hover:underline disabled:opacity-50 disabled:cursor-not-allowed disabled:no-underline"
                  >
                    Reject all
                  </button>
                )}
              </>
            )}
            {!actions.every(canReject) && (
              // Some tool does not allow Reject: cancelling the whole request is still possible.
              <button
                type="button"
                onClick={onCancel}
                disabled={locked}
                className="px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 hover:underline disabled:opacity-50 disabled:cursor-not-allowed disabled:no-underline"
              >
                Cancel request
              </button>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

export default HitlApprovalCard;
