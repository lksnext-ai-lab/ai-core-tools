import { screen, waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import i18n from '../../src/i18n';
import AppSettingsPage from '../../src/pages/settings/AppSettingsPage';
import { apiMock } from './apiMock';
import { renderWithProviders, tr } from './testUtils';

const EMBEDDINGS = [
  { service_id: 1, name: 'Ada', provider: 'OpenAI', model_name: 'ada', created_at: '', lifecycle_status: 'active' },
  { service_id: 2, name: 'Bge', provider: 'Ollama', model_name: 'bge', created_at: '', lifecycle_status: 'active' },
  { service_id: 3, name: 'Old', provider: 'OpenAI', model_name: 'old', created_at: '', lifecycle_status: 'retired' },
];

function setup(embeddingId: number | null, role = 'owner', embeddingsFail = false) {
  apiMock.getApp.mockResolvedValue({
    app_id: 7,
    name: 'Demo',
    user_role: role,
    agent_rate_limit: 0,
    max_file_size_mb: 0,
    default_sandbox_service_id: null,
    default_embedding_service_id: embeddingId,
    langsmith_api_key: '****abcd',
  } as never);
  apiMock.getAppSlugInfo.mockResolvedValue({ slug: 'demo' } as never);
  apiMock.getSandboxServices.mockResolvedValue([] as never);
  if (embeddingsFail) apiMock.getEmbeddingServices.mockRejectedValue(new Error('down'));
  else apiMock.getEmbeddingServices.mockResolvedValue(EMBEDDINGS as never);
  apiMock.updateApp.mockResolvedValue({} as never);
  return renderWithProviders(
    <Routes>
      <Route path="/apps/:appId/settings" element={<AppSettingsPage />} />
    </Routes>,
    { path: '/apps/7/settings' },
  );
}

const selector = () => screen.getByRole('combobox', { name: tr('appSettingsPage.embeddingService') });

describe('App settings: default embedding service', () => {
  it('lists the App embedding services, shows the saved one and explains what it is for', async () => {
    setup(2);
    await waitFor(() => expect(selector()).toHaveValue('2'));
    expect(apiMock.getEmbeddingServices).toHaveBeenCalledWith(7);
    expect(selector()).toHaveDisplayValue('Bge (Ollama)');
    expect(screen.getByRole('option', { name: tr('appSettingsPage.noDefaultEmbeddingService') })).toBeInTheDocument();
    expect(screen.getByText(/index the files attached in the App Chat/)).toBeInTheDocument();
  });

  it('does not offer a retired service for new selection', async () => {
    setup(null);
    await waitFor(() => expect(screen.getByRole('option', { name: /Ada/ })).toBeInTheDocument());
    expect(screen.queryByRole('option', { name: /Old/ })).not.toBeInTheDocument();
  });

  it('keeps the saved service visible when it is retired, flagged as retired', async () => {
    setup(3);
    await waitFor(() => expect(selector()).toHaveValue('3'));
    expect(screen.getByRole('option', { name: /Old.*retired/i })).toBeInTheDocument();
  });

  it('saves the chosen id with the update', async () => {
    const { user } = setup(null);
    await waitFor(() => expect(screen.getByRole('option', { name: /Ada/ })).toBeInTheDocument());
    await user.selectOptions(selector(), '1');
    await user.click(screen.getByRole('button', { name: tr('appSettingsPage.saveChanges') }));
    await waitFor(() => expect(apiMock.updateApp).toHaveBeenCalledTimes(1));
    expect(apiMock.updateApp.mock.calls[0][0]).toBe(7);
    expect(apiMock.updateApp.mock.calls[0][1]).toMatchObject({ default_embedding_service_id: 1 });
  });

  it('clears to null', async () => {
    const { user } = setup(2);
    await waitFor(() => expect(selector()).toHaveValue('2'));
    await user.selectOptions(selector(), '');
    await user.click(screen.getByRole('button', { name: tr('appSettingsPage.saveChanges') }));
    await waitFor(() => expect(apiMock.updateApp).toHaveBeenCalledTimes(1));
    expect(apiMock.updateApp.mock.calls[0][1]).toMatchObject({ default_embedding_service_id: null });
  });

  it('shows an inline error when the embedding services cannot be loaded', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    setup(null, 'owner', true);
    expect(await screen.findByText(tr('appSettingsPage.embeddingServicesLoadFailed'))).toBeInTheDocument();
  });

  it('names the settings page without an arrow glyph a screen reader would read out', async () => {
    setup(null);
    await waitFor(() => expect(selector()).toBeInTheDocument());
    expect(tr('appSettingsPage.embeddingServicesSettings')).not.toMatch(/[→>]/);
  });

  it('is read-only for a member who cannot edit the App settings', async () => {
    setup(2, 'editor');
    await waitFor(() => expect(selector()).toHaveValue('2'));
    await waitFor(() => expect(selector()).toBeDisabled());
  });
});

