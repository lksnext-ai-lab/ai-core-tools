import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, userEvent, within } from 'storybook/test';

import { MessageMetaBadge } from './MessageMetaBadge';

const labels = {
  source: 'Source',
  skills: 'Skills',
  mcps: 'MCP',
  deleted: '(deleted)',
  toggle: (model: string) => `Response details: ${model}`,
} as const;

const meta = {
  title: 'UI/MessageMetaBadge',
  component: MessageMetaBadge,
  parameters: { layout: 'centered' },
  tags: ['autodocs'],
  args: {
    labels,
    model: { id: 1, label: 'GPT-4o' },
  },
  decorators: [
    (Story) => (
      <div className="min-h-[160px] w-80 pt-4">
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof MessageMetaBadge>;

export default meta;
type Story = StoryObj<typeof meta>;

export const ModelOnly: Story = {};

export const WithDetails: Story = {
  args: {
    source: { id: 'r1', label: 'Product manuals' },
    skills: [
      { id: 1, label: 'Summarize' },
      { id: 2, label: 'Translate' },
    ],
    mcps: [{ id: 3, label: 'Jira' }],
  },
  play: async ({ canvasElement }) => {
    const toggle = within(canvasElement).getByRole('button');
    await expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(toggle);
    await expect(toggle).toHaveAttribute('aria-expanded', 'true');
    await expect(within(canvasElement).getByText('Product manuals')).toBeVisible();
  },
};

export const SourceOnly: Story = {
  args: { source: { id: 'd1', label: 'docs.example.com' } },
};

export const DeletedModel: Story = {
  args: { model: { id: 1, label: 'Retired model', deleted: true } },
};

export const DeletedResources: Story = {
  args: {
    source: { id: 'r1', label: 'Old repository', deleted: true },
    skills: [
      { id: 1, label: 'Summarize' },
      { id: 2, label: 'Removed skill', deleted: true },
    ],
    mcps: [{ id: 3, label: 'Removed server', deleted: true }],
  },
  play: async ({ canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole('button'));
    await expect(within(canvasElement).getAllByText('(deleted)')).toHaveLength(3);
  },
};

export const KeyboardToggle: Story = {
  args: { skills: [{ id: 1, label: 'Summarize' }] },
  play: async ({ canvasElement }) => {
    const toggle = within(canvasElement).getByRole('button');
    toggle.focus();
    await userEvent.keyboard('{Enter}');
    await expect(toggle).toHaveAttribute('aria-expanded', 'true');
    await userEvent.keyboard(' ');
    await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  },
};
