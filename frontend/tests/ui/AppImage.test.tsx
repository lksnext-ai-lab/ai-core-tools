import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AppAvatar } from '../../src/components/ui/AppAvatar';
import AppsPage from '../../src/pages/AppsPage';
import AppSettingsPage from '../../src/pages/settings/AppSettingsPage';
import { apiMock } from './apiMock';
import { renderWithProviders, tr } from './testUtils';

vi.mock('../../src/contexts/UserContext', () => ({
  useUser: () => ({ user: { user_id: 1, email: 'ane@example.com', is_editor: true }, loading: false }),
  useOptionalUser: () => undefined,
}));

const VERSION = '2026-11-21T10:00:00Z';

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => 'blob:app-image');
  URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('AppAvatar', () => {
  it('shows the initials, the image, and the initials again when the image fails', () => {
    const { container, rerender } = render(<AppAvatar name="Customer Support" />);
    expect(container).toHaveTextContent('CS');
    rerender(<AppAvatar name="Customer Support" src="blob:x" />);
    const img = container.querySelector('img');
    expect(img).toHaveAttribute('src', 'blob:x');
    fireEvent.error(img!);
    expect(container.querySelector('img')).toBeNull();
    expect(container).toHaveTextContent('CS');
  });
});

function renderSettings(role: string, imageVersion: string | null) {
  apiMock.getApp.mockResolvedValue({
    app_id: 7,
    name: 'Demo',
    user_role: role,
    agent_rate_limit: 0,
    max_file_size_mb: 0,
    default_sandbox_service_id: null,
    default_embedding_service_id: null,
    langsmith_api_key: '',
    image_updated_at: imageVersion,
  } as never);
  apiMock.getAppSlugInfo.mockResolvedValue({ slug: 'demo' } as never);
  apiMock.getSandboxServices.mockResolvedValue([] as never);
  apiMock.getEmbeddingServices.mockResolvedValue([] as never);
  apiMock.getAppImage.mockResolvedValue(new Blob(['img'], { type: 'image/webp' }) as never);
  return renderWithProviders(
    <Routes>
      <Route path="/apps/:appId/settings" element={<AppSettingsPage />} />
    </Routes>,
    { path: '/apps/7/settings' },
  );
}

describe('App settings: image', () => {
  it('administrators upload an image, which then shows in the tile', async () => {
    apiMock.uploadAppImage.mockResolvedValue({ image_updated_at: VERSION } as never);
    const { user, container } = renderSettings('administrator', null);
    const input = await screen.findByLabelText(tr('appSettingsPage.image.inputLabel'));
    expect(apiMock.getAppImage).not.toHaveBeenCalled();

    const file = new File(['png'], 'app.png', { type: 'image/png' });
    await user.upload(input, file);

    await waitFor(() => expect(apiMock.uploadAppImage).toHaveBeenCalledWith(7, file));
    expect(await screen.findByText(tr('imageUpload.uploadSuccess'))).toBeInTheDocument();
    await waitFor(() => expect(apiMock.getAppImage).toHaveBeenCalledWith(7, VERSION));
    await waitFor(() => expect(container.querySelector('img[src="blob:app-image"]')).not.toBeNull());
    expect(screen.getByRole('button', { name: tr('imageUpload.change') })).toBeInTheDocument();
  });

  it('removing the image goes back to the initials', async () => {
    apiMock.deleteAppImage.mockResolvedValue(null as never);
    const { user, container } = renderSettings('owner', VERSION);
    await waitFor(() => expect(container.querySelector('img[src="blob:app-image"]')).not.toBeNull());
    await user.click(screen.getByRole('button', { name: tr('imageUpload.remove') }));
    await waitFor(() => expect(apiMock.deleteAppImage).toHaveBeenCalledWith(7));
    await waitFor(() => expect(container.querySelector('img')).toBeNull());
    expect(screen.getByRole('button', { name: tr('imageUpload.upload') })).toBeInTheDocument();
  });

  it('members below administrator see the image but no controls', async () => {
    const { container } = renderSettings('editor', VERSION);
    await waitFor(() => expect(container.querySelector('img[src="blob:app-image"]')).not.toBeNull());
    expect(screen.queryByLabelText(tr('appSettingsPage.image.inputLabel'))).toBeNull();
    expect(screen.queryByRole('button', { name: tr('imageUpload.change') })).toBeNull();
  });
});

describe('Apps list: image', () => {
  it('loads the image of the Apps that have one, by version', async () => {
    const base = {
      created_at: '2026-01-01', owner_id: 1, role: 'owner', langsmith_configured: false, agent_rate_limit: 0,
      agent_count: 0, repository_count: 0, domain_count: 0, silo_count: 0, collaborator_count: 0,
    };
    apiMock.getApps.mockResolvedValue([
      { ...base, app_id: 1, name: 'With Image', image_updated_at: VERSION },
      { ...base, app_id: 2, name: 'Plain Workspace', image_updated_at: null },
    ] as never);
    apiMock.getAppImage.mockResolvedValue(new Blob(['img']) as never);
    const { container } = renderWithProviders(<AppsPage />);
    await screen.findByText('With Image');
    await waitFor(() => expect(container.querySelectorAll('img[src="blob:app-image"]')).toHaveLength(1));
    expect(apiMock.getAppImage).toHaveBeenCalledTimes(1);
    expect(apiMock.getAppImage).toHaveBeenCalledWith(1, VERSION);
    expect(screen.getByText('PW')).toBeInTheDocument();
  });
});
