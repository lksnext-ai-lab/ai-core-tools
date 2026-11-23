import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { TurnMetaBadge } from '../../src/components/chat/TurnMetaBadge';
import { makeTurn, makeTurnConfig } from './apiMock';
import { renderWithProviders, tr } from './testUtils';

describe('TurnMetaBadge', () => {
  it('shows only the model, with no disclosure, when the turn used nothing else', () => {
    renderWithProviders(<TurnMetaBadge turn={makeTurn({ ai_service_name: 'Alpha' })} />);
    expect(screen.getByText('Alpha')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('expands and collapses the details with aria-expanded', async () => {
    const { user } = renderWithProviders(
      <TurnMetaBadge
        turn={makeTurn({
          ai_service_name: 'Alpha',
          silo_id: 10,
          silo_name: 'Handbook',
          skills: [{ id: 20, name: 'Summarize', deleted: false }],
          mcp_configs: [{ id: 30, name: 'Tickets', deleted: false }],
        })}
      />,
    );
    const toggle = screen.getByRole('button', { name: tr('appChat.meta.toggle', { model: 'Alpha' }) });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    const details = document.getElementById(toggle.getAttribute('aria-controls') as string) as HTMLElement;
    expect(details).not.toBeVisible();

    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(details).toBeVisible();
    expect(details).toHaveTextContent('Handbook');
    expect(details).toHaveTextContent('Summarize');
    expect(details).toHaveTextContent('Tickets');

    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(details).not.toBeVisible();
  });

  it('marks removed resources with "(deleted)" as text, keeping their names', async () => {
    const { user } = renderWithProviders(
      <TurnMetaBadge
        turn={makeTurn({
          ai_service_name: 'Alpha',
          ai_service_deleted: true,
          silo_id: 10,
          silo_name: 'Handbook',
          silo_deleted: true,
          skills: [
            { id: 20, name: 'Summarize', deleted: true },
            { id: 21, name: 'Translate', deleted: false },
          ],
        })}
      />,
    );
    // The model is deleted: its marker is part of the badge name, not colour only.
    const toggle = screen.getByRole('button', { name: `Details of Alpha ${tr('appChat.meta.deleted')}` });
    await user.click(toggle);
    const details = document.getElementById(toggle.getAttribute('aria-controls') as string) as HTMLElement;
    expect(details).toHaveTextContent('Handbook');
    expect(details).toHaveTextContent('Summarize');
    // One marker for the source and one for the deleted skill; the live skill has none.
    expect(details.textContent?.match(/\(deleted\)/g)).toHaveLength(2);
    expect(details).toHaveTextContent('Translate');
    expect(screen.getByText('Translate').parentElement).not.toHaveTextContent('(deleted)');
  });

  it('falls back to the metadata summary of a turn still streaming, where nothing is deleted yet', async () => {
    const { user } = renderWithProviders(
      <TurnMetaBadge turnConfig={makeTurnConfig({ ai_service: { id: 2, name: 'Beta' }, silo: { id: 10, name: null } })} />,
    );
    const toggle = screen.getByRole('button', { name: tr('appChat.meta.toggle', { model: 'Beta' }) });
    await user.click(toggle);
    // A source without a name gets the translated fallback.
    const details = document.getElementById(toggle.getAttribute('aria-controls') as string) as HTMLElement;
    expect(details).toHaveTextContent(tr('appChat.selection.unnamedSource', { id: 10 }));
    expect(document.body).not.toHaveTextContent('(deleted)');
  });

  it('renders nothing without a turn or a summary', () => {
    renderWithProviders(<TurnMetaBadge />);
    // Only the router probe (the current path) is on the page.
    expect(document.body.textContent).toBe('/');
  });
});
