import type { Meta, StoryObj } from '@storybook/react-vite';
import {
  Bot,
  CircleHelp,
  Code2,
  FileText,
  Lightbulb,
  MessageCircle,
  ShieldCheck,
  Sparkles,
  Star,
} from 'lucide-react';

import { Badge } from './Badge';

const iconOptions = {
  None: null,
  Bot: <Bot size={12} />,
  Help: <CircleHelp size={12} />,
  Code: <Code2 size={12} />,
  Document: <FileText size={12} />,
  Idea: <Lightbulb size={12} />,
  Message: <MessageCircle size={12} />,
  Security: <ShieldCheck size={12} />,
  Sparkles: <Sparkles size={12} />,
  Star: <Star size={12} />,
};

const meta = {
  title: 'UI/Badge',
  component: Badge,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
  argTypes: {
    variant: {
      control: 'select',
      options: ['success', 'info', 'warning', 'error', 'default', 'primary', 'secondary'],
    },
    icon: {
      control: 'select',
      options: Object.keys(iconOptions),
      mapping: iconOptions,
    },
  },
} satisfies Meta<typeof Badge>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Success: Story = { args: { label: 'Success', variant: 'success' } };
export const Info: Story = { args: { label: 'Information', variant: 'info' } };
export const Warning: Story = { args: { label: 'Warning', variant: 'warning' } };
export const Error: Story = { args: { label: 'Error', variant: 'error' } };
export const Default: Story = { args: { label: 'Default', variant: 'default' } };
export const Primary: Story = { args: { label: 'Primary', variant: 'primary' } };
export const Secondary: Story = { args: { label: 'Secondary', variant: 'secondary' } };
export const WithIcon: Story = {
  args: { label: 'Badge with icon', variant: 'info', icon: 'Bot' },
};