describe('App settings: LangSmith key is owner-only', () => {
  const keyField = () => screen.getByLabelText(tr('appSettingsPage.langsmithApiKey'));

  it('an administrator sees the key read-only with the explanation, and no test-connection button', async () => {
    setup(null, 'administrator');
    await waitFor(() => expect(screen.getByRole('option', { name: /Ada/ })).toBeInTheDocument());
    expect(keyField()).toBeDisabled();
    expect(screen.getByText(tr('appSettingsPage.langsmithOwnerOnly'))).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: tr('appSettingsPage.testConnection') })).not.toBeInTheDocument();
    // The rest stays editable.
    expect(selector()).toBeEnabled();
  });

  it('an administrator can change the embedding service and save, and the payload never carries the key', async () => {
    const { user } = setup(null, 'administrator');
    await waitFor(() => expect(screen.getByRole('option', { name: /Ada/ })).toBeInTheDocument());
    await user.selectOptions(selector(), '2');
    await user.click(screen.getByRole('button', { name: tr('appSettingsPage.saveChanges') }));
    await waitFor(() => expect(apiMock.updateApp).toHaveBeenCalledTimes(1));
    const payload = apiMock.updateApp.mock.calls[0][1] as Record<string, unknown>;
    expect(payload).toMatchObject({ name: 'Demo', default_embedding_service_id: 2 });
    expect(payload).not.toHaveProperty('langsmith_api_key');
  });

  it('the owner can edit the key and the explanation is not shown', async () => {
    const { user } = setup(null, 'owner');
    await waitFor(() => expect(screen.getByRole('option', { name: /Ada/ })).toBeInTheDocument());
    expect(keyField()).toBeEnabled();
    expect(screen.queryByText(tr('appSettingsPage.langsmithOwnerOnly'))).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: tr('appSettingsPage.testConnection') })).toBeInTheDocument();
    await user.click(keyField());
    await user.keyboard('lsv2_new');
    await user.click(screen.getByRole('button', { name: tr('appSettingsPage.saveChanges') }));
    await waitFor(() => expect(apiMock.updateApp).toHaveBeenCalledTimes(1));
    expect(apiMock.updateApp.mock.calls[0][1]).toMatchObject({ langsmith_api_key: 'lsv2_new' });
  });

  it('an untouched key is sent back as stored by the owner', async () => {
    const { user } = setup(null, 'owner');
    await waitFor(() => expect(screen.getByRole('option', { name: /Ada/ })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: tr('appSettingsPage.saveChanges') }));
    await waitFor(() => expect(apiMock.updateApp).toHaveBeenCalledTimes(1));
    expect(apiMock.updateApp.mock.calls[0][1]).toMatchObject({ langsmith_api_key: '****abcd' });
  });

  it('is explained in Spanish', async () => {
    await i18n.changeLanguage('es');
    setup(null, 'administrator');
    expect(await screen.findByText('Solo el propietario de la App puede cambiar la clave de API de LangSmith.')).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/appSettingsPage\./);
  });
});
