import { useState } from 'react';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { fn } from 'storybook/test';

import { FormTextArea } from './FormField';

const meta = {
  title: 'UI/FormTextArea',
  component: FormTextArea,
  parameters: {
    layout: 'padded',
  },
  tags: ['autodocs'],
  decorators: [
    (Story) => (
      <div className="max-w-md">
        <Story />
      </div>
    ),
  ],
  args: {
    id: 'agent-description',
    label: 'Description',
    value: '',
    placeholder: 'Describe what this agent does...',
    onChange: fn(),
  },
} satisfies Meta<typeof FormTextArea>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Interactive: Story = {
  render: function InteractiveTextArea(args) {
    const [value, setValue] = useState(args.value);

    return (
      <FormTextArea
        {...args}
        value={value}
        onChange={(event) => {
          args.onChange(event);
          setValue(event.target.value);
        }}
      />
    );
  },
};

export const Required: Story = {
  args: {
    required: true,
  },
};

export const Disabled: Story = {
  args: {
    value: 'Answers customer questions using the product documentation.',
    disabled: true,
  },
};

export const WithHelpText: Story = {
  args: {
    helpText: 'A short summary shown in the marketplace card.',
    maxLength: 280,
  },
};

export const WithError: Story = {
  args: {
    error: 'Description is required.',
  },
};

export const Tall: Story = {
  args: {
    id: 'system-prompt',
    label: 'System prompt',
    rows: 8,
    value: 'You are a helpful assistant for the support team.\nAnswer using the knowledge base only.',
  },
};
