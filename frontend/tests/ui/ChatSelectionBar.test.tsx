import { useReducer } from 'react';
import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ChatSelectionBar } from '../../src/components/chat/ChatSelectionBar';
import { selectionReducer } from '../../src/components/chat/chatSelection';
import type { ChatOptions, ChatSelection } from '../../src/types/appChat';
import { makeOptions, SELECTION } from './apiMock';
import { chip, renderWithProviders, tr } from './testUtils';

/** Real reducer, like the page: the bar is judged by what the chips show after an interaction. */
function Harness({
  options,
  initial = SELECTION,
  disabled = false,
}: Readonly<{ options: ChatOptions; initial?: ChatSelection | null; disabled?: boolean }>) {
  const [selection, dispatch] = useReducer(selectionReducer, initial);
  return (
    <>
      <ChatSelectionBar options={options} selection={selection} dispatch={dispatch} disabled={disabled} />
      <output data-testid="selection">{JSON.stringify(selection)}</output>
    </>
  );
}

const currentSelection = (): ChatSelection => JSON.parse(screen.getByTestId('selection').textContent ?? 'null');

describe('ChatSelectionBar', () => {
  it('exposes a labelled group with four selectors named by purpose and current value', () => {
    renderWithProviders(
      <Harness
        options={makeOptions()}
        initial={{ ai_service_id: 2, silo_id: 10, skill_ids: [20], mcp_config_ids: [30] }}
      />,
    );
    const group = screen.getByRole('group', { name: tr('appChat.selection.groupLabel') });
    const buttons = within(group).getAllByRole('button');
    expect(buttons.map((b) => b.getAttribute('aria-haspopup'))).toEqual(['listbox', 'listbox', 'listbox', 'listbox']);
    expect(chip('model')).toHaveAccessibleName('Model Beta');
    expect(chip('source')).toHaveAccessibleName('Source Handbook');
    expect(chip('skills')).toHaveAccessibleName('Skills Summarize');
    expect(chip('mcps')).toHaveAccessibleName('MCP Tickets');
  });

  it('selects a model with the keyboard only', async () => {
    const { user } = renderWithProviders(<Harness options={makeOptions()} />);
    chip('model').focus();
    await user.keyboard('{Enter}');
    const listbox = await screen.findByRole('listbox', { name: tr('appChat.selection.model') });
    expect(chip('model')).toHaveAttribute('aria-expanded', 'true');
    expect(within(listbox).getByRole('option', { name: /Alpha/ })).toHaveAttribute('aria-selected', 'true');

    await user.keyboard('{ArrowDown}{Enter}');

    expect(currentSelection().ai_service_id).toBe(2);
    expect(chip('model')).toHaveAccessibleName('Model Beta');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    // Focus returns to the trigger so keyboard users keep their place.
    expect(chip('model')).toHaveFocus();
  });

  it('supports selecting and removing several skills without closing the list', async () => {
    const { user } = renderWithProviders(<Harness options={makeOptions()} />);
    await user.click(chip('skills'));
    const listbox = await screen.findByRole('listbox', { name: tr('appChat.selection.skills') });
    expect(listbox).toHaveAttribute('aria-multiselectable', 'true');

    await user.click(within(listbox).getByRole('option', { name: /Summarize/ }));
    await user.click(within(listbox).getByRole('option', { name: /Translate/ }));

    expect(screen.getByRole('listbox', { name: tr('appChat.selection.skills') })).toBeInTheDocument();
    expect(within(listbox).getByRole('option', { name: /Summarize/ })).toHaveAttribute('aria-selected', 'true');
    expect(within(listbox).getByRole('option', { name: /Translate/ })).toHaveAttribute('aria-selected', 'true');
    expect(currentSelection().skill_ids).toEqual([20, 21]);
    // App and system skills are grouped.
    expect(within(listbox).getByText(tr('appChat.skillGroups.app'))).toBeInTheDocument();
    expect(within(listbox).getByText(tr('appChat.skillGroups.system'))).toBeInTheDocument();

    await user.click(within(listbox).getByRole('option', { name: /Summarize/ }));
    expect(currentSelection().skill_ids).toEqual([21]);
    await user.keyboard('{Escape}');
    expect(chip('skills')).toHaveAccessibleName('Skills Translate');
  });

  it('summarises more than two selected skills as a count', () => {
    const options = makeOptions({
      skills: [1, 2, 3].map((id) => ({ skill_id: id, name: `Skill ${id}`, is_system: false })),
    });
    renderWithProviders(
      <Harness options={options} initial={{ ai_service_id: 1, silo_id: null, skill_ids: [1, 2, 3], mcp_config_ids: [] }} />,
    );
    expect(chip('skills')).toHaveAccessibleName(`Skills ${tr('appChat.selection.nSelected', { count: 3 })}`);
  });

  it('shows the selected retired model disabled with its reason, hides other retired models, and cannot pick it', async () => {
    const options = makeOptions({
      ai_services: [
        { service_id: 1, name: 'Alpha', is_system: false, lifecycle_status: 'retired' },
        { service_id: 2, name: 'Beta', is_system: false, lifecycle_status: 'active' },
        { service_id: 3, name: 'Gamma', is_system: false, lifecycle_status: 'retired' },
      ],
    });
    const { user } = renderWithProviders(<Harness options={options} initial={{ ...SELECTION, ai_service_id: 1 }} />);
    expect(chip('model')).toHaveAccessibleName(/Alpha/);
    await user.click(chip('model'));

    const retired = await screen.findByRole('option', { name: /Alpha/ });
    expect(retired).toHaveAttribute('aria-disabled', 'true');
    expect(retired).toHaveTextContent(tr('appChat.selection.modelRetired'));
    expect(screen.queryByRole('option', { name: /Gamma/ })).not.toBeInTheDocument();

    await user.click(retired);
    expect(currentSelection().ai_service_id).toBe(1);
    await user.click(screen.getByRole('option', { name: /Beta/ }));
    expect(currentSelection().ai_service_id).toBe(2);
  });

  it('shows a source whose embedding service is retired disabled with its reason', async () => {
    const options = makeOptions({
      silos: [
        { silo_id: 10, name: 'Handbook', source_type: 'repository' },
        { silo_id: 11, name: 'Old index', source_type: 'silo', disabled_reason: 'embedding_service_retired' },
      ],
    });
    const { user } = renderWithProviders(<Harness options={options} />);
    await user.click(chip('source'));
    const disabled = await screen.findByRole('option', { name: /Old index/ });
    expect(disabled).toHaveAttribute('aria-disabled', 'true');
    expect(disabled).toHaveTextContent(tr('appChat.siloDisabled.embedding_service_retired'));
    await user.click(disabled);
    expect(currentSelection().silo_id).toBeNull();
    await user.click(screen.getByRole('option', { name: /Handbook/ }));
    expect(currentSelection().silo_id).toBe(10);
    await user.click(chip('source'));
    await user.click(await screen.findByRole('option', { name: tr('appChat.selection.sourceNone') }));
    expect(currentSelection().silo_id).toBeNull();
  });

  it('locks every selector when disabled', async () => {
    const { user } = renderWithProviders(<Harness options={makeOptions()} disabled />);
    for (const key of ['model', 'source', 'skills', 'mcps'] as const) {
      expect(chip(key)).toBeDisabled();
    }
    await user.click(chip('model'));
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('with no selection only the model can be chosen, and choosing it starts a bare selection', async () => {
    const { user } = renderWithProviders(<Harness options={makeOptions()} initial={null} />);
    expect(chip('model')).toHaveAccessibleName(`Model ${tr('appChat.selection.modelPlaceholder')}`);
    expect(chip('source')).toBeDisabled();
    expect(chip('skills')).toBeDisabled();
    expect(chip('mcps')).toBeDisabled();
    await user.click(chip('model'));
    await user.click(await screen.findByRole('option', { name: /Beta/ }));
    expect(currentSelection()).toEqual({ ai_service_id: 2, silo_id: null, skill_ids: [], mcp_config_ids: [] });
    expect(chip('skills')).toBeEnabled();
  });
});
