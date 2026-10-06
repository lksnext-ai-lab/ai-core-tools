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
      options: ['marron'],
    },
    icon: {
      control: 'select',
      options: ['Bot', 'FileText', 'MessagesSquare', 'Store'],
    },
  },
} satisfies Meta<typeof BackgroundImage>;

export default meta;
type Story = StoryObj<typeof meta>;

export const RecentConversation: Story = {
  args: {
    icon: 'Bot',
    size: 34,
    variant: 'marron',
  },
};

export const DocumentConversation: Story = {
  args: {
    icon: 'FileText',
    size: 40,
    variant: 'marron',
  },
};

export const SupportConversation: Story = {
  args: {
    icon: 'MessagesSquare',
    size: 48,
    variant: 'marron',
  },
};

export const Dark: Story = {
  args: {
    icon: 'Bot',
    size: 34,
    variant: 'marron',
  },
  parameters: {
    layout: 'fullscreen',
  },
  render: (args) => (
    <div className="dark flex min-h-screen items-center justify-center bg-canvas-dark p-8">
      <BackgroundImage {...args} />
    </div>
  ),
};

