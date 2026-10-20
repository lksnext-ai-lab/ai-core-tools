import { useState } from 'react';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { fn } from 'storybook/test';

import { FormCheckbox } from './FormField';

const meta = {
  title: 'UI/FormCheckbox',
  component: FormCheckbox,
  parameters: {
    layout: 'padded',
  },
  tags: ['autodocs'],
  args: {
    id: 'has-memory',
    label: 'Enable memory',
    checked: false,
    onChange: fn(),
  },
} satisfies Meta<typeof FormCheckbox>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Interactive: Story = {
  render: function InteractiveCheckbox(args) {
    const [checked, setChecked] = useState(args.checked);

    return (
      <FormCheckbox
        {...args}
        checked={checked}
        onChange={(event) => {
          args.onChange(event);
          setChecked(event.target.checked);
        }}
      />
    );
  },
};

export const Checked: Story = {
  args: {
    checked: true,
  },
};

export const WithHelpText: Story = {
  args: {
    helpText: 'The agent remembers previous messages in the conversation.',
  },
};

export const Disabled: Story = {
  args: {
    checked: true,
    disabled: true,
  },
};
