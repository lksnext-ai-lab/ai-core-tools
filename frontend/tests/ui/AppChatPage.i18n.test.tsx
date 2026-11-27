import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import i18n from '../../src/i18n';
import { apiError, apiMock, makeOptions, makeTurn, setupChatApi } from './apiMock';
import { chip, composer, renderAppChat, sendButton, waitForChat } from './testUtils';

const en = () => i18n.getFixedT('en', 'common');
const es = () => i18n.getFixedT('es', 'common');

/** No raw translation key and none of the listed English strings may be on screen. */
function expectTranslated(englishKeys: readonly string[]) {
  const text = document.body.textContent ?? '';
  expect(text).not.toMatch(/\b(appChat|agentPlayground|conversationSidebar|alert)\.[A-Za-z_]+/);
  for (const key of englishKeys) {
    const english = en()(key);
    const spanish = es()(key);
    expect(spanish, `es text of ${key} must differ from English`).not.toBe(english);
    expect(text, `English fallback of ${key} on screen`).not.toContain(english);
  }
}

describe('App Chat in Spanish', () => {
  it('translates the page, the selectors, the composer and the empty-model state', async () => {
    await i18n.changeLanguage('es');
    setupChatApi({
      options: makeOptions({
        ai_services: [{ service_id: 3, name: 'Gamma', is_system: false, lifecycle_status: 'retired' }],
        default_selection: null,
        has_usable_model: false,
      }),
      role: 'owner',
    });
    renderAppChat();
    await waitForChat();

    expect(await screen.findByText('No hay ningún modelo disponible para el chat')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Configurar servicios de IA' })).toBeInTheDocument();
    expect(screen.getByText('Elige el modelo, la fuente, las skills y las herramientas de cada mensaje')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Conversaciones' })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: es()('appChat.selection.groupLabel') })).toBeInTheDocument();
    expect(composer()).toHaveAccessibleName('Mensaje para el asistente…');
    expect(composer()).toHaveAccessibleDescription(
      'El envío está desactivado: esta App no tiene ningún modelo disponible para el chat.',
    );
    expect(sendButton()).toHaveAccessibleName('Enviar mensaje');
    expectTranslated([
      'appChat.empty.title',
      'appChat.empty.configureLink',
      'appChat.page.subtitle',
      'appChat.selection.groupLabel',
      'appChat.blocked.noUsableModel',
      'agentPlayground.chat.sendMessage',
    ]);
  });

  it('translates the turn warnings, the retired-model error and the notice', async () => {
    await i18n.changeLanguage('es');
    const stream = setupChatApi();
    const { user } = renderAppChat();
    await waitFor(() => expect(chip('model')).toHaveAccessibleName(/Alpha/));
    await waitFor(() => expect(composer()).toBeEnabled());

    // First turn: a warning comes back with the answer.
    await user.type(composer(), 'hola');
    await user.click(sendButton());
    await waitFor(() => expect(stream.turns).toHaveLength(1));
    stream.turns[0].done(41, 'Respuesta', makeTurn({ warnings: [{ kind: 'mcp_config', id: 30 }] }));
    const title = await screen.findByText('Parte de tu selección no se ha usado');
    const alert = title.closest('[role="alert"]') as HTMLElement;
    expect(alert).toHaveTextContent('No se pudo usar la configuración MCP "Tickets"');
    expect(within(alert).getByRole('button', { name: 'Descartar: Parte de tu selección no se ha usado' })).toBeInTheDocument();
    expectTranslated(['appChat.warnings.title', 'appChat.warnings.mcp_configNamed', 'alert.dismiss']);

    // Second turn: the model reached end of service.
    await user.type(composer(), 'otra vez');
    apiMock.streamAppChatMessage.mockRejectedValueOnce(apiError(409, 'SERVICE_RETIRED'));
    await user.click(sendButton());
    const retired = await screen.findAllByText(/fin de servicio/);
    expect(retired.length).toBeGreaterThanOrEqual(2); // the error in the conversation and the page notice
    expectTranslated(['appChat.transportErrors.serviceRetired', 'appChat.notices.serviceRetired']);
  });
});
