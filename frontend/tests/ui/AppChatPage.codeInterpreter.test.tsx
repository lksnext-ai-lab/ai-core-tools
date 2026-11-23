import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import i18n from '../../src/i18n';
import type { ChatAttachmentIndexing, ChatCodeInterpreter } from '../../src/types/appChat';
import { apiMock, makeOptions, SELECTION, setupChatApi } from './apiMock';
import { chip, composer, dismissName, renderAppChat, tr } from './testUtils';

const DISABLED: ChatCodeInterpreter = { enabled: false, reason: 'disabled_in_app_settings' };
const PROVIDER: ChatCodeInterpreter = { enabled: false, reason: 'sandbox_provider_unavailable' };
const UNKNOWN = { enabled: false, reason: 'something_new' } as unknown as ChatCodeInterpreter;
const WITH_SKILL = { default_selection: { ...SELECTION, skill_ids: [20] } };

/** Options whose default selection has a skill, so the "not set up" notices apply. */
function opts(block: ChatCodeInterpreter | undefined, extra = {}) {
  return makeOptions({ ...WITH_SKILL, ...(block ? { code_interpreter: block } : {}), ...extra });
}
const RETIRED: ChatCodeInterpreter = { enabled: false, reason: 'sandbox_service_retired' };
const NO_EMBEDDING: ChatAttachmentIndexing = { enabled: false, reason: 'no_default_embedding_service' };

const codeDismissName = tr('alert.dismissNamed', { name: tr('appChat.codeInterpreter.title') });
const codeTitle = () => screen.queryByText(tr('appChat.codeInterpreter.title'));
const indexingTitle = () => screen.queryByText(tr('appChat.attachmentIndexing.title'));

async function ready() {
  await waitFor(() => expect(chip('model')).toHaveAccessibleName(/Alpha|Alfa/));
  await waitFor(() => expect(composer()).toBeEnabled());
}

async function roleLoaded() {
  await waitFor(() => expect(apiMock.getApp).toHaveBeenCalled());
  await apiMock.getApp.mock.results[0].value;
}

describe('Chat notice: code interpreter is off', () => {
  it.each([
    ['switched off', DISABLED, 'disabled'],
    ['retired sandbox', RETIRED, 'retired'],
  ])('administrators see the %s notice with a link to the App settings', async (_name, block, key) => {
    setupChatApi({ options: opts(block), role: 'administrator' });
    renderAppChat();
    await ready();

    const notice = (await screen.findByText(tr('appChat.codeInterpreter.title'))).closest('[role]') as HTMLElement;
    expect(notice).toHaveTextContent(tr(`appChat.codeInterpreter.${key}`).slice(0, 60));
    const link = await within(notice).findByRole('link', { name: tr('appChat.attachmentIndexing.configureLink') });
    expect(link).toHaveAttribute('href', '/apps/7/settings');
    expect(within(notice).queryByText(tr('appChat.attachmentIndexing.askAdmin'))).not.toBeInTheDocument();
  });

  it('a viewer is told to ask an administrator or owner, with no link', async () => {
    setupChatApi({ options: opts(DISABLED), role: 'viewer' });
    renderAppChat();
    await ready();
    await roleLoaded();

    const notice = (await screen.findByText(tr('appChat.codeInterpreter.title'))).closest('[role]') as HTMLElement;
    expect(await within(notice).findByText(new RegExp(tr('appChat.attachmentIndexing.askAdmin')))).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: tr('appChat.attachmentIndexing.configureLink') })).not.toBeInTheDocument();
  });

  it('shows both notices together and dismisses each independently', async () => {
    setupChatApi({
      options: opts(DISABLED, { attachment_indexing: NO_EMBEDDING }),
      role: 'owner',
    });
    const { user } = renderAppChat();
    await ready();
    expect(await screen.findByText(tr('appChat.codeInterpreter.title'))).toBeInTheDocument();
    expect(await screen.findByText(tr('appChat.attachmentIndexing.title'))).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: codeDismissName }));
    expect(codeTitle()).not.toBeInTheDocument();
    expect(indexingTitle()).toBeInTheDocument();
    expect(composer()).toHaveFocus();

    await user.click(screen.getByRole('button', { name: dismissName }));
    expect(indexingTitle()).not.toBeInTheDocument();
  });

  it('dismissing the indexing notice keeps the code notice', async () => {
    setupChatApi({
      options: opts(RETIRED, { attachment_indexing: NO_EMBEDDING }),
      role: 'owner',
    });
    const { user } = renderAppChat();
    await ready();
    await screen.findByText(tr('appChat.codeInterpreter.title'));
    await user.click(screen.getByRole('button', { name: dismissName }));
    expect(indexingTitle()).not.toBeInTheDocument();
    expect(codeTitle()).toBeInTheDocument();
  });

  it('comes back on the next visit while the condition holds', async () => {
    setupChatApi({ options: opts(DISABLED), role: 'owner' });
    const first = renderAppChat();
    await ready();
    await screen.findByText(tr('appChat.codeInterpreter.title'));
    await first.user.click(screen.getByRole('button', { name: codeDismissName }));
    first.unmount();

    renderAppChat();
    await ready();
    expect(await screen.findByText(tr('appChat.codeInterpreter.title'))).toBeInTheDocument();
  });

  it.each([
    ['enabled', { enabled: true, reason: null } as ChatCodeInterpreter],
    ['absent (older backend)', undefined],
  ])('is not shown when the code interpreter is %s', async (_name, block) => {
    setupChatApi({ options: opts(block), role: 'owner' });
    renderAppChat();
    await ready();
    await roleLoaded();
    expect(codeTitle()).not.toBeInTheDocument();
  });

  it('is translated in Spanish', async () => {
    await i18n.changeLanguage('es');
    setupChatApi({ options: opts(DISABLED), role: 'viewer' });
    renderAppChat();
    await screen.findByText('En este chat no se puede ejecutar código');
    await roleLoaded();
    expect(await screen.findByText(/ejecutar código en el Chat está desactivado para esta App/)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/appChat\.(codeInterpreter|attachmentIndexing)/);
  });

  it.each([
    ['viewer', 'viewer'],
    ['administrator', 'administrator'],
  ])('a %s gets no link and no ask-admin text when the provider is not allowed', async (_name, role) => {
    setupChatApi({ options: opts(PROVIDER), role });
    renderAppChat();
    await ready();
    await roleLoaded();
    const notice = (await screen.findByText(tr('appChat.codeInterpreter.title'))).closest('[role]') as HTMLElement;
    expect(notice).toHaveTextContent(/Contact the platform administrator/);
    expect(within(notice).queryByRole('link')).not.toBeInTheDocument();
    expect(within(notice).queryByText(tr('appChat.attachmentIndexing.askAdmin'))).not.toBeInTheDocument();
  });

  it('an unknown reason shows the generic text with no link', async () => {
    setupChatApi({ options: opts(UNKNOWN), role: 'owner' });
    renderAppChat();
    await ready();
    await roleLoaded();
    const notice = (await screen.findByText(tr('appChat.codeInterpreter.title'))).closest('[role]') as HTMLElement;
    expect(notice).toHaveTextContent(tr('appChat.codeInterpreter.unavailable'));
    expect(within(notice).queryByRole('link')).not.toBeInTheDocument();
  });
});

