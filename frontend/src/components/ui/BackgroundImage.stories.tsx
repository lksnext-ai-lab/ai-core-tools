import type { Meta, StoryObj } from '@storybook/react-vite';
import { Bot, Database, FileText, MessageSquare, Plug } from 'lucide-react';

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
      options: ['marron', 'vacio', 'gris'],
    },
    icon: {
      control: 'select',
      options: ['Bot', 'Database', 'FileText', 'MessageSquare', 'Plug'],
      mapping: { Bot, Database, FileText, MessageSquare, Plug },
    },
    rounded: {
      control: 'text',
    },
  },
} satisfies Meta<typeof BackgroundImage>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Size34: Story = {
  args: {
    icon: Bot,
    size: 34,
    variant: 'marron',
  },
};

export const Size40: Story = {
  args: {
    icon: FileText,
    size: 40,
    variant: 'marron',
  },
};

export const Size48: Story = {
  args: {
    icon: MessageSquare,
    size: 48,
    variant: 'marron',
  },
};

export const Variants: Story = {
  args: {
    icon: Database,
    size: 44,
  },
  render: (args) => (
    <div className="flex items-center gap-4">
      <BackgroundImage {...args} variant="marron" />
      <BackgroundImage {...args} variant="vacio" />
      <BackgroundImage {...args} variant="gris" />
    </div>
  ),
};

export const Rounded: Story = {
  args: {
    icon: Plug,
    size: 64,
    rounded: 'rounded-full',
    variant: 'marron',
  },
};

export const WithAlt: Story = {
  args: {
    icon: Bot,
    alt: 'Support agent',
    size: 70,
    variant: 'vacio',
  },
};

export const VacioSinIcono: Story = {
  args: {
    text: 'YOU',
    size: 38,
    variant: 'vacio',
  },
};
