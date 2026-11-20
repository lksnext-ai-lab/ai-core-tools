import type { Meta, StoryObj } from '@storybook/react-vite';

import { UserAvatar } from './UserAvatar';

const meta = {
  title: 'UI/UserAvatar',
  component: UserAvatar,
  parameters: { layout: 'centered' },
  tags: ['autodocs'],
  args: { name: 'Aritz Galdos', email: 'aritz@example.com', size: 38 },
} satisfies Meta<typeof UserAvatar>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const EmailOnly: Story = { args: { name: undefined } };
export const Small: Story = { args: { size: 28 } };
