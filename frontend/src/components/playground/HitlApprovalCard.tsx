import { useEffect, useState } from 'react';
import { ShieldAlert } from 'lucide-react';
import type { HitlDecision, HitlPendingApproval } from '../../types/streaming';

interface HitlApprovalCardProps {
  readonly approval: HitlPendingApproval;
  readonly disabled?: boolean;
  readonly onDecide: (decisions: HitlDecision[]) => void;
}

/**
 * Human-in-the-loop review of the tool calls an agent wants to run.
 *
 * Only offers what the middleware allows for each tool (review_configs): arguments are
 * editable only when `edit` is allowed, and Approve/Reject are disabled when any pending
 * tool does not allow them. Decisions are sent in the same order as the actions.
 */
function HitlApprovalCard({ approval, disabled = false, onDecide }: HitlApprovalCardProps) {
  const actions = approval.action_requests;
  const allowedFor = (name: string) =>
    approval.review_configs.find((rc) => rc.action_name === name)?.allowed_decisions ?? [];

  const [drafts, setDrafts] = useState<string[]>(() => actions.map((a) => JSON.stringify(a.args, null, 2)));
  const [errors, setErrors] = useState<(string | null)[]>(() => actions.map(() => null));

  useEffect(() => {
    setDrafts(actions.map((a) => JSON.stringify(a.args, null, 2)));
    setErrors(actions.map(() => null));
  }, [approval]);

  const canApprove = actions.every((a) => {
    const allowed = allowedFor(a.name);
    return allowed.includes('approve') || allowed.includes('edit');
  });
  const canReject = actions.every((a) => allowedFor(a.name).includes('reject'));

  const handleApprove = () => {
    const nextErrors = actions.map(() => null as string | null);
    const decisions: HitlDecision[] = [];
    actions.forEach((action, idx) => {
      const allowed = allowedFor(action.name);
      if (!allowed.includes('edit')) {
        decisions.push({ type: 'approve' });
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
        decisions.push({ type: 'edit', edited_action: { name: action.name, args: args as Record<string, unknown> } });
      } else if (allowed.includes('approve')) {
        decisions.push({ type: 'approve' });
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
    onDecide(actions.map((a) => ({ type: 'reject', message: `The user rejected the call to ${a.name}.` })));
  };

  return (
    <div className="flex justify-start mb-4" role="region" aria-label="Approval required">
      <div className="w-full max-w-[85%] min-w-0">
        <div className="bg-amber-50 dark:bg-amber-900/30 border border-amber-200 dark:border-amber-700 rounded-xl p-4 space-y-3">
          <div className="flex items-center gap-2 text-amber-800 dark:text-amber-200 text-sm font-medium">
            <ShieldAlert className="w-4 h-4 shrink-0" aria-hidden="true" />
            Approval required
          </div>
          <p className="text-xs text-amber-900/80 dark:text-amber-100/80">
            The agent wants to run {actions.length === 1 ? 'this tool' : 'these tools'}. Nothing runs until you decide.
          </p>

          {actions.map((action, idx) => {
            const editable = allowedFor(action.name).includes('edit');
            const fieldId = `hitl-args-${idx}`;
            return (
              <div key={`${action.name}-${idx}`} className="bg-white dark:bg-gray-800 rounded-lg p-3 border border-amber-100 dark:border-amber-800">
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
                    disabled={disabled}
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

          <div className="flex flex-wrap gap-2 pt-1">
            <button
              type="button"
              onClick={handleApprove}
              disabled={disabled || !canApprove}
              className="px-4 py-2 bg-green-600 hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
            >
              Approve
            </button>
            <button
              type="button"
              onClick={handleReject}
              disabled={disabled || !canReject}
              className="px-4 py-2 bg-red-600 hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
            >
              Reject
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default HitlApprovalCard;
