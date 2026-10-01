import type { Meta, StoryObj } from '@storybook/react';

import { Title } from './Title';

const meta = {
  title: 'UI/Title',
  component: Title,
  parameters: {
    layout: 'padded',
  },
  tags: ['autodocs'],
  args: {
    titulo: 'Buenos días, Tomás',
    subtitulo: 'Retoma una conversación reciente o entra en una de tus apps para gestionarla.',
  },
} satisfies Meta<typeof Title>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};