describe('Chat notice: code interpreter depends on the selected skills', () => {
  it.each([
    ['switched off', DISABLED],
  ])('%s: hidden without skills, shown with one, and follows the selection', async (_name, block) => {
    setupChatApi({ options: makeOptions({ code_interpreter: block }), role: 'owner' });
    const { user } = renderAppChat();
    await ready();
    await roleLoaded();
    expect(codeTitle()).not.toBeInTheDocument();

    await user.click(chip('skills'));
    const listbox = await screen.findByRole('listbox', { name: tr('appChat.selection.skills') });
    await user.click(within(listbox).getByRole('option', { name: /Summarize/ }));
    expect(await screen.findByText(tr('appChat.codeInterpreter.title'))).toBeInTheDocument();

    await user.click(within(listbox).getByRole('option', { name: /Summarize/ }));
    expect(codeTitle()).not.toBeInTheDocument();
  });

  it.each([
    ['retired', RETIRED],
    ['provider unavailable', PROVIDER],
    ['unknown', UNKNOWN],
  ])('%s: shown even with no skill selected', async (_name, block) => {
    setupChatApi({ options: makeOptions({ code_interpreter: block }), role: 'owner' });
    renderAppChat();
    await ready();
    expect(await screen.findByText(tr('appChat.codeInterpreter.title'))).toBeInTheDocument();
  });

  it('stays dismissed when the skills are deselected and selected again during the visit', async () => {
    setupChatApi({ options: opts(DISABLED), role: 'owner' });
    const { user } = renderAppChat();
    await ready();
    await screen.findByText(tr('appChat.codeInterpreter.title'));
    await user.click(screen.getByRole('button', { name: codeDismissName }));
    expect(codeTitle()).not.toBeInTheDocument();

    await user.click(chip('skills'));
    const listbox = await screen.findByRole('listbox', { name: tr('appChat.selection.skills') });
    await user.click(within(listbox).getByRole('option', { name: /Summarize/ })); // deselect
    await user.click(within(listbox).getByRole('option', { name: /Summarize/ })); // select again
    expect(within(listbox).getByRole('option', { name: /Summarize/ })).toHaveAttribute('aria-selected', 'true');
    expect(codeTitle()).not.toBeInTheDocument();
  });
});
