import { describe, expect, it, vi } from 'vitest';
import { resolveCurrentUser } from '../resolveCurrentUser';
import type { CurrentUserResult } from '../../services/auth';

const OK: CurrentUserResult = { status: 'ok', user: { user_id: 7, email: 'ana@example.com', platform_role: 'editor' } };
const UNAUTHORIZED: CurrentUserResult = { status: 'unauthorized' };
const UNAVAILABLE: CurrentUserResult = { status: 'unavailable' };

function sequence(...results: CurrentUserResult[]) {
  const fetchCurrentUser = vi.fn<() => Promise<CurrentUserResult>>();
  results.forEach(result => fetchCurrentUser.mockResolvedValueOnce(result));
  return fetchCurrentUser;
}

describe('resolveCurrentUser', () => {
  it('returns the user without renewing when the session is accepted', async () => {
    const fetchCurrentUser = sequence(OK);
    const renewSession = vi.fn().mockResolvedValue(true);

    await expect(resolveCurrentUser({ fetchCurrentUser, renewSession })).resolves.toEqual(OK);
    expect(renewSession).not.toHaveBeenCalled();
  });

  it('renews once and retries when the backend rejects expired credentials', async () => {
    const fetchCurrentUser = sequence(UNAUTHORIZED, OK);
    const renewSession = vi.fn().mockResolvedValue(true);

    await expect(resolveCurrentUser({ fetchCurrentUser, renewSession })).resolves.toEqual(OK);
    expect(renewSession).toHaveBeenCalledTimes(1);
    expect(fetchCurrentUser).toHaveBeenCalledTimes(2);
  });

  it('reports unauthorized when the renewal fails', async () => {
    const fetchCurrentUser = sequence(UNAUTHORIZED);
    const renewSession = vi.fn().mockResolvedValue(false);

    await expect(resolveCurrentUser({ fetchCurrentUser, renewSession })).resolves.toEqual(UNAUTHORIZED);
    expect(fetchCurrentUser).toHaveBeenCalledTimes(1);
  });

  it('treats a throwing renewal as a failed renewal', async () => {
    const fetchCurrentUser = sequence(UNAUTHORIZED);
    const renewSession = vi.fn().mockRejectedValue(new Error('network'));

    await expect(resolveCurrentUser({ fetchCurrentUser, renewSession })).resolves.toEqual(UNAUTHORIZED);
  });

  it('does not renew or downgrade the user when the backend is unreachable', async () => {
    const fetchCurrentUser = sequence(UNAVAILABLE);
    const renewSession = vi.fn().mockResolvedValue(true);

    await expect(resolveCurrentUser({ fetchCurrentUser, renewSession })).resolves.toEqual(UNAVAILABLE);
    expect(renewSession).not.toHaveBeenCalled();
  });
});
