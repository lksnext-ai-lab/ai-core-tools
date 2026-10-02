import type { Meta, StoryObj } from '@storybook/react';
import { fn } from '@storybook/test';
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

export const DashboardMyApps: Story = {
  args: {
    label: 'My Apps',
    variant: 'secondary',
    size: 'medium',
    icon: <ChevronLeft className="h-[14px] w-[14px]" aria-hidden="true" />,
    onClick: fn(),
  },
};

export const AgentsNewAgent: Story = {
  args: {
    label: '+ Nuevo agente',
    variant: 'primary',
    size: 'spacious',
    onClick: fn(),
  },
};

export const AgentsOpen: Story = {
  args: {
    label: 'Abrir',
    variant: 'table',
    size: 'small',
    onClick: fn(),
  },
};

export const AgentsEdit: Story = {
  args: {
    label: 'Editar',
    variant: 'muted',
    size: 'small',
    onClick: fn(),
  },
};

export const DataSourcesRetry: Story = {
  args: {
    label: 'Reintentar',
    variant: 'danger',
    size: 'compact',
    onClick: fn(),
  },
};

export const McpServerConnect: Story = {
  args: {
    label: '+ Conectar',
    variant: 'secondary',
    size: 'medium',
    onClick: fn(),
  },
};

export const GeneralSettingsSave: Story = {
  args: {
    label: 'Guardar cambios',
    variant: 'primary',
    size: 'large',
    onClick: fn(),
  },
};

export const MarketplaceBrowseAgents: Story = {
  args: {
    label: 'Browse Agents',
    variant: 'primary',
    size: 'spacious',
    icon: <Store className="h-4 w-4" aria-hidden="true" />,
    onClick: fn(),
  },
};