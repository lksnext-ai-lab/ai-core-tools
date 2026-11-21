import type { Meta, StoryObj } from '@storybook/react-vite';

import { AppAvatar } from './AppAvatar';

const SAMPLE_IMAGE =
  'data:image/svg+xml;utf8,' +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" fill="#c9a46a"/><path d="M14 46 L28 24 L38 38 L44 30 L52 46 Z" fill="#fff7e8"/></svg>',
  );

const meta = {
  title: 'UI/AppAvatar',
  component: AppAvatar,
  parameters: { layout: 'centered' },
  tags: ['autodocs'],
  args: { name: 'Customer Support', size: 40 },
} satisfies Meta<typeof AppAvatar>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Initials: Story = {};
export const WithImage: Story = { args: { src: SAMPLE_IMAGE } };
export const Large: Story = { args: { src: SAMPLE_IMAGE, size: 64 } };
/** An image that fails to load falls back to the initials. */
export const BrokenImage: Story = { args: { src: 'https://invalid.example/missing.png', size: 64 } };
