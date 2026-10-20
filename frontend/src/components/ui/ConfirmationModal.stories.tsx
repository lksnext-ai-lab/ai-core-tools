import type { Meta, StoryObj } from '@storybook/react-vite';
import { fn } from 'storybook/test';

import ConfirmationModal from './ConfirmationModal';

const meta = {
  title: 'UI/ConfirmationModal',
  component: ConfirmationModal,
  parameters: {
    layout: 'fullscreen',
  },
  tags: ['autodocs'],
  argTypes: {
    variant: {
      control: 'inline-radio',
      options: ['danger', 'warning', 'info'],
    },
  },
  decorators: [
    (Story) => (
      <div className="min-h-[360px]">
        <Story />
      </div>
    ),
  ],
  args: {
    isOpen: true,
    onConfirm: fn(),
    onCancel: fn(),
  },
} satisfies Meta<typeof ConfirmationModal>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Danger: Story = {
  args: {
    variant: 'danger',
    title: 'Delete agent',
    message: 'This action cannot be undone. The agent and its conversations will be permanently deleted.',
    confirmLabel: 'Delete',
  },
};

export const Warning: Story = {
  args: {
    variant: 'warning',
    title: 'Discard changes',
    message: 'You have unsaved changes. Leaving this page will discard them.',
    confirmLabel: 'Discard',
  },
};

export const Info: Story = {
  args: {
    variant: 'info',
    title: 'Re-index repository',
    message: 'All documents will be processed again. This may take a few minutes.',
    confirmLabel: 'Re-index',
  },
};

export const Loading: Story = {
  args: {
    variant: 'danger',
    title: 'Delete agent',
    message: 'This action cannot be undone.',
    confirmLabel: 'Deleting...',
    isLoading: true,
  },
};

export const RichMessage: Story = {
  args: {
    variant: 'danger',
    title: 'Delete silo',
    message: (
      <>
        Are you sure you want to delete <strong className="text-fg dark:text-fg-dark">Product Docs</strong>?
        <br />
        The 3 agents using it will lose access to its knowledge base.
      </>
    ),
    confirmLabel: 'Delete',
  },
};
