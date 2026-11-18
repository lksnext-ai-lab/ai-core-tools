import type { Meta, StoryObj } from '@storybook/react-vite';
import { fn, userEvent, within } from 'storybook/test';
import { ArrowDownToLine, CheckCircle2, ClipboardCopy, Pencil, Plug, RefreshCw, Settings, Trash2 } from 'lucide-react';

import ActionDropdown, { type ActionItem } from './ActionDropdown';
import { Spinner } from './Spinner';

const serviceActions: ActionItem[] = [
  { label: 'Test Connection', onClick: fn(), icon: <Plug className="w-4 h-4" /> },
  { label: 'Edit', onClick: fn(), icon: <Pencil className="w-4 h-4" />, variant: 'primary' },
  { label: 'Copy', onClick: fn(), icon: <ClipboardCopy className="w-4 h-4" />, variant: 'primary' },
  { label: 'Delete', onClick: fn(), icon: <Trash2 className="w-4 h-4" />, variant: 'danger' },
];

const meta = {
  title: 'UI/ActionDropdown',
  component: ActionDropdown,
  parameters: {
    layout: 'centered',
    docs: {
      description: {
        component:
          'Actions menu rendered in a portal with fixed positioning, so it is never clipped by tables or scroll containers. '
          + 'Use `triggerAriaLabel` when the trigger has no visible text.',
      },
    },
  },
  tags: ['autodocs'],
  argTypes: {
    size: {
      control: 'inline-radio',
      options: ['sm', 'md', 'lg'],
    },
  },
  decorators: [
    (Story) => (
      <div className="min-h-[260px] pt-4">
        <Story />
      </div>
    ),
  ],
  args: {
    actions: serviceActions,
    size: 'sm',
  },
} satisfies Meta<typeof ActionDropdown>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Open: Story = {
  play: async ({ canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole('button', { name: /actions/i }));
  },
};

export const Sizes: Story = {
  render: (args) => (
    <div className="flex items-start gap-6">
      <ActionDropdown {...args} size="sm" />
      <ActionDropdown {...args} size="md" />
      <ActionDropdown {...args} size="lg" />
    </div>
  ),
};

export const CustomTrigger: Story = {
  args: {
    triggerText: 'Options',
    triggerIcon: <Settings className="w-4 h-4" />,
  },
};

export const WithRowAriaLabel: Story = {
  args: {
    triggerAriaLabel: 'Actions for Support agent',
  },
};

export const WithoutIcon: Story = {
  args: {
    triggerIcon: null,
  },
};

export const Variants: Story = {
  args: {
    actions: [
      { label: 'Default', onClick: fn() },
      { label: 'Primary', onClick: fn(), variant: 'primary' },
      { label: 'Secondary', onClick: fn(), variant: 'secondary' },
      { label: 'Success', onClick: fn(), icon: <CheckCircle2 className="w-4 h-4" />, variant: 'success' },
      { label: 'Warning', onClick: fn(), icon: <RefreshCw className="w-4 h-4" />, variant: 'warning' },
      { label: 'Danger', onClick: fn(), icon: <Trash2 className="w-4 h-4" />, variant: 'danger' },
    ],
  },
};

export const WithDisabledAndLoading: Story = {
  args: {
    actions: [
      { label: 'Testing...', onClick: fn(), icon: <Spinner size="sm" tone="current" />, disabled: true },
      { label: 'Export', onClick: fn(), icon: <ArrowDownToLine className="w-4 h-4" />, disabled: true },
      { label: 'Edit', onClick: fn(), icon: <Pencil className="w-4 h-4" />, variant: 'primary' },
      { label: 'Delete', onClick: fn(), icon: <Trash2 className="w-4 h-4" />, variant: 'danger' },
    ],
  },
};
