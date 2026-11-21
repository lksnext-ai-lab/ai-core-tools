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

const SAMPLE_PICTURE =
  'data:image/svg+xml;utf8,' +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" fill="#7a8fa6"/><circle cx="32" cy="25" r="12" fill="#e8edf2"/><rect x="12" y="42" width="40" height="30" rx="15" fill="#e8edf2"/></svg>',
  );

export const WithPicture: Story = { args: { src: SAMPLE_PICTURE, size: 64 } };
/** A picture that fails to load falls back to the initials. */
export const BrokenPicture: Story = { args: { src: 'https://invalid.example/missing.png', size: 64 } };
