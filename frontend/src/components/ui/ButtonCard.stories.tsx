import type { Meta, StoryObj } from '@storybook/react-vite';
import { fn } from 'storybook/test';
import { BookOpen, Bot } from 'lucide-react';

import { Badge } from './Badge';
import { ButtonApp } from './ButtonApp';
import { ButtonCard } from './ButtonCard';

const meta = {
  title: 'UI/ButtonCard',
  component: ButtonCard,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
  decorators: [
    (Story) => (
      <div className="w-[340px] max-w-full">
        <Story />
      </div>
    ),
  ],
  args: {
    children: null,
    onClick: fn(),
  },
} satisfies Meta<typeof ButtonCard>;

export default meta;
type Story = StoryObj<typeof meta>;

const appStats = [
  { label: 'AGENTS', value: 4 },
  { label: 'REPOS', value: 2 },
  { label: 'DOMAINS', value: 1 },
  { label: 'SILOS', value: 3 },
  { label: 'COLLABS', value: 5 },
];

function statCellClass(index: number) {
  return index < appStats.length - 1 ? 'border-r border-[#e0ddd6] dark:border-line-dark' : '';
}

function AppCardContent({ name, configured }: Readonly<{ name: string; configured: boolean }>) {
  return (
    <>
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-[34px] w-[34px] shrink-0 items-center justify-center overflow-hidden rounded-md border-[0.8px] border-[#FF682C] text-sm font-medium">
            {name.slice(0, 2).toUpperCase()}
          </div>
          <span className="min-w-0 text-[18px] leading-tight text-ink dark:text-ink-dark">{name}</span>
        </div>
        <span className="rounded-full bg-white px-2.5 py-1 text-[11px] font-medium text-fg-secondary">Owner</span>
      </div>
      <p className="mb-4 whitespace-pre-line text-[13.5px] leading-[1.45] text-fg-secondary dark:text-fg-secondary-dark">
        2026-10-09
      </p>
      <div className="mb-4 flex flex-wrap gap-2">
        <Badge label={configured ? 'Configured' : 'Not configured'} variant={configured ? 'success' : 'error'} />
      </div>
      <div className="relative z-0 mt-auto border-t border-[#e0ddd6] dark:border-line-dark">
        <div className="overflow-x-auto pt-2">
          <table className="table-fixed text-center leading-none">
            <thead>
              <tr>
                {appStats.map((stat, index) => (
                  <th
                    key={stat.label}
                    className={`px-2 py-0 text-[8px] font-medium uppercase tracking-[0.04em] text-fg-tertiary dark:text-fg-tertiary-dark ${statCellClass(index)}`}
                  >
                    {stat.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                {appStats.map((stat, index) => (
                  <td
                    key={stat.label}
                    className={`px-2 py-0 text-sm font-semibold text-ink dark:text-ink-dark ${statCellClass(index)}`}
                  >
                    {stat.value}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

function AgentCardContent({ name, description }: Readonly<{ name: string; description: string }>) {
  return (
    <>
      <div className="mb-3 flex min-w-0 items-center gap-3">
        <div className="flex h-[34px] w-[34px] shrink-0 items-center justify-center overflow-hidden rounded-md border-[0.8px] border-[#FF682C] text-sm font-medium">
          <Bot className="h-5 w-5 text-fg dark:text-fg-dark" aria-hidden="true" />
        </div>
        <div className="min-w-0 text-[18px] leading-tight">
          <span className="block text-ink dark:text-ink-dark">{name}</span>
          <span className="block text-[12.5px] text-fg-secondary dark:text-fg-secondary-dark">Support Workspace • 2026-10-09</span>
        </div>
      </div>
      <p className="mb-4 whitespace-pre-line text-[13.5px] leading-[1.45] text-fg-secondary dark:text-fg-secondary-dark">
        {description}
      </p>
      <div className="mb-4 flex flex-wrap gap-2">
        <Badge label="Customer Support" variant="error" />
        <Badge label="Knowledge" variant="success" icon={<BookOpen className="h-3 w-3" />} />
        <Badge label="faq" variant="default" />
      </div>
      <div className="relative z-0 mt-auto border-t border-[#e0ddd6] dark:border-line-dark">
        <div className="flex items-center gap-3 pt-3 text-xs text-fg-tertiary dark:text-fg-tertiary-dark">
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1">
            <span>4.6 (18)</span>
            <span>1,240 chats</span>
          </div>
          <ButtonApp
            label="Start Chat"
            variant="primary"
            size="compact"
            onClick={fn()}
            className="pointer-events-auto relative z-10 shrink-0"
          />
        </div>
      </div>
    </>
  );
}

export const AppCard: Story = {
  args: {
    ariaLabel: 'Open Document Support',
    children: <AppCardContent name="Document Support" configured />,
  },
};

export const AgentCard: Story = {
  args: {
    ariaLabel: 'Open Support Assistant',
    children: (
      <AgentCardContent
        name="Support Assistant"
        description="Answers customer questions using the product documentation."
      />
    ),
  },
};

export const Grid: Story = {
  decorators: [
    (Story) => (
      <div className="w-[1080px] max-w-full">
        <Story />
      </div>
    ),
  ],
  render: (args) => (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
      <ButtonCard {...args} ariaLabel="Open Document Support">
        <AppCardContent name="Document Support" configured />
      </ButtonCard>
      <ButtonCard {...args} ariaLabel="Open Sales Insights">
        <AppCardContent name="Sales Insights" configured={false} />
      </ButtonCard>
      <ButtonCard {...args} ariaLabel="Open Support Assistant">
        <AgentCardContent
          name="Support Assistant"
          description={'Answers customer questions using the product documentation.\nEscalates to a human when needed.'}
        />
      </ButtonCard>
    </div>
  ),
};
