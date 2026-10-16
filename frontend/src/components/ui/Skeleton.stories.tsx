import type { Meta, StoryObj } from '@storybook/react-vite';

import { Skeleton } from './Skeleton';

const meta = {
  title: 'UI/Skeleton',
  component: Skeleton,
  parameters: {
    layout: 'padded',
  },
  tags: ['autodocs'],
  argTypes: {
    shape: {
      control: 'select',
      options: ['line', 'block', 'round'],
    },
  },
} satisfies Meta<typeof Skeleton>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Line: Story = {
  args: { shape: 'line', className: 'h-3 w-48' },
};

export const Block: Story = {
  args: { shape: 'block', className: 'h-[104px] w-64' },
};

export const Round: Story = {
  args: { shape: 'round', className: 'h-16 w-16' },
};

export const TextLines: Story = {
  render: () => (
    <div className="w-80 space-y-2">
      <Skeleton className="h-5 w-40" />
      <Skeleton className="h-3 w-full" />
      <Skeleton className="h-3 w-5/6" />
      <Skeleton className="h-3 w-2/3" />
    </div>
  ),
};

export const ListRows: Story = {
  render: () => (
    <div className="w-96 space-y-3">
      {[1, 2, 3].map((i) => (
        <div key={i} className="flex items-center gap-3">
          <Skeleton className="h-3 w-28" />
          <Skeleton shape="round" className="h-2 flex-1" />
          <Skeleton className="h-3 w-8" />
        </div>
      ))}
    </div>
  ),
};

export const Card: Story = {
  render: () => (
    <div className="w-64 space-y-2 rounded-lg border border-line bg-surface p-3 dark:border-line-dark dark:bg-surface-dark">
      <Skeleton className="h-4 w-3/4" />
      <Skeleton className="h-3 w-1/2" />
      <div className="flex gap-1 pt-1">
        <Skeleton className="h-3 w-12" />
        <Skeleton className="h-3 w-10" />
      </div>
    </div>
  ),
};
