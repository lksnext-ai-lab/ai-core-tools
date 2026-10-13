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

import { agentRowStatus } from '../systemOneStatus';

describe('agentRowStatus (the Status column of the agents list)', () => {
  it('is active for any agent that can run', () => {
    expect(agentRowStatus({ type: 'agent', system_one_service: null }).kind).toBe('active');
    expect(agentRowStatus({ type: 'system_one_agent', system_one_service: { service_id: 1, name: 'S', model: 'm' } }).kind).toBe('active');
  });
  it('says a System One agent without its service cannot run', () => {
    const status = agentRowStatus({ type: 'system_one_agent', system_one_service: null });
    expect(status.kind).toBe('inoperative');
    expect(status.label).toBe('Inoperative');
    expect(status.detail).toMatch(/no System One service/i);
  });
  it('does not change how other agent types are shown', () => {
    expect(agentRowStatus({ type: 'ocr_agent', system_one_service: undefined }).kind).toBe('active');
  });
});
