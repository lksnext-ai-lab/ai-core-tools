import type { HitlAction, HitlDecision } from '../../types/streaming';

export type HitlActionChoice = 'approve' | 'reject';

export interface HitlDecisionBuildResult {
  readonly decisions: HitlDecision[] | null;
  readonly errors: (string | null)[];
}

export function buildHitlDecisions(
  actions: readonly HitlAction[],
  drafts: readonly string[],
  choices: readonly (HitlActionChoice | null)[],
): HitlDecisionBuildResult {
  const errors = actions.map(() => null as string | null);
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
        errors[index] = 'This tool does not allow rejection.';
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
      errors[index] = 'This tool does not allow approval.';
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
      errors[index] = 'Arguments must be valid JSON.';
      return;
    }
    if (typeof args !== 'object' || args === null || Array.isArray(args)) {
      errors[index] = 'Arguments must be a JSON object.';
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
      errors[index] = 'This tool only accepts edited arguments.';
    }
  });

  if (!complete || errors.some((error) => error !== null)) {
    return { decisions: null, errors };
  }
  return { decisions, errors };
}
