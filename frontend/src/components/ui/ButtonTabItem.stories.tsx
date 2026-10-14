import type { Meta, StoryObj } from '@storybook/react-vite';
import { fn } from 'storybook/test';
import { Bot } from 'lucide-react';
import { MemoryRouter } from 'react-router-dom';

import ButtonTab from './ButtonTab';
import ButtonTabItem from './ButtonTabItem';

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
  title: 'Planificación de producto',
  subtitle: 'Mattin AI · Asistente de producto',
  description: 'He preparado una propuesta inicial para el próximo sprint.',
  dateLabel: '10 min',
  dateTime: '2026-10-09T10:00:00Z',
  icon: <Bot className="h-[17px] w-[17px] text-[#816729]" aria-hidden="true" />,
  editingTitle: 'Planificación de producto',
  onEdit: fn(),
  onDelete: fn(),
  onTitleChange: fn(),
  onSaveTitle: fn(),
  onCancelEdit: fn(),
};

export const Edit: Story = {
  args: {
    ...sharedArgs,
    variant: 'edit',
  },
};

export const EditingTitle: Story = {
  args: {
    ...sharedArgs,
    variant: 'edit',
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