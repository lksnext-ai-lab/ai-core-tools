import type { Meta, StoryObj } from '@storybook/react';

import { Title } from './Title';

const meta = {
  title: 'UI/Title',
  component: Title,
  parameters: {
    layout: 'padded',
  },
  tags: ['autodocs'],
  argTypes: {
    variant: {
      control: 'select',
      options: ['titPrincipal', 'titSecundario', 'titTerciario'],
    },
    subtitleMarginBottom: {
      control: { type: 'number', min: 0, step: 1 },
    },
  },
  args: {
    titulo: 'Buenos días, Tomás',
    subtitulo: 'Retoma una conversación reciente o entra en una de tus apps para gestionarla.',
    subtitleMarginBottom: 40,
  },
} satisfies Meta<typeof Title>;

export default meta;
type Story = StoryObj<typeof meta>;

export const TitPrincipal: Story = {
  args: {
    variant: 'titPrincipal',
   subtitulo: 'Titulos de la páginas principales',
  },
};

export const TitSecundario: Story = {
  args: {
    variant: 'titSecundario',
    subtitulo: 'Titulos de la páginas principales de los submenus',
  },
};

export const TitTerciario: Story = {
  args: {
    variant: 'titTerciario',
    subtitulo: 'Titulos de la páginas que van a estar en un card con background',
  },
};