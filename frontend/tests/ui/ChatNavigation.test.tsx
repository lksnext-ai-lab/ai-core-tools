import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { Sidebar } from '../../src/components/sidebar/Sidebar';
import { defaultNavigation } from '../../src/core/defaultNavigation';
import appSource from '../../src/core/AppRoot.tsx?raw';
import { apiMock } from './apiMock';
import { renderWithProviders, tr } from './testUtils';

const userState = vi.hoisted(() => ({
  current: { is_admin: false, platform_role: 'viewer' } as { is_admin: boolean; platform_role: string },
}));

vi.mock('../../src/contexts/UserContext', () => ({
  useUser: () => ({ user: userState.current, loading: false }),
}));

function renderSidebar(config = defaultNavigation) {
  apiMock.getApps.mockResolvedValue([{ app_id: 7, name: 'Demo' }] as never);
  return renderWithProviders(
    <Routes>
      <Route path="/apps/:appId/*" element={<Sidebar navigationConfig={config} />} />
    </Routes>,
    { path: '/apps/7' },
  );
}

describe('Chat routes', () => {
  it('are open to any App member: wrapped in ProtectedLayoutRoute, not the editor or admin wrapper', () => {
    // Source-level guard: rendering AppRoot needs the whole auth stack.
    const lines = appSource.split('\n').filter((line) => /<Route path="\/apps\/:appId\/chat(\/:conversationId)?"/.test(line));
    expect(lines).toHaveLength(2);
    for (const line of lines) {
      expect(line).toContain('<ProtectedLayoutRoute');
      expect(line).not.toMatch(/EditorLayoutRoute|AdminLayoutRoute/);
      expect(line).toContain('<AppChatPage />');
    }
  });
});

describe('Chat menu entry', () => {
  it('is part of the default App navigation, open to every member', () => {
    const entry = defaultNavigation.appNavigation?.find((item) => item.path === '/apps/:appId/chat');
    expect(entry).toBeDefined();
    expect(entry?.adminOnly).toBeFalsy();
    expect(entry?.editorOnly).toBeFalsy();
  });

  it('is rendered, translated and linked to the App chat for a user with the platform role viewer', async () => {
    userState.current = { is_admin: false, platform_role: 'viewer' };
    renderSidebar();

    const link = await screen.findByRole('link', { name: tr('breadcrumbs.navigation.chat') });
    expect(link).toHaveAttribute('href', '/apps/7/chat');
    // Proves the Sidebar's role filter is active for this user (mocked `useUser` with platform_role 'viewer', not
    // an App role): an editor-only entry is hidden while the Chat entry, which has no role flag, is shown.
    expect(screen.queryByRole('link', { name: tr('breadcrumbs.navigation.myApps') })).not.toBeInTheDocument();
    // And the App panel (not just the global rail) is what is showing.
    expect(screen.getByRole('link', { name: tr('breadcrumbs.navigation.agents') })).toBeInTheDocument();
  });
});

describe('App settings menu', () => {
  it('opens the general App settings page from the expanded submenu', async () => {
    userState.current = { is_admin: false, platform_role: 'editor' };
    renderSidebar();

    await userEvent.click(await screen.findByRole('button', { name: tr('breadcrumbs.navigation.appSettings') }));
    const general = await screen.findByRole('link', { name: tr('breadcrumbs.navigation.general') });
    expect(general).toHaveAttribute('href', '/apps/7/settings/general');
  });
});
