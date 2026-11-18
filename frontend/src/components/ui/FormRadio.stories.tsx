
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
    id: 'conversation-new',
    name: 'conversation_mode',
    value: 'new_per_run',
    label: 'Each run starts a new conversation',
    checked: false,
    onChange: fn(),
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

export const Disabled: Story = {
  args: {
    checked: false,
    disabled: true,
  },
};

export const DisabledChecked: Story = {
  args: {
    checked: true,
    disabled: true,
  },
};

export const WithHelpText: Story = {
  args: {
    helpText: 'A new conversation is created for every execution.',
  },
};

export const WithDescription: Story = {
  args: {
    label: (
      <span className="flex flex-col">
        <span className="font-medium">
          Start a new conversation
        </span>
        <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
          Previous messages will not be included.
        </span>
      </span>
    ),
  },
};

export const Required: Story = {
  args: {
    required: true,
  },
};

export const RadioOnly: Story = {
  args: {
    label: undefined,
    ariaLabel: 'Select this card',
    radioOnly: true,
  },
};

const conversationModes = [
  {
    value: 'new_per_run',
    label: 'Each run starts a new conversation',
  },
  {
    value: 'continuous',
    label: 'All runs continue the same conversation',
  },
];

export const Group: Story = {
  render: function RadioGroup(args) {
    const [mode, setMode] = useState(conversationModes[0].value);

    return (
      <fieldset>
        <legend className="mb-2 text-sm font-medium text-fg dark:text-fg-dark">
          Conversation mode
        </legend>

        <div className="space-y-2">
          {conversationModes.map((option) => (
            <FormRadio
              key={option.value}
              id={`conversation-${option.value}`}
              name="conversation_mode"
              value={option.value}
              label={option.label}
              checked={mode === option.value}
              onChange={() => {
                args.onChange();
                setMode(option.value);
              }}
            />
          ))}
        </div>
      </fieldset>
    );
  },
};

export const DisabledGroup: Story = {
  render: (args) => (
    <fieldset disabled>
      <legend className="mb-2 text-sm font-medium text-fg dark:text-fg-dark">
        Conversation mode
      </legend>

      <div className="space-y-2">
        {conversationModes.map((option, index) => (
          <FormRadio
            key={option.value}
            id={`disabled-conversation-${option.value}`}
            name="disabled_conversation_mode"
            value={option.value}
            label={option.label}
            checked={index === 0}
            onChange={args.onChange}
            disabled
          />
        ))}
      </div>
    </fieldset>
  ),
};
