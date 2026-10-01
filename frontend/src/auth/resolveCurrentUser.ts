import type { CurrentUserResult } from '../services/auth';

interface ResolveCurrentUserDeps {
  readonly fetchCurrentUser: () => Promise<CurrentUserResult>;
  /** Renews the credentials once (OIDC silent renew or LOCAL refresh-token rotation). */
  readonly renewSession: () => Promise<boolean>;
}

/** Asks the backend who the user is, renewing the session once if it rejects the credentials. */
export async function resolveCurrentUser({
  fetchCurrentUser,
  renewSession,
}: ResolveCurrentUserDeps): Promise<CurrentUserResult> {
  const first = await fetchCurrentUser();
  if (first.status !== 'unauthorized') return first;

  const renewed = await renewSession().catch(() => false);
  return renewed ? fetchCurrentUser() : first;
}
