import type { Meta, StoryObj } from '@storybook/react-vite';
import { fn } from 'storybook/test';

import Alert from './Alert';

const meta = {
  title: 'UI/Alert',
  component: Alert,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
  argTypes: {
    type: {
      control: 'inline-radio',
      options: ['success', 'error', 'warning', 'info'],
    },
  },
  decorators: [
    (Story) => (
      <div className="w-[480px] max-w-full">
        <Story />
      </div>
    ),
  ],
  args: {
    message: 'Something happened that you should know about.',
    dismissLabel: 'Dismiss',
  },
} satisfies Meta<typeof Alert>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Success: Story = { args: { type: 'success', message: 'Changes saved successfully.' } };
export const ErrorAlert: Story = { name: 'Error', args: { type: 'error', message: 'Failed to load the data.' } };
export const Warning: Story = { args: { type: 'warning', message: 'This action may affect other resources.' } };
export const Info: Story = { args: { type: 'info', message: 'Embedding services convert text into vectors.' } };

export const CustomTitle: Story = {
  args: { type: 'error', title: 'Sync Error', message: 'The source could not be synchronized.' },
};

export const Dismissible: Story = {
  args: { type: 'info', message: 'You can close this message.', onDismiss: fn() },
};

export const RichMessage: Story = {
  args: {
    type: 'warning',
    title: 'Warnings',
    message: (
      <ul className="list-disc list-inside space-y-1">
        <li>Dependency not found.</li>
        <li>API keys must be reconfigured after import.</li>
      </ul>
    ),
  },
};
