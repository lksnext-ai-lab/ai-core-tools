import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import i18n from '../../src/i18n';
import type { ChatSelectionWarning } from '../../src/types/appChat';
import { makeTurn, setupChatApi } from './apiMock';
import { chip, composer, renderAppChat, sendButton, waitForChat } from './testUtils';

async function sendWithWarnings(warnings: unknown[]) {
  const stream = setupChatApi();
  const { user } = renderAppChat();
  await waitForChat();
  await waitFor(() => expect(chip('model')).toHaveAccessibleName(/Alpha|Alfa/));
  await waitFor(() => expect(composer()).toBeEnabled());
  await user.type(composer(), 'make a file');
  await user.click(sendButton());
  await waitFor(() => expect(stream.turns).toHaveLength(1));
  stream.turns[0].metadata(41);
  stream.turns[0].done(41, 'Done', makeTurn({ warnings: warnings as ChatSelectionWarning[] }));
}

const alertOf = async () =>
  (await screen.findByRole('alert', {}, { timeout: 3000 })) as HTMLElement;

describe('Chat warning: sandbox output not delivered', () => {
  it('uses the singular form for one file (en)', async () => {
    await sendWithWarnings([{ kind: 'sandbox_output', id: 1 }]);
    expect(await screen.findByText('1 file created by the code could not be delivered (size, number or time limit).')).toBeInTheDocument();
  });

  it('uses the plural form for several files and keeps only the largest count (en)', async () => {
    await sendWithWarnings([{ kind: 'sandbox_output', id: 2 }, { kind: 'sandbox_output', id: 4 }]);
    expect(await screen.findByText('4 files created by the code could not be delivered (size, number or time limit).')).toBeInTheDocument();
    expect(screen.queryByText(/^2 files/)).not.toBeInTheDocument();
  });

  it('is translated, singular and plural (es)', async () => {
    await i18n.changeLanguage('es');
    await sendWithWarnings([{ kind: 'sandbox_output', id: 1 }]);
    expect(await screen.findByText('No se ha podido entregar 1 archivo creado por el código (límite de tamaño, número o tiempo).')).toBeInTheDocument();
  });

  it('is translated in the plural (es)', async () => {
    await i18n.changeLanguage('es');
    await sendWithWarnings([{ kind: 'sandbox_output', id: 3 }]);
    expect(await screen.findByText('No se han podido entregar 3 archivos creados por el código (límite de tamaño, número o tiempo).')).toBeInTheDocument();
  });

  it('never shows a raw key for a warning kind it does not know', async () => {
    await sendWithWarnings([{ kind: 'brand_new', id: 9 }, { kind: 'sandbox_output', id: 2 }]);
    const alert = await alertOf();
    await within(alert).findByText(/2 files created by the code/);
    expect(document.body.textContent).not.toMatch(/appChat\.warnings\.|brand_new/);
  });

  it('shows no warning box when the only warning is unknown', async () => {
    await sendWithWarnings([{ kind: 'brand_new', id: 9 }]);
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/apps/7/chat/41'));
    expect(document.body.textContent).not.toMatch(/appChat\.warnings\.|brand_new/);
    expect(screen.queryByText(i18n.t('appChat.warnings.title'))).not.toBeInTheDocument();
  });
});
