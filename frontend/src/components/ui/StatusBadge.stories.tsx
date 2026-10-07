import type { Meta, StoryObj } from '@storybook/react-vite';

import { StatusBadge } from './Badge';

const meta = {
  title: 'UI/StatusBadge',
  component: StatusBadge,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
  argTypes: {
    status: {
      control: 'select',
      options: ['active', 'inactive', 'pending', 'error', 'success', 'warning'],
    },
  },
} satisfies Meta<typeof StatusBadge>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Active: Story = { args: { status: 'active' } };
export const Inactive: Story = { args: { status: 'inactive' } };
export const Pending: Story = { args: { status: 'pending' } };
export const Error: Story = { args: { status: 'error' } };
export const Success: Story = { args: { status: 'success' } };
export const Warning: Story = { args: { status: 'warning' } };