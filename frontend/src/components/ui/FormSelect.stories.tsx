import { useState } from 'react';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { fn } from 'storybook/test';

import { FormSelect } from './FormField';

const options = [
  { value: '', label: 'Choose a service...' },
  { value: 'chat', label: 'Chat completion' },
  { value: 'embedding', label: 'Embeddings' },
  { value: 'vision', label: 'Vision' },
];

const meta = {
  title: 'UI/FormSelect',
  component: FormSelect,
  parameters: {
    layout: 'padded',
  },
  tags: ['autodocs'],
  args: {
    id: 'service-select',
    label: 'AI Service',
    value: '',
    options,
    onChange: fn(),
  },
} satisfies Meta<typeof FormSelect>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Interactive: Story = {
  render: function InteractiveSelect(args) {
    const [value, setValue] = useState(args.value);

    return (
      <FormSelect
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
    value: 'chat',
    disabled: true,
  },
};

export const WithHelpText: Story = {
  args: {
    helpText: 'Choose the model service this agent should use.',
  },
};

export const WithError: Story = {
  args: {
    error: 'Select a service to continue.',
  },
};