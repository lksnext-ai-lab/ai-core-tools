import { useEffect, useRef, useState } from 'react';
import { Clock, ShieldAlert } from 'lucide-react';
import { useCountdown } from '../../hooks/useCountdown';
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
 * Only offers what the middleware allows for each tool: arguments are editable only when
 * `edit` is allowed, and Approve/Reject are disabled when any pending tool does not allow
 * them; Cancel covers that case. Unanswered requests expire and are rejected by the server.
 */
function HitlApprovalCard({ approval, disabled = false, onDecide, onCancel, onExpire }: HitlApprovalCardProps) {
  const { actions } = approval;
  const remainingMs = useCountdown(approval.expires_at);
  const expired = approval.status === 'expired' || remainingMs === 0;

  const [drafts, setDrafts] = useState<string[]>(() => actions.map((a) => JSON.stringify(a.args, null, 2)));
  const [errors, setErrors] = useState<(string | null)[]>(() => actions.map(() => null));
  const expireNotified = useRef(false);

  useEffect(() => {
    setDrafts(actions.map((a) => JSON.stringify(a.args, null, 2)));
    setErrors(actions.map(() => null));
    expireNotified.current = false;
  }, [approval, actions]);

  useEffect(() => {
    if (expired && !expireNotified.current) {
      expireNotified.current = true;
      onExpire?.();
    }
  }, [expired, onExpire]);

  const locked = disabled || expired;
  const canApprove = actions.every((a) => a.allowed_decisions.includes('approve') || a.allowed_decisions.includes('edit'));
  const canReject = actions.every((a) => a.allowed_decisions.includes('reject'));

  const handleApprove = () => {
    const nextErrors = actions.map(() => null as string | null);
    const decisions: HitlDecision[] = [];
    actions.forEach((action, idx) => {
      if (!action.allowed_decisions.includes('edit')) {
        decisions.push({ action_id: action.action_id, type: 'approve' });
        return;
      }
      let args: unknown;
      try {
        args = JSON.parse(drafts[idx]);
      } catch {
        nextErrors[idx] = 'Arguments must be valid JSON.';
        return;
      }
      if (typeof args !== 'object' || args === null || Array.isArray(args)) {
        nextErrors[idx] = 'Arguments must be a JSON object.';
        return;
      }
      const changed = JSON.stringify(args) !== JSON.stringify(action.args);
      if (changed) {
        decisions.push({ action_id: action.action_id, type: 'edit', args: args as Record<string, unknown> });
      } else if (action.allowed_decisions.includes('approve')) {
        decisions.push({ action_id: action.action_id, type: 'approve' });
      } else {
        nextErrors[idx] = 'This tool only accepts edited arguments.';
      }
    });
    setErrors(nextErrors);
    if (nextErrors.every((e) => e === null)) {
      onDecide(decisions);
    }
  };

  const handleReject = () => {
    onDecide(actions.map((a) => ({
      action_id: a.action_id,
      type: 'reject',
      message: `The user rejected the call to ${a.name}. Do not call it again unless the user asks for it.`,
    })));
  };

  return (
    <div className="flex justify-start mb-4" role="region" aria-label="Approval required">
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
            {expired
              ? 'This request expired and the tool was not executed. The agent’s answer will appear shortly.'
              : `The agent wants to run ${actions.length === 1 ? 'this tool' : 'these tools'}. Nothing runs until you decide.`}
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
                    }}
                    spellCheck={false}
                    disabled={locked}
                    aria-invalid={errors[idx] !== null}
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
              </div>
            );
          })}

          <div className="flex flex-wrap items-center gap-2 pt-1">
            <button
              type="button"
              onClick={handleApprove}
              disabled={locked || !canApprove}
              className="px-4 py-2 bg-green-600 hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
            >
              Approve
            </button>
            <button
              type="button"
              onClick={handleReject}
              disabled={locked || !canReject}
              className="px-4 py-2 bg-red-600 hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
            >
              Reject
            </button>
            {!canReject && (
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
    </div>
  );
}

export default HitlApprovalCard;
