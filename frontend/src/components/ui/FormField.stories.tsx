import { useState } from 'react';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { fn } from 'storybook/test';

import { FormField } from './FormField';

const meta = {
  title: 'UI/FormField',
  component: FormField,
  parameters: {
    layout: 'padded',
  },
  tags: ['autodocs'],
  argTypes: {
    type: {
      control: 'select',
      options: ['text', 'email', 'password', 'number', 'url', 'tel', 'time', 'file'],
    },
  },
  decorators: [
    (Story) => (
      <div className="max-w-md">
        <Story />
      </div>
    ),
  ],
  args: {
    id: 'agent-name',
    label: 'Agent name',
    value: '',
    placeholder: 'e.g. Support Assistant',
    onChange: fn(),
  },
} satisfies Meta<typeof FormField>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Interactive: Story = {
  render: function InteractiveField(args) {
    const [value, setValue] = useState(args.value ?? '');

    return (
      <FormField
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
    value: 'Support Assistant',
    disabled: true,
  },
};

export const WithHelpText: Story = {
  args: {
    helpText: 'Shown to users in the marketplace.',
  },
};

export const WithError: Story = {
  args: {
    value: 'a',
    error: 'Name must be at least 3 characters.',
  },
};

export const NumberInput: Story = {
  args: {
    id: 'max-depth',
    label: 'Max depth',
    type: 'number',
    value: 2,
    min: 0,
    max: 5,
    placeholder: undefined,
    helpText: '0–5 link-following levels from the seed URL.',
  },
};

export const Password: Story = {
  args: {
    id: 'api-key',
    label: 'API key',
    type: 'password',
    value: 'sk-0000000000000000',
    placeholder: undefined,
    autoComplete: 'off',
  },
};

export const FileInput: Story = {
  args: {
    id: 'import-file',
    label: 'Import file',
    type: 'file',
    accept: '.json',
    placeholder: undefined,
    helpText: 'JSON export of an agent.',
  },
};
