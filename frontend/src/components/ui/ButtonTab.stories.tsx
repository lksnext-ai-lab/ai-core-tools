import type { Meta, StoryObj } from '@storybook/react-vite';
import { fn } from 'storybook/test';
import { MessageSquare } from 'lucide-react';
import { MemoryRouter } from 'react-router-dom';

import ButtonTab from './ButtonTab';
import ButtonTabItem from './ButtonTabItem';
import BackgroundImage from './BackgroundImage';

const agentIconUrl =
  'data:image/svg+xml;utf8,' +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 34 34"><rect width="34" height="34" fill="#2a271c"/><text x="17" y="22" font-family="sans-serif" font-size="13" fill="#f4efe3" text-anchor="middle">HR</text></svg>',
  );

const meta = {
  title: 'UI/ButtonTab',
  component: ButtonTab,
  decorators: [
    (Story) => (
      <MemoryRouter>
        <Story />
      </MemoryRouter>
    ),
  ],
  parameters: {
    layout: 'padded',
  },
  tags: ['autodocs'],
  args: {
    children: null,
    ariaLabel: 'Recent conversations',
  },
} satisfies Meta<typeof ButtonTab>;

export default meta;
type Story = StoryObj<typeof meta>;

export const RecentConversations: Story = {
  render: (args) => (
    <div className="mx-auto max-w-3xl">
      <ButtonTab {...args}>
        <ButtonTabItem
          title="Product planning"
          description={'Mattin AI · Product assistant\nI have drafted an initial proposal for the next sprint.'}
          dateLabel="10 min ago"
          dateTime="2026-10-09T10:00:00Z"
          icon={<BackgroundImage icon={MessageSquare} variant="marron" />}
          onClick={fn()}
          onEdit={fn()}
          onDelete={fn()}
        />
        <ButtonTabItem
          title="Holiday policy"
          description={'HR Workspace · HR assistant\nYou have 23 working days of holiday per year.'}
          dateLabel="Yesterday"
          dateTime="2026-10-08T10:00:00Z"
          icon={<img src={agentIconUrl} alt="" className="h-full w-full object-cover" />}
          onClick={fn()}
          onEdit={fn()}
          onDelete={fn()}
        />
        <ButtonTabItem
          title="Documentation review"
          description={'Research · Research assistant\nNo messages yet'}
          dateLabel="3 days ago"
          dateTime="2026-10-06T10:00:00Z"
          icon={<BackgroundImage icon={MessageSquare} variant="marron" />}
          onClick={fn()}
          onEdit={fn()}
          onDelete={fn()}
        />
      </ButtonTab>
    </div>
  ),
};

export const MixedItems: Story = {
  args: {
    ariaLabel: 'Conversations',
  },
  render: (args) => (
    <div className="mx-auto max-w-3xl">
      <ButtonTab {...args}>
        <ButtonTabItem
          title="Editable conversation"
          description={'Mattin AI · Product assistant\nHover the row to see the edit and delete actions.'}
          dateLabel="10 min ago"
          dateTime="2026-10-09T10:00:00Z"
          icon={<BackgroundImage icon={MessageSquare} variant="marron" />}
          variant="edit"
          onClick={fn()}
          onEdit={fn()}
          onDelete={fn()}
        />
        <ButtonTabItem
          title="Linked conversation"
          description={'HR Workspace · HR assistant\nThis row navigates to the conversation.'}
          dateLabel="Yesterday"
          dateTime="2026-10-08T10:00:00Z"
          icon={<img src={agentIconUrl} alt="" className="h-full w-full object-cover" />}
          variant="link"
          to="/marketplace/chat/1"
        />
      </ButtonTab>
    </div>
  ),
};
