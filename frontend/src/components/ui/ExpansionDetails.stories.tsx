import type { Meta, StoryObj } from '@storybook/react-vite';

import ExpansionDetails from './ExpansionDetails';

const meta = {
  title: 'UI/ExpansionDetails',
  component: ExpansionDetails,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
  decorators: [
    (Story) => (
      <div className="w-[480px] max-w-full">
        <Story />
      </div>
    ),
  ],
  args: {
    header: 'Discovery',
    children: (
      <div className="space-y-1">
        <p className="text-sm font-medium text-fg dark:text-fg-dark">Sitemap URL</p>
        <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">
          https://example.com/sitemap.xml
        </p>
      </div>
    ),
  },
} satisfies Meta<typeof ExpansionDetails>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
