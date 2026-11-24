import { useState } from 'react';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, screen, userEvent, within } from 'storybook/test';
import { Bot, Database } from 'lucide-react';

import { Badge } from './Badge';
import {
  CompactSelectPopover,
  type CompactSelectOption,
  type CompactSelectPopoverMultipleProps,
  type CompactSelectPopoverSingleProps,
} from './CompactSelectPopover';

const models: readonly CompactSelectOption[] = [
  { value: 'gpt', label: 'GPT-4o', description: 'OpenAI' },
  { value: 'claude', label: 'Claude Sonnet', description: 'Anthropic' },
  { value: 'mistral', label: 'Mistral Large', description: 'MistralAI' },
];

const sources: readonly CompactSelectOption[] = [
  { value: '', label: 'None' },
  { value: 'repo-1', label: 'Product manuals', group: 'Repositories' },
  { value: 'repo-2', label: 'HR policies', group: 'Repositories' },
  { value: 'dom-1', label: 'docs.example.com', group: 'Web domains' },
  {
    value: 'silo-1',
    label: 'Legacy silo',
    group: 'Silos',
    disabled: true,
    disabledReason: 'Its embedding service is retired',
  },
];

const skills: readonly CompactSelectOption[] = [
  { value: 's1', label: 'Summarize' },
  { value: 's2', label: 'Translate' },
  { value: 's3', label: 'Code review' },
  { value: 's4', label: 'SQL helper', disabled: true, disabledReason: 'Not available in this app' },
];

const manyOptions: readonly CompactSelectOption[] = Array.from({ length: 40 }, (_, i) => ({
  value: `opt-${i}`,
  label: `Option ${i + 1}`,
  group: i < 20 ? 'First batch' : 'Second batch',
}));

function Stateful(args: Readonly<CompactSelectPopoverSingleProps>) {
  const [value, setValue] = useState<string | null>(args.value);
  return <CompactSelectPopover {...args} multiple={false} value={value} onChange={setValue} />;
}

function StatefulMulti(args: Readonly<CompactSelectPopoverMultipleProps>) {
  const [value, setValue] = useState<readonly string[]>(args.value);
  return <CompactSelectPopover {...args} multiple value={value} onChange={setValue} />;
}

const texts = {
  searchPlaceholder: 'Search…',
  emptyLabel: 'No results',
  resultsLabel: (count: number) => `${count} results`,
} as const;

const meta: Meta<CompactSelectPopoverSingleProps> = {
  title: 'UI/CompactSelectPopover',
  component: CompactSelectPopover,
  parameters: { layout: 'centered' },
  tags: ['autodocs'],
  args: {
    ariaLabel: 'Model',
    label: 'Model',
    options: models,
    value: 'gpt',
    onChange: () => undefined,
    ...texts,
  },
  render: (args) => <Stateful {...args} />,
  decorators: [
    (Story) => (
      <div className="flex min-h-[380px] w-80 items-start justify-center pt-4">
        <Story />
      </div>
    ),
  ],
};

export default meta;
type Story = StoryObj<CompactSelectPopoverSingleProps>;
type MultiStory = StoryObj<CompactSelectPopoverMultipleProps>;

const multiArgs: CompactSelectPopoverMultipleProps = {
  multiple: true,
  ariaLabel: 'Skills',
  label: 'Skills',
  placeholder: 'None',
  options: skills,
  value: ['s1'],
  onChange: () => undefined,
  summarizeSelection: (labels) => `${labels.length} selected`,
  selectionChangeLabel: (label, selected) => `${label} ${selected ? 'selected' : 'deselected'}`,
  ...texts,
};

export const Default: Story = {
  args: { icon: <Bot size={14} /> },
};

export const Empty: Story = {
  args: { options: [], value: null, placeholder: 'No models' },
};

export const NoSelection: Story = {
  args: { value: null, placeholder: 'Choose a model' },
};

