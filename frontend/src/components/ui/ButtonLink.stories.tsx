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
  args: { label: 'Abrir', to: '/', variant: 'primary', size: 'medium' },
};

export const Secondary: Story = {
  args: { label: 'Editar', to: '/', variant: 'secondary', size: 'medium' },
};

export const Table: Story = {
  args: { label: 'Ver detalle', to: '/', variant: 'table', size: 'small' },
};

export const Muted: Story = {
  args: { label: 'Volver', to: '/', variant: 'muted', size: 'control' },
};

export const Danger: Story = {
  args: { label: 'Eliminar', to: '/', variant: 'danger', size: 'small' },
};

export const WithIcon: Story = {
  args: {
    label: 'Editar',
    to: '/',
    variant: 'secondary',
    size: 'medium',
    icon: <Pencil className="h-4 w-4" aria-hidden="true" />,
  },
};

export const BackLink: Story = {
  args: {
    label: 'My Apps',
    to: '/',
    variant: 'secondary',
    size: 'medium',
    icon: <ChevronLeft className="h-4 w-4" aria-hidden="true" />,
  },
};