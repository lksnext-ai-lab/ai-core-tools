import { describe, expect, it } from 'vitest';
import { serviceStatus } from '../systemOneStatus';

const ok = { status: 'success', message: 'Connection successful', verifiable: true } as const;

describe('serviceStatus', () => {
  it('needs a model before anything else', () => {
    expect(serviceStatus('', ok)).toBe('model_required');
    expect(serviceStatus('   ', null)).toBe('model_required');
  });
  it('is checking until the server has answered', () => {
    expect(serviceStatus('m', null)).toBe('checking');
    expect(serviceStatus('m', undefined)).toBe('checking');
  });
  it('is connected only when the server could be verified', () => {
    expect(serviceStatus('m', ok)).toBe('connected');
  });
  it('says so when the server answers but cannot prove the token or the model', () => {
    expect(serviceStatus('m', { ...ok, verifiable: false })).toBe('unverifiable');
  });
  it('tells a rejected token apart from an unreachable server', () => {
    expect(serviceStatus('m', { status: 'error', message: 'The server rejected the token (HTTP 401)', verifiable: true })).toBe('token_rejected');
    expect(serviceStatus('m', { status: 'error', message: 'Cannot connect to the System One server', verifiable: true })).toBe('unreachable');
  });
});
