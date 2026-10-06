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
    variant: { control: 'select' },
    size: { control: 'select' },
  },
} satisfies Meta<typeof ButtonApp>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Secunday: Story = {
  args: {
    label: 'My Apps',
    variant: 'secondary',
    size: 'medium',
    icon: <ChevronLeft className="h-[14px] w-[14px]" aria-hidden="true" />,
    onClick: fn(),
  },
};

export const Primary: Story = {
  args: {
    label: '+ Nuevo agente',
    variant: 'primary',
    size: 'spacious',
    onClick: fn(),
  },
};

export const Table: Story = {
  args: {
    label: 'Abrir',
    variant: 'table',
    size: 'small',
    onClick: fn(),
  },
};

export const Muted: Story = {
  args: {
    label: 'Editar',
    variant: 'muted',
    size: 'small',
    onClick: fn(),
  },
};

export const Danger: Story = {
  args: {
    label: 'Reintentar',
    variant: 'danger',
    size: 'compact',
    onClick: fn(),
  },
};


export const PrtimaryIcon: Story = {
  args: {
    label: 'Browse Agents',
    variant: 'primary',
    size: 'spacious',
    icon: <Store className="h-4 w-4" aria-hidden="true" />,
    onClick: fn(),
  },
};