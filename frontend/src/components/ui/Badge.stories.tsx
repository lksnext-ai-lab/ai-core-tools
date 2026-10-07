import type { Meta, StoryObj } from '@storybook/react-vite';

import { Badge } from './Badge';

const meta = {
  title: 'UI/Badge',
  component: Badge,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
  argTypes: {
    variant: {
      control: 'select',
      options: ['success', 'info', 'warning', 'error', 'default', 'primary', 'secondary'],
    },
  },
} satisfies Meta<typeof Badge>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Success: Story = { args: { label: 'Success', variant: 'success' } };
export const Info: Story = { args: { label: 'Information', variant: 'info' } };
export const Warning: Story = { args: { label: 'Warning', variant: 'warning' } };
export const Error: Story = { args: { label: 'Error', variant: 'error' } };
export const Default: Story = { args: { label: 'Default', variant: 'default' } };
export const Primary: Story = { args: { label: 'Primary', variant: 'primary' } };
export const Secondary: Story = { args: { label: 'Secondary', variant: 'secondary' } };