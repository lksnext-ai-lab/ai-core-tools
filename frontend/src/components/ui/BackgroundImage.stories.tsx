import type { Meta, StoryObj } from '@storybook/react-vite';

import { BackgroundImage } from './BackgroundImage';

const meta = {
  title: 'UI/BackgroundImage',
  component: BackgroundImage,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
  argTypes: {
    variant: {
      control: 'select',
      options: ['marron', 'vacio'],
    },
    icon: {
      control: 'select',
      options: ['Bot', 'FileText', 'MessageSquare', 'Store'],
    },
  },
} satisfies Meta<typeof BackgroundImage>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Size34: Story = {
  args: {
    icon: 'Bot',
    size: 34,
    variant: 'marron',
  },
};

export const Size40: Story = {
  args: {
    icon: 'FileText',
    size: 40,
    variant: 'marron',
  },
};

export const Siz48: Story = {
  args: {
    icon: 'MessageSquare',
    size: 48,
    variant: 'marron',
  },
};

export const VacioSinIcono: Story = {
  args: {
    icon: undefined,
    alt: '',
    text: 'YOU',
    size: 38,
    variant: 'vacio',
  },
};



