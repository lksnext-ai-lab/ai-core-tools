import type { Meta, StoryObj } from '@storybook/react-vite';
import { ChevronLeft, Pencil } from 'lucide-react';
import { MemoryRouter } from 'react-router-dom';

import ButtonLink from './ButtonLink';

const meta = {
  title: 'UI/ButtonLink',
  component: ButtonLink,
  decorators: [
    (Story) => (
      <MemoryRouter>
        <Story />
      </MemoryRouter>
    ),
  ],
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
  argTypes: {
    variant: {
      control: 'select',
      options: ['primary', 'secondary', 'table', 'muted', 'danger'],
    },
    size: {
      control: 'select',
      options: ['compact', 'small', 'control', 'medium', 'spacious', 'large'],
    },
  },
} satisfies Meta<typeof ButtonLink>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Primary: Story = {
  args: { label: 'Open', to: '/', variant: 'primary', size: 'medium' },
};

export const Secondary: Story = {
  args: { label: 'View settings', to: '/', variant: 'secondary', size: 'medium' },
};

export const Table: Story = {
  args: { label: 'View details', to: '/', variant: 'table', size: 'small' },
};

export const Muted: Story = {
  args: { label: 'Back', to: '/', variant: 'muted', size: 'control' },
};

export const Danger: Story = {
  args: { label: 'View errors', to: '/', variant: 'danger', size: 'small' },
};

export const WithIcon: Story = {
  args: {
    label: 'Edit',
    to: '/',
    variant: 'secondary',
    size: 'medium',
    icon: <Pencil className="h-[14px] w-[14px]" aria-hidden="true" />,
  },
};

export const BackLink: Story = {
  args: {
    label: 'My Apps',
    to: '/',
    variant: 'secondary',
    size: 'medium',
    icon: <ChevronLeft className="h-[14px] w-[14px]" aria-hidden="true" />,
  },
};

export const Variants: Story = {
  args: {
    label: 'Link',
    to: '/',
    size: 'medium',
  },
  render: (args) => (
    <div className="flex items-center gap-3">
      <ButtonLink {...args} variant="primary" label="Primary" />
      <ButtonLink {...args} variant="secondary" label="Secondary" />
      <ButtonLink {...args} variant="table" label="Table" />
      <ButtonLink {...args} variant="muted" label="Muted" />
      <ButtonLink {...args} variant="danger" label="Danger" />
    </div>
  ),
};

export const Sizes: Story = {
  args: {
    label: 'Link',
    to: '/',
    variant: 'primary',
  },
  render: (args) => (
    <div className="flex items-center gap-3">
      <ButtonLink {...args} size="compact" label="Compact" />
      <ButtonLink {...args} size="small" label="Small" />
      <ButtonLink {...args} size="control" label="Control" />
      <ButtonLink {...args} size="medium" label="Medium" />
      <ButtonLink {...args} size="spacious" label="Spacious" />
      <ButtonLink {...args} size="large" label="Large" />
    </div>
  ),
};
