import type { HitlAction, HitlDecision } from '../../types/streaming';

export type HitlActionChoice = 'approve' | 'reject';
export type HitlDecisionError =
  | 'rejectNotAllowed'
  | 'approveNotAllowed'
  | 'invalidJson'
  | 'jsonObjectRequired'
  | 'editedArgumentsRequired';

export interface HitlDecisionBuildResult {
  readonly decisions: HitlDecision[] | null;
  readonly errors: (HitlDecisionError | null)[];
}

export function buildHitlDecisions(
  actions: readonly HitlAction[],
  drafts: readonly string[],
  choices: readonly (HitlActionChoice | null)[],
): HitlDecisionBuildResult {
  const errors = actions.map(() => null as HitlDecisionError | null);
  const decisions: HitlDecision[] = [];
  let complete = true;

  actions.forEach((action, index) => {
    const choice = choices[index];
    if (!choice) {
      complete = false;
      return;
    }

    if (choice === 'reject') {
      if (!action.allowed_decisions.includes('reject')) {
        errors[index] = 'rejectNotAllowed';
        return;
      }
      decisions.push({
        action_id: action.action_id,
        type: 'reject',
        message: `The user rejected the call to ${action.name}. Do not call it again unless the user asks for it.`,
      });
      return;
    }

    if (!action.allowed_decisions.includes('approve') && !action.allowed_decisions.includes('edit')) {
      errors[index] = 'approveNotAllowed';
      return;
    }
    if (!action.allowed_decisions.includes('edit')) {
      decisions.push({ action_id: action.action_id, type: 'approve' });
      return;
    }

    let args: unknown;
    try {
      args = JSON.parse(drafts[index] ?? '');
    } catch {
      errors[index] = 'invalidJson';
      return;
    }
    if (typeof args !== 'object' || args === null || Array.isArray(args)) {
      errors[index] = 'jsonObjectRequired';
      return;
    }

    if (JSON.stringify(args) !== JSON.stringify(action.args)) {
      decisions.push({
        action_id: action.action_id,
        type: 'edit',
        args: args as Record<string, unknown>,
      });
    } else if (action.allowed_decisions.includes('approve')) {
      decisions.push({ action_id: action.action_id, type: 'approve' });
    } else {
      errors[index] = 'editedArgumentsRequired';
    }
  });

  if (!complete || errors.some((error) => error !== null)) {
    return { decisions: null, errors };
  }
  return { decisions, errors };
}
