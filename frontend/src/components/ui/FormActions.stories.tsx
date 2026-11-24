import type { Meta, StoryObj } from '@storybook/react-vite';
import { fn } from 'storybook/test';

import { FormActions } from './FormActions';

const meta = {
  title: 'UI/FormActions',
  component: FormActions,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
  decorators: [
    (Story) => (
      <form className="w-[560px] max-w-full" onSubmit={(event) => event.preventDefault()}>
        <Story />
      </form>
    ),
  ],
  args: {
    onCancel: fn(),
    isSubmitting: false,
  },
} satisfies Meta<typeof FormActions>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Creating: Story = {
  args: {
    isEditing: false,
    submitLabel: 'Create App',
  },
};

export const Editing: Story = {
  args: {
    isEditing: true,
  },
};

export const Submitting: Story = {
  args: {
    isSubmitting: true,
  },
};

export const CustomSubmittingLabel: Story = {
  args: {
    isSubmitting: true,
    submitLabel: 'Import',
    submittingLabel: 'Importing...',
  },
};

export const SubmitDisabled: Story = {
  args: {
    submitLabel: 'Create Skill',
    submitDisabled: true,
  },
};

export const WithoutCancel: Story = {
  args: {
    submitLabel: 'Import',
    showCancel: false,
  },
};
