import { useState, type ComponentProps } from 'react';
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
  argTypes: {
    variant: {
      control: 'inline-radio',
      options: ['checkbox', 'toggle'],
    },
  },
  args: {
    id: 'has-memory',
    label: 'Enable memory',
    checked: false,
    onChange: fn(),
  },
} satisfies Meta<typeof FormCheckbox>;

export default meta;
type Story = StoryObj<typeof meta>;

function CheckboxDemo(args: ComponentProps<typeof FormCheckbox>) {
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
}

export const Interactive: Story = {
  render: (args) => <CheckboxDemo {...args} />,
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

export const Toggle: Story = {
  args: {
    id: 'ssl-verify',
    label: 'Verify SSL certificate',
    variant: 'toggle',
    checked: true,
  },
  render: (args) => <CheckboxDemo {...args} />,
};

export const ToggleWithHelpText: Story = {
  args: {
    id: 'ssl-verify-help',
    label: 'Verify SSL certificate',
    variant: 'toggle',
    checked: true,
    helpText: 'Disable only for servers that use self-signed certificates.',
  },
};

export const ToggleDisabled: Story = {
  args: {
    id: 'ssl-verify-disabled',
    label: 'Verify SSL certificate',
    variant: 'toggle',
    checked: true,
    disabled: true,
  },
};
