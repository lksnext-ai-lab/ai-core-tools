import { useEffect, useRef, useState } from 'react';
import { Clock } from 'lucide-react';
import { useCountdown } from '../../hooks/useCountdown';
import Alert from '../ui/Alert';
import { ButtonApp } from '../ui/ButtonApp';
import CardApp from '../ui/CardApp';
import { FormTextArea } from '../ui/FormField';
import { buildHitlDecisions, type HitlActionChoice } from './hitlApprovalDecisions';
import type { HitlDecision, HitlPendingApproval } from '../../types/streaming';
import { useTranslation } from 'react-i18next';

export interface HitlApprovalCardProps {
  readonly approval: HitlPendingApproval;
  readonly disabled?: boolean;
  readonly onDecide: (decisions: HitlDecision[]) => void;
  /** Reject the whole request; offered only when some tool does not allow Reject. */
  readonly onCancel: () => void;
  /** Called once when the deadline passes while the card is shown. */
  readonly onExpire?: () => void;
}

/**
 * Human-in-the-loop review of the tool calls an agent wants to run.
 *
 * Each tool gets its own decision. All decisions are submitted together because the paused
 * middleware resumes the complete batch; a single tool is decided with one click. Unanswered
 * requests expire and are rejected by the server.
 */
function HitlApprovalCard({ approval, disabled = false, onDecide, onCancel, onExpire }: HitlApprovalCardProps) {
  const { t } = useTranslation('common');
  const { actions } = approval;
  const remainingMs = useCountdown(approval.expires_at);
  const expired = approval.status === 'expired' || remainingMs === 0;
  const formatRemaining = (ms: number): string => {
    const totalSeconds = Math.ceil(ms / 1000);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    if (hours > 0) {
      return t('hitlApproval.time.hoursMinutes', {
        hours,
        minutes: String(minutes).padStart(2, '0'),
      });
    }
    return `${minutes}:${String(seconds).padStart(2, '0')}`;
  };

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

  const statusText = expired
    ? t('hitlApproval.statusExpired')
    : actions.length > 1
      ? t('hitlApproval.statusMultiple')
      : t('hitlApproval.statusSingle');

  return (
    <section className="flex justify-start mb-4" aria-label={t('hitlApproval.required')}>
      <div className="w-full max-w-[85%] min-w-0">
        <Alert
          type="warning"
          polite
          title={t('hitlApproval.required')}
          message={(
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p aria-live="polite">{statusText}</p>
                <span
                  className={`flex items-center gap-1 text-xs tabular-nums ${
                    expired ? 'text-error dark:text-error-dark' : ''
                  }`}
                >
                  <Clock className="w-3.5 h-3.5" aria-hidden="true" />
                  {expired ? t('hitlApproval.expired') : t('hitlApproval.expiresIn', { time: formatRemaining(remainingMs) })}
                </span>
              </div>

              {actions.map((action, idx) => {
                const editable = action.allowed_decisions.includes('edit');
                const fieldId = `hitl-args-${approval.approval_id}-${idx}`;
                const choice = choices[idx];
                return (
                  <CardApp key={action.action_id} className="p-3">
                    {editable ? (
                      <FormTextArea
                        id={fieldId}
                        label={action.name}
                        labelClassName="mb-1 block break-all font-mono text-sm text-fg dark:text-fg-dark"
                        textareaClassName="font-mono text-xs"
                        rows={Math.min(8, Math.max(3, drafts[idx]?.split('\n').length ?? 3))}
                        value={drafts[idx] ?? ''}
                        onChange={(e) => {
                          const value = e.target.value;
                          setDrafts((prev) => prev.map((d, i) => (i === idx ? value : d)));
                          setChoices((prev) => prev.map((c, i) => (i === idx ? null : c)));
                          setErrors((prev) => prev.map((error, i) => (i === idx ? null : error)));
                        }}
                        disabled={locked}
                        error={errors[idx] ? t(`hitlApproval.errors.${errors[idx]}`) : undefined}
                      />
                    ) : (
                      <>
                        <p id={`${fieldId}-name`} className="mb-1 break-all font-mono text-sm text-fg dark:text-fg-dark">
                          {action.name}
                        </p>
                        <pre
                          aria-labelledby={`${fieldId}-name`}
                          className="overflow-x-auto rounded-md bg-tableCab p-2 font-mono text-xs text-fg dark:bg-btCard-dark dark:text-fg-dark"
                        >
                          {JSON.stringify(action.args, null, 2)}
                        </pre>
                        {errors[idx] && (
                          <p className="mt-1 text-xs text-error dark:text-error-dark">{t(`hitlApproval.errors.${errors[idx]}`)}</p>
                        )}
                      </>
                    )}
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      {canApprove(action) && (
                        <ButtonApp
                          label={t('hitlApproval.approve')}
                          onClick={() => choose(idx, 'approve')}
                          disabled={locked}
                          ariaPressed={single ? undefined : choice === 'approve'}
                          variant={choice === 'approve' ? 'primary' : 'secondary'}
                          size="small"
                        />
                      )}
                      {canReject(action) && (
                        <ButtonApp
                          label={t('hitlApproval.reject')}
                          onClick={() => choose(idx, 'reject')}
                          disabled={locked}
                          ariaPressed={single ? undefined : choice === 'reject'}
                          variant={choice === 'reject' ? 'dangerSolid' : 'danger'}
                          size="small"
                        />
                      )}
                    </div>
                  </CardApp>
                );
              })}

              <div className="flex flex-wrap items-center gap-2">
                {!single && (
                  <>
                    <ButtonApp
                      label={t('hitlApproval.submitDecisions')}
                      onClick={() => submit(choices)}
                      disabled={locked || choices.some((c) => c === null)}
                      variant="primary"
                      size="small"
                    />
                    {actions.every(canApprove) && (
                      <ButtonApp
                        label={t('hitlApproval.approveAll')}
                        onClick={() => chooseAll('approve')}
                        disabled={locked}
                        variant="secondary"
                        size="small"
                      />
                    )}
                    {actions.every(canReject) && (
                      <ButtonApp
                        label={t('hitlApproval.rejectAll')}
                        onClick={() => chooseAll('reject')}
                        disabled={locked}
                        variant="danger"
                        size="small"
                      />
                    )}
                  </>
                )}
                {!actions.every(canReject) && (
                  // Some tool does not allow Reject: cancelling the whole request is still possible.
                  <ButtonApp
                    label={t('hitlApproval.cancelRequest')}
                    onClick={onCancel}
                    disabled={locked}
                    variant="muted"
                    size="small"
                  />
                )}
              </div>
            </div>
          )}
        />
      </div>
    </section>
  );
}

export default HitlApprovalCard;
