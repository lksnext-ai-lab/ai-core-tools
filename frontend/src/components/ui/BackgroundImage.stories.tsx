import type { Meta, StoryObj } from '@storybook/react';

import { BackgroundImage } from './BackgroundImage';

const meta = {
  title: 'UI/BackgroundImage',
  component: BackgroundImage,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
  argTypes: {
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
    backgroundColor: '#ebe6dd',
    iconColor: '#816729',
  },
};

export const DocumentConversation: Story = {
  args: {
    icon: 'FileText',
    size: 40,
    backgroundColor: '#eef4fb',
    iconColor: '#3a5573',
  },
};

export const SupportConversation: Story = {
  args: {
    icon: 'MessagesSquare',
    size: 48,
    backgroundColor: '#eaf5ef',
    iconColor: '#1f7a4d',
  },
};