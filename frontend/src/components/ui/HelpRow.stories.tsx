import type { Meta, StoryObj } from '@storybook/react-vite';

import HelpRow from './HelpRow';

const meta = {
  title: 'UI/HelpRow',
  component: HelpRow,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
  decorators: [
    (Story) => (
      <div className="w-[680px] max-w-full">
        <Story />
      </div>
    ),
  ],
  args: {
    title: 'How does it work?',
    children: 'Each task sends its message to the agent at the scheduled time.',
  },
} satisfies Meta<typeof HelpRow>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Dark: Story = {
  decorators: [
    (Story) => (
      <div className="dark rounded-lg bg-canvas-dark p-6">
        <Story />
      </div>
    ),
  ],
};