export const Grouped: Story = {
  args: { ariaLabel: 'Source', label: 'Source', icon: <Database size={14} />, options: sources, value: '' },
  play: async ({ canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole('button', { name: /Source/ }));
    await expect(screen.getByRole('group', { name: 'Repositories' })).toBeInTheDocument();
  },
};

export const GroupHeaderWithSpaces: Story = {
  args: { ariaLabel: 'Source', label: 'Source', options: sources, value: 'dom-1' },
  play: async ({ canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole('button', { name: /Source/ }));
    await expect(screen.getByRole('group', { name: 'Web domains' })).toBeInTheDocument();
  },
};

export const DisabledOptionsWithReason: Story = {
  args: { ariaLabel: 'Source', label: 'Source', options: sources, value: 'repo-1' },
  play: async ({ canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole('button', { name: /Source/ }));
    const option = screen.getByRole('option', { name: /Legacy silo/ });
    await expect(option).toHaveAttribute('aria-disabled', 'true');
    await expect(option).toHaveTextContent('Its embedding service is retired');
  },
};

export const Searchable: Story = {
  args: { ariaLabel: 'Source', label: 'Source', options: sources, value: '', searchable: true },
  play: async ({ canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole('button', { name: /Source/ }));
    await userEvent.type(screen.getByRole('combobox'), 'zzz');
    await expect(screen.getAllByText('No results').length).toBeGreaterThan(0);
  },
};

export const Disabled: Story = {
  args: { value: 'claude', disabled: true },
};

export const WithTrailingBadge: Story = {
  args: {
    value: 'old',
    options: [
      ...models,
      { value: 'old', label: 'Legacy model', trailing: <Badge label="Deprecated" variant="warning" /> },
    ],
  },
};

export const LongLabel: Story = {
  args: {
    value: 'long',
    options: [
      ...models,
      { value: 'long', label: 'An extremely long model display name that will not fit in the chip' },
    ],
  },
};

export const ManyOptions: Story = {
  args: { ariaLabel: 'Option', label: 'Option', options: manyOptions, value: 'opt-3', searchable: true },
};

export const StaleSelection: Story = {
  args: {
    value: 'deleted-model',
    options: models,
    fallbackLabel: (value) => `${value} (deleted)`,
  },
};

export const MultipleSelection: MultiStory = {
  args: multiArgs,
  render: (args) => <StatefulMulti {...args} />,
  play: async ({ canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole('button', { name: /Skills/ }));
    await expect(screen.getByRole('listbox')).toHaveAttribute('aria-multiselectable', 'true');
    await userEvent.click(screen.getByRole('option', { name: 'Translate' }));
    await expect(screen.getByRole('option', { name: 'Translate' })).toHaveAttribute('aria-selected', 'true');
    await expect(screen.getByRole('status')).toHaveTextContent('Translate selected');
  },
};

export const MultipleSearchable: MultiStory = {
  args: { ...multiArgs, searchable: true },
  render: (args) => <StatefulMulti {...args} />,
};

export const ManySelected: MultiStory = {
  args: { ...multiArgs, value: ['s1', 's2', 's3'] },
  render: (args) => <StatefulMulti {...args} />,
};

export const KeyboardInteraction: Story = {
  play: async ({ canvasElement }) => {
    const trigger = within(canvasElement).getByRole('button', { name: /Model/ });
    trigger.focus();
    await userEvent.keyboard('{Enter}');
    await expect(trigger).toHaveAttribute('aria-expanded', 'true');
    await expect(trigger).toHaveAttribute('aria-haspopup', 'listbox');
    await userEvent.keyboard('{ArrowDown}{End}{Home}{ArrowDown}');
    await userEvent.keyboard('{Enter}');
    await expect(trigger).toHaveAttribute('aria-expanded', 'false');
    await expect(trigger).toHaveFocus();
    await expect(trigger).toHaveAccessibleName(/Claude Sonnet/);
    await userEvent.keyboard(' ');
    await userEvent.keyboard('{Escape}');
    await expect(trigger).toHaveAttribute('aria-expanded', 'false');
    await expect(trigger).toHaveFocus();
  },
};
