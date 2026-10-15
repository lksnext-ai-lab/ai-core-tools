import { useState } from 'react';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { fn } from 'storybook/test';
import { Clock } from 'lucide-react';

import { SidePanel } from './SidePanel';

const historyGroups = [
  {
    label: 'Today',
    items: [
      { title: 'Warranty of model X-200', time: '10:12', snippet: 'The warranty period for model X-200 is 24 months…' },
      { title: 'Supplier onboarding', time: '08:35', snippet: 'To onboard a supplier you need the form…' },
    ],
  },
  {
    label: 'Yesterday',
    items: [{ title: 'Return request', time: '17:40', snippet: 'How do I request a return? — You can start it from…' }],
  },
  {
    label: 'Previous 7 days',
    items: [
      { title: 'Premium maintenance', time: '12 Jul, 09:03', snippet: 'What does premium maintenance include?…' },
      { title: 'Holiday policy', time: '10 Jul, 16:20', snippet: 'Summarise the holiday policy — 23 working days…' },
    ],
  },
];

function HistoryList() {
  return (
    <>
      {historyGroups.map((group) => (
        <div key={group.label} className="mb-3.5">
          <div className="text-[11px] uppercase tracking-[0.05em] text-fg-tertiary dark:text-fg-tertiary-dark px-2.5 pt-1.5 pb-1">
            {group.label}
          </div>
          {group.items.map((item) => (
            <button
              key={item.title}
              type="button"
              className="w-full text-left flex flex-col gap-[3px] rounded-md px-2.5 py-[9px]
                         hover:bg-surface-hover dark:hover:bg-surface-hover-dark transition-colors duration-150"
            >
              <span className="flex items-baseline gap-2 w-full">
                <span className="flex-1 min-w-0 truncate text-[13.5px] font-medium text-fg dark:text-fg-dark">
                  {item.title}
                </span>
                <span className="flex-none text-[11.5px] text-fg-tertiary dark:text-fg-tertiary-dark">{item.time}</span>
              </span>
              <span className="truncate max-w-full text-[12.5px] leading-snug text-fg-tertiary dark:text-fg-tertiary-dark">
                {item.snippet}
              </span>
            </button>
          ))}
        </div>
      ))}
    </>
  );
}

const newButton = (
  <button
    type="button"
    className="font-display text-[12.5px] px-[11px] py-[5px] rounded-md
               border border-ink dark:border-ink-dark text-fg dark:text-fg-dark
               hover:bg-surface-hover dark:hover:bg-surface-hover-dark transition-colors duration-150"
  >
    New
  </button>
);

const searchInput = (
  <input
    type="search"
    placeholder="Search conversations…"
    aria-label="Search conversations"
    className="w-full rounded-md px-[11px] py-2 text-[13px]
               bg-surface dark:bg-surface-dark border border-line dark:border-line-dark
               text-fg dark:text-fg-dark placeholder:text-fg-tertiary dark:placeholder:text-fg-tertiary-dark
               focus:outline-none focus:border-accent dark:focus:border-accent-dark"
  />
);

const meta = {
  title: 'UI/SidePanel',
  component: SidePanel,
  parameters: {
    layout: 'fullscreen',
  },
  tags: ['autodocs'],
  argTypes: {
    side: {
      control: 'inline-radio',
      options: ['left', 'right'],
    },
  },
  args: {
    open: true,
    onClose: fn(),
    title: 'History',
    side: 'left',
    closeLabel: 'Close history',
    headerActions: newButton,
    toolbar: searchInput,
    children: <HistoryList />,
  },
  render: function InteractiveSidePanel(args) {
    const [open, setOpen] = useState(args.open);

    return (
      // SidePanel is absolutely positioned: it covers this `relative` frame.
      <div className="relative h-[560px] overflow-hidden bg-canvas dark:bg-canvas-dark">
        <div className="flex items-center justify-between gap-3 px-8 py-[18px] border-b border-line dark:border-line-dark">
          <h2 className="font-display text-lg font-normal tracking-tight text-fg dark:text-fg-dark">
            Product support
          </h2>
          <button
            type="button"
            onClick={() => setOpen(true)}
            title="Conversation history"
            aria-label="Conversation history"
            aria-expanded={open}
            className="w-[34px] h-[34px] flex items-center justify-center rounded-lg
                       border border-line dark:border-line-dark
                       text-fg-secondary dark:text-fg-secondary-dark
                       hover:bg-surface-hover dark:hover:bg-surface-hover-dark hover:text-fg dark:hover:text-fg-dark
                       transition-colors duration-150"
          >
            <Clock className="w-[17px] h-[17px]" />
          </button>
        </div>
        <p className="px-8 py-6 text-sm text-fg-secondary dark:text-fg-secondary-dark">
          Click the clock button to open the panel. Close it with the X, the backdrop or Escape.
        </p>

        <SidePanel
          {...args}
          open={open}
          onClose={() => {
            args.onClose();
            setOpen(false);
          }}
        />
      </div>
    );
  },
} satisfies Meta<typeof SidePanel>;

export default meta;
type Story = StoryObj<typeof meta>;

export const History: Story = {};

export const Right: Story = {
  args: {
    side: 'right',
  },
};

export const Simple: Story = {
  args: {
    title: 'Details',
    closeLabel: 'Close panel',
    headerActions: undefined,
    toolbar: undefined,
    children: (
      <p className="px-2.5 py-2 text-sm text-fg-secondary dark:text-fg-secondary-dark">
        Any content can go inside the panel.
      </p>
    ),
  },
};

export const Closed: Story = {
  args: {
    open: false,
  },
};
