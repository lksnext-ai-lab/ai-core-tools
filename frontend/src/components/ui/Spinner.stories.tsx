import type { Meta, StoryObj } from '@storybook/react-vite';

import { Spinner } from './Spinner';

const meta = {
  title: 'UI/Spinner',
  component: Spinner,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
  argTypes: {
    size: {
      control: 'select',
      options: ['xs', 'sm', 'md', 'lg', 'xl'],
    },
    tone: {
      control: 'select',
      options: ['fg', 'current', 'muted'],
    },
  },
} satisfies Meta<typeof Spinner>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: { size: 'sm' },
};

export const WithLabel: Story = {
  args: { size: 'lg', label: 'Cargando agentes…' },
};

export const Sizes: Story = {
  render: () => (
    <div className="flex items-center gap-6">
      <Spinner size="xs" />
      <Spinner size="sm" />
      <Spinner size="md" />
      <Spinner size="lg" />
      <Spinner size="xl" />
    </div>
  ),
};

export const Tones: Story = {
  render: () => (
    <div className="flex items-center gap-6">
      <Spinner size="lg" tone="fg" />
      <Spinner size="lg" tone="muted" />
      <span className="inline-flex items-center gap-2 rounded-md bg-ink px-[15px] py-[9px] text-sm text-ink-on dark:bg-ink-dark dark:text-ink-on-dark">
        <Spinner tone="current" />
        Guardando…
      </span>
      <span className="inline-flex items-center gap-2 rounded-md border border-error px-[15px] py-[9px] text-sm text-error dark:border-error-dark dark:text-error-dark">
        <Spinner tone="current" />
        Eliminando…
      </span>
    </div>
  ),
};
