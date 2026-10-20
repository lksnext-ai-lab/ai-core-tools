import { useState } from 'react';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { fn } from 'storybook/test';
import { ChevronLeft, Store } from 'lucide-react';

import { ButtonApp } from './ButtonApp';

const meta = {
  title: 'UI/ButtonApp',
  component: ButtonApp,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
  argTypes: {
    variant: {
      control: 'select',
      options: ['primary', 'secondary', 'table', 'muted', 'danger', 'dangerSolid'],
    },
    size: {
      control: 'select',
      options: ['compact', 'small', 'control', 'medium', 'spacious', 'large'],
    },
  },
  args: {
    onClick: fn(),
  },
} satisfies Meta<typeof ButtonApp>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Primary: Story = {
  args: {
    label: 'New Agent',
    variant: 'primary',
    size: 'spacious',
    icon: <span aria-hidden="true">+</span>,
  },
};

export const Secondary: Story = {
  args: {
    label: 'My Apps',
    variant: 'secondary',
    size: 'medium',
    icon: <ChevronLeft className="h-[14px] w-[14px]" aria-hidden="true" />,
  },
};

export const Table: Story = {
  args: {
    label: 'Open',
    variant: 'table',
    size: 'small',
  },
};

export const Muted: Story = {
  args: {
    label: 'Edit',
    variant: 'muted',
    size: 'small',
  },
};

export const Danger: Story = {
  args: {
    label: 'Retry',
    variant: 'danger',
    size: 'compact',
  },
};

export const PrimaryIcon: Story = {
  args: {
    label: 'Browse Agents',
    variant: 'primary',
    size: 'spacious',
    icon: <Store className="h-4 w-4" aria-hidden="true" />,
  },
};

export const Variants: Story = {
  args: {
    label: 'Button',
    size: 'medium',
  },
  render: (args) => (
    <div className="flex items-center gap-3">
      <ButtonApp {...args} variant="primary" label="Primary" />
      <ButtonApp {...args} variant="secondary" label="Secondary" />
      <ButtonApp {...args} variant="table" label="Table" />
      <ButtonApp {...args} variant="muted" label="Muted" />
      <ButtonApp {...args} variant="danger" label="Danger" />
      <ButtonApp {...args} variant="dangerSolid" label="Danger Solid" />
    </div>
  ),
};

export const Sizes: Story = {
  args: {
    label: 'Button',
    variant: 'primary',
  },
  render: (args) => (
    <div className="flex items-center gap-3">
      <ButtonApp {...args} size="compact" label="Compact" />
      <ButtonApp {...args} size="small" label="Small" />
      <ButtonApp {...args} size="control" label="Control" />
      <ButtonApp {...args} size="medium" label="Medium" />
      <ButtonApp {...args} size="spacious" label="Spacious" />
      <ButtonApp {...args} size="large" label="Large" />
    </div>
  ),
};

export const Disabled: Story = {
  args: {
    label: 'Save',
    variant: 'primary',
    size: 'medium',
    disabled: true,
  },
};

export const Loading: Story = {
  args: {
    label: 'Saving...',
    size: 'medium',
  },
  render: (args) => (
    <div className="flex items-center gap-3">
      <ButtonApp {...args} variant="primary" loading />
      <ButtonApp {...args} variant="secondary" loading />
      <ButtonApp {...args} variant="danger" label="Deleting..." loading />
    </div>
  ),
};

function ToggleDemo(args: Story['args']) {
  const [pressed, setPressed] = useState(false);

  return (
    <ButtonApp
      {...args}
      label="My Apps"
      variant="primary"
      size="control"
      ariaPressed={pressed}
      onClick={() => setPressed((value) => !value)}
    />
  );
}

export const Toggle: Story = {
  args: {
    label: 'My Apps',
  },
  render: (args) => <ToggleDemo {...args} />,
};
