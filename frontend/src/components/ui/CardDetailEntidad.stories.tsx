import type { Meta, StoryObj } from '@storybook/react-vite';
import { fn } from 'storybook/test';
import { Bot } from 'lucide-react';

import { CardDetailEntidad } from './CardDetailEntidad';
import { Badge, ProviderBadge, StatusBadge } from './Badge';

const meta = {
  title: 'UI/CardDetailEntidad',
  component: CardDetailEntidad,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
  argTypes: {
    onClick: { action: 'card clicked' },
    onActionClick: { action: 'action clicked' },
  },
} satisfies Meta<typeof CardDetailEntidad>;

export default meta;
type Story = StoryObj<typeof meta>;

const ownerBadge = (
  <span className="rounded-full bg-white px-2.5 py-1 text-[11px] font-medium text-fg-secondary">
    Owner
  </span>
);

export const RecentAppCard: Story = {
  args: {
    badgeText: 'SD',
    titleCab: '',
    subTitleCab: undefined,
    title: 'Soporte Documental',
    description: 'Consulta y gestiona la documentación de tu organización.',
    metadata: '3 agentes · 8 miembros',
    onClick: fn(),
  },
};

export const MarketCard: Story = {
  args: {
    badgeText: 'LI',
    titleCab: '',
    subTitleCab: '',
    title: 'LKS Next INFO',
    description: 'Agente especializado en información corporativa.',
    metadata: 'Productividad · 4.8 ★',
    actionLabel: 'Iniciar chat',
    onClick: fn(),
    onActionClick: fn(),
  },
};

export const MyAppCard: Story = {
  args: {
    badgeText: 'RH',
    titleCab: '',
    subTitleCab: '',
    topRight: ownerBadge,
    title: 'RR.HH. Interno',
    description: 'Agentes y fuentes de datos para la gestión interna.',
    metadata: '6 agentes · 12 miembros',
    onClick: fn(),
  },
};

export const WithImage: Story = {
  args: {
    imageFallback: <Bot className="h-5 w-5 text-fg dark:text-fg-dark" aria-hidden="true" />,
    titleCab: 'Asistente IA',
    subTitleCab: 'Icono de agente',
    title: '',
    description: 'El icono aparece cuando no se proporciona una imagen.',
    metadata: 'Icono · Variante visual',
    onClick: fn(),
  },
};

export const WithBadges: Story = {
  args: {
    badgeText: 'BG',
    titleCab: '',
    subTitleCab: '',
    title: 'Card con etiquetas',
    description: 'Las etiquetas se muestran debajo de la descripción.',
    badges: [
      <Badge key="active" label="Activo" variant="success" />,
      <ProviderBadge key="provider" provider="OpenAI" />,
      <StatusBadge key="status" status="pending" />,
    ],
    metadata: '3 etiquetas · Variante visual',
    onClick: fn(),
  },
};

export const WithTable: Story = {
  args: {
    badgeText: 'TB',
    titleCab: '',
    subTitleCab: '',
    title: 'Card con tabla',
    description: 'Las métricas se muestran en una tabla compacta.',
    table: [
      { label: 'AGENTS', value: 0 },
      { label: 'REPOS', value: 0 },
      { label: 'DOMAINS', value: 0 },
      { label: 'SILOS', value: 0 },
      { label: 'COLLABS', value: 1 },
    ],
    metadata: 'Este contenido queda oculto',
    actionLabel: 'Acción oculta',
    onClick: fn(),
    onActionClick: fn(),
  },
};