import { afterEach, describe, expect, it, vi } from 'vitest';

import { authService } from '../../src/services/auth';

type ActualApi = typeof import('../../src/services/api');

async function realApi() {
  // The shared setup replaces `apiService` with an in-memory mock; these tests need the real one.
  return (await vi.importActual<ActualApi>('../../src/services/api')).apiService;
}

function sseResponse(body: string): Response {
  return new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
}

describe('streaming requests and an expired session', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renews the session once and retries the stream', async () => {
    const api = await realApi();
    const refresh = vi.spyOn(authService, 'refresh').mockResolvedValue(true);
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response('{"detail":"Authentication failed"}', { status: 401 }))
      .mockResolvedValueOnce(sseResponse('data: {"type":"done"}\n\n'));

    const events: unknown[] = [];
    await api.streamAppChatMessage(1, { message: 'hi', selection: {} } as never, { onEvent: (event) => events.push(event) });

    expect(refresh).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('expires the session when the renewal fails, without a second request', async () => {
    const api = await realApi();
    vi.spyOn(authService, 'refresh').mockResolvedValue(false);
    vi.spyOn(authService, 'logout').mockResolvedValue();
    const expired = vi.spyOn(authService, 'notifySessionExpired').mockImplementation(() => {});
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response('{"detail":"Authentication failed"}', { status: 401 }));

    await expect(
      api.streamAppChatMessage(1, { message: 'hi', selection: {} } as never, { onEvent: () => {} }),
    ).rejects.toMatchObject({ status: 401 });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    await vi.waitFor(() => expect(expired).toHaveBeenCalled());
  });
});
