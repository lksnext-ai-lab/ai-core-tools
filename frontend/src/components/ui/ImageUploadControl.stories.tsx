import type { Meta, StoryObj } from '@storybook/react-vite';
import { fn } from 'storybook/test';

import { ImageUploadControl } from './ImageUploadControl';

const meta = {
  title: 'UI/ImageUploadControl',
  component: ImageUploadControl,
  parameters: { layout: 'centered' },
  tags: ['autodocs'],
  args: {
    hasImage: false,
    inputLabel: 'Choose an image',
    onUpload: fn(async () => {}),
    onRemove: fn(async () => {}),
    onSuccess: fn(),
    onError: fn(),
  },
} satisfies Meta<typeof ImageUploadControl>;

export default meta;
type Story = StoryObj<typeof meta>;

export const NoImage: Story = {};
export const WithImage: Story = { args: { hasImage: true } };
export const Disabled: Story = { args: { hasImage: true, disabled: true } };
