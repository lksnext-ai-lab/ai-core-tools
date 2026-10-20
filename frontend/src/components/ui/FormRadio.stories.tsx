import { useState } from 'react';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { fn } from 'storybook/test';

import { FormRadio } from './FormField';

const meta = {
  title: 'UI/FormRadio',
  component: FormRadio,
  parameters: {
    layout: 'padded',
  },
  tags: ['autodocs'],
  args: {
    label: 'Each run starts a new conversation',
    checked: false,
    onChange: fn(),
    className: 'flex gap-2 text-sm',
  },
} satisfies Meta<typeof FormRadio>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Unchecked: Story = {};

export const Checked: Story = {
  args: {
    checked: true,
  },
};

const conversationModes = [
  { value: 'new_per_run', label: 'Each run starts a new conversation' },
  { value: 'continuous', label: 'All runs continue the same conversation' },
];

export const Group: Story = {
  render: function RadioGroup(args) {
    const [mode, setMode] = useState(conversationModes[0].value);

    return (
      <fieldset>
        <legend className="mb-2 text-sm font-medium text-fg dark:text-fg-dark">Conversation mode</legend>
        {conversationModes.map((option) => (
          <FormRadio
            key={option.value}
            label={option.label}
            checked={mode === option.value}
            onChange={() => {
              args.onChange();
              setMode(option.value);
            }}
            className={`mb-2 ${args.className}`}
          />
        ))}
      </fieldset>
    );
  },
};

export const DisabledGroup: Story = {
  render: (args) => (
    <fieldset disabled>
      <legend className="mb-2 text-sm font-medium text-fg dark:text-fg-dark">Conversation mode</legend>
      {conversationModes.map((option, index) => (
        <FormRadio
          key={option.value}
          label={option.label}
          checked={index === 0}
          onChange={args.onChange}
          className={`mb-2 ${args.className}`}
        />
      ))}
    </fieldset>
  ),
};
