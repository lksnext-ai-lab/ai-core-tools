import type { Meta, StoryObj } from '@storybook/react-vite';
import { fn } from 'storybook/test';
import { MessageSquare } from 'lucide-react';
import { MemoryRouter } from 'react-router-dom';

import ButtonTab from './ButtonTab';
import ButtonTabItem from './ButtonTabItem';
import BackgroundImage from './BackgroundImage';

const meta = {
  title: 'UI/ButtonTabItem',
  component: ButtonTabItem,
  decorators: [
    (Story) => (
      <MemoryRouter>
        <div className="mx-auto max-w-3xl">
          <ButtonTab ariaLabel="Conversation example">
            <Story />
          </ButtonTab>
        </div>
      </MemoryRouter>
    ),
  ],
  tags: ['autodocs'],
  argTypes: {
    variant: {
      control: 'select',
      options: ['edit', 'link'],
    },
  },
} satisfies Meta<typeof ButtonTabItem>;

export default meta;
type Story = StoryObj<typeof meta>;

const sharedArgs = {
  title: 'Product planning',
  description: 'Mattin AI · Product assistant — I have drafted an initial proposal for the next sprint.',
  icon: <BackgroundImage icon={MessageSquare} variant="marron" />,
};

const editArgs = {
  ...sharedArgs,
  variant: 'edit' as const,
  dateLabel: '10 min ago',
  dateTime: '2026-10-09T10:00:00Z',
  onEdit: fn(),
  onDelete: fn(),
  onTitleChange: fn(),
  onSaveTitle: fn(),
  onCancelEdit: fn(),
};

export const Edit: Story = {
  args: editArgs,
};

export const Clickable: Story = {
  args: {
    ...editArgs,
    onClick: fn(),
  },
};

export const EditingTitle: Story = {
  args: {
    ...editArgs,
    isEditing: true,
  },
};

export const Link: Story = {
  args: {
    ...sharedArgs,
    variant: 'link',
    to: '/marketplace/chat/42',
  },
};
