import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { UserAvatar } from '../../src/components/ui/UserAvatar';
import ProfilePage from '../../src/pages/ProfilePage';
import { apiMock } from './apiMock';
import { renderWithProviders, tr } from './testUtils';

const userState = vi.hoisted(() => ({
  user: null as Record<string, unknown> | null,
  avatarUrl: null as string | null,
  setUser: (() => {}) as (user: unknown) => void,
}));

vi.mock('../../src/contexts/UserContext', () => ({
  useUser: () => ({ user: userState.user, loading: false, avatarUrl: userState.avatarUrl, setUser: userState.setUser }),
}));

const { ApiError } = await vi.importActual<typeof import('../../src/services/api')>('../../src/services/api');

describe('UserAvatar', () => {
  it('shows the initials without a picture', () => {
    const { container } = render(<UserAvatar name="Ane Etxeberria" />);
    expect(container).toHaveTextContent('AE');
    expect(container.querySelector('img')).toBeNull();
  });

  it('shows the picture and falls back to the initials when it fails to load', () => {
    const { container } = render(<UserAvatar name="Ane Etxeberria" src="blob:avatar" />);
    const img = container.querySelector('img');
    expect(img).toHaveAttribute('src', 'blob:avatar');
    expect(img).toHaveAttribute('alt', '');
    fireEvent.error(img!);
    expect(container.querySelector('img')).toBeNull();
    expect(container).toHaveTextContent('AE');
  });
});

describe('ProfilePage picture', () => {
  const baseUser = { user_id: 1, email: 'ane@example.com', name: 'Ane', is_authenticated: true };

  beforeEach(() => {
    userState.user = { ...baseUser, avatar_updated_at: null };
    userState.avatarUrl = null;
    userState.setUser = vi.fn();
    apiMock.getApps.mockResolvedValue([] as never);
    apiMock.getPendingInvitations.mockResolvedValue([] as never);
    apiMock.getMarketplaceQuotaUsage.mockResolvedValue({ call_count: 0, quota: 0, is_exempt: false } as never);
  });

  it('uploads a picture and stores its new version on the user', async () => {
    apiMock.uploadMyAvatar.mockResolvedValue({ image_updated_at: '2026-11-21T10:00:00Z' } as never);
    const { user } = renderWithProviders(<ProfilePage />);
    const file = new File(['png'], 'me.png', { type: 'image/png' });
    await user.upload(screen.getByLabelText(tr('profilePage.avatar.inputLabel')), file);
    await waitFor(() => expect(apiMock.uploadMyAvatar).toHaveBeenCalledWith(file));
    expect(userState.setUser).toHaveBeenCalledWith(expect.objectContaining({ avatar_updated_at: '2026-11-21T10:00:00Z' }));
    expect(await screen.findByText(tr('imageUpload.uploadSuccess'))).toBeInTheDocument();
  });

  it('rejects a file over 5 MB without uploading it', async () => {
    const { user } = renderWithProviders(<ProfilePage />);
    const file = new File([new Uint8Array(5 * 1024 * 1024 + 1)], 'big.png', { type: 'image/png' });
    await user.upload(screen.getByLabelText(tr('profilePage.avatar.inputLabel')), file);
    expect(await screen.findByText(tr('imageUpload.tooLarge'))).toBeInTheDocument();
    expect(apiMock.uploadMyAvatar).not.toHaveBeenCalled();
  });

  it('shows the backend reason when the server rejects the picture', async () => {
    apiMock.uploadMyAvatar.mockRejectedValue(
      new ApiError('bad', 400, { code: 'IMAGE_INVALID_TYPE', message: 'bad' }) as never,
    );
    const { user } = renderWithProviders(<ProfilePage />);
    await user.upload(
      screen.getByLabelText(tr('profilePage.avatar.inputLabel')),
      new File(['x'], 'x.png', { type: 'image/png' }),
    );
    expect(await screen.findByText(tr('imageUpload.invalidType'))).toBeInTheDocument();
  });

  it('removes the picture', async () => {
    userState.user = { ...baseUser, avatar_updated_at: '2026-11-21T10:00:00Z' };
    userState.avatarUrl = 'blob:avatar';
    apiMock.deleteMyAvatar.mockResolvedValue(null as never);
    const { user } = renderWithProviders(<ProfilePage />);
    expect(screen.queryByRole('button', { name: tr('imageUpload.upload') })).toBeNull();
    await user.click(screen.getByRole('button', { name: tr('imageUpload.remove') }));
    await waitFor(() => expect(apiMock.deleteMyAvatar).toHaveBeenCalled());
    expect(userState.setUser).toHaveBeenCalledWith(expect.objectContaining({ avatar_updated_at: null }));
  });
});
