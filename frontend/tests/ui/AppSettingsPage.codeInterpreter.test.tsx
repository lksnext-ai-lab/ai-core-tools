import { screen, waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import i18n from '../../src/i18n';
import AppSettingsPage from '../../src/pages/settings/AppSettingsPage';
import { apiMock } from './apiMock';
import { renderWithProviders, tr } from './testUtils';

function setup(opts: { enabled?: boolean; sandboxId?: number | null; role?: string; omit?: boolean } = {}) {
  const { enabled = false, sandboxId = null, role = 'owner', omit = false } = opts;
  apiMock.getApp.mockResolvedValue({
    app_id: 7,
    name: 'Demo',
    user_role: role,
    agent_rate_limit: 0,
    max_file_size_mb: 0,
    default_sandbox_service_id: sandboxId,
    default_embedding_service_id: null,
    langsmith_api_key: '****abcd',
    ...(omit ? {} : { chat_code_interpreter_enabled: enabled }),
  } as never);
  apiMock.getAppSlugInfo.mockResolvedValue({ slug: 'demo' } as never);
  apiMock.getSandboxServices.mockResolvedValue([
    { service_id: 4, name: 'Box', provider: 'OpenSandbox', created_at: '', lifecycle_status: 'active' },
  ] as never);
  apiMock.getEmbeddingServices.mockResolvedValue([] as never);
  apiMock.updateApp.mockResolvedValue({} as never);
  return renderWithProviders(
    <Routes>
      <Route path="/apps/:appId/settings" element={<AppSettingsPage />} />
    </Routes>,
    { path: '/apps/7/settings' },
  );
}

const box = () => screen.findByRole('checkbox', { name: tr('appSettingsPage.chatCodeInterpreter') });
const save = () => screen.getByRole('button', { name: tr('appSettingsPage.saveChanges') });

describe('App settings: code interpreter in the Chat', () => {
  it('is off by default and states the consequences plainly', async () => {
    setup();
    expect(await box()).not.toBeChecked();
    const help = screen.getByText(/Every member of this App, viewers included/);
    expect(help).toHaveTextContent(/cannot ask for approval before running code/);
    expect(help).toHaveTextContent(/cost and network access apply/);
    expect(help).toHaveTextContent(/self-hosted OpenSandbox server, sandboxes are not isolated from each other/);
    expect(await box()).toHaveAccessibleDescription(expect.stringContaining('viewers included'));
  });

  it('saves the switch through updateApp', async () => {
    const { user } = setup();
    await user.click(await box());
    await user.click(save());
    await waitFor(() => expect(apiMock.updateApp).toHaveBeenCalledTimes(1));
    expect(apiMock.updateApp.mock.calls[0][1]).toMatchObject({ chat_code_interpreter_enabled: true });
  });

  it('shows the saved value', async () => {
    setup({ enabled: true, sandboxId: 4 });
    expect(await box()).toBeChecked();
  });

  it('a missing field (older backend) reads as off', async () => {
    setup({ omit: true });
    expect(await box()).not.toBeChecked();
  });

  it('says the system default sandbox is used when the App has none, and stays usable', async () => {
    setup({ enabled: true, sandboxId: null });
    const checkbox = await box();
    expect(checkbox).toBeEnabled();
    expect(checkbox).toHaveAccessibleDescription(expect.stringContaining('or the system default when none is selected'));
    expect(document.body.textContent).not.toMatch(/no effect/);
  });

  it('is read-only below administrator', async () => {
    setup({ role: 'editor' });
    expect(await box()).toBeDisabled();
  });

  it('is editable by administrators', async () => {
    setup({ role: 'administrator' });
    expect(await box()).toBeEnabled();
  });

  it('is translated in Spanish', async () => {
    await i18n.changeLanguage('es');
    setup();
    expect(await screen.findByRole('checkbox', { name: 'Permitir ejecutar código en el Chat' })).toBeInTheDocument();
    expect(screen.getByText(/incluidos los lectores/)).toBeInTheDocument();
    expect(screen.getByText(/OpenSandbox autoalojado, los sandboxes no están aislados entre sí/)).toBeInTheDocument();
  });
});
