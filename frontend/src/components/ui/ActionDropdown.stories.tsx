import { useState, type ComponentProps } from 'react';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { fn } from 'storybook/test';
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

export const IconOnlyTrigger: Story = {
  args: {
    triggerText: '',
    triggerAriaLabel: 'Row actions',
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

function ContextMenuDemo(args: ComponentProps<typeof ActionDropdown>) {
  const [position, setPosition] = useState<{ x: number; y: number } | null>(null);

  return (
    <>
      <div
        onContextMenu={(e) => {
          e.preventDefault();
          setPosition({ x: e.clientX, y: e.clientY });
        }}
        className="flex h-[200px] w-[360px] items-center justify-center rounded-lg border border-dashed border-line text-sm text-fg-tertiary dark:border-line-dark dark:text-fg-tertiary-dark"
      >
        Right-click anywhere in this area
      </div>
      <ActionDropdown
        {...args}
        position={position}
        isOpen={position !== null}
        onClose={() => setPosition(null)}
      />
    </>
  );
}

export const ContextMenu: Story = {
  render: (args) => <ContextMenuDemo {...args} />,
};
