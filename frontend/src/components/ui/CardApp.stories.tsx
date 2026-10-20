import type { Meta, StoryObj } from '@storybook/react-vite';
import { Settings } from 'lucide-react';

import { CardApp } from './CardApp';
import BackgroundImage from './BackgroundImage';

const meta = {
  title: 'UI/CardApp',
  component: CardApp,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
  argTypes: {
    variant: {
      control: 'inline-radio',
      options: ['white', 'canvas', 'subtle'],
    },
  },
  decorators: [
    (Story) => (
      <div className="w-[360px] max-w-full">
        <Story />
      </div>
    ),
  ],
  args: {
    children: <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">Card content goes here.</p>,
  },
} satisfies Meta<typeof CardApp>;

export default meta;
type Story = StoryObj<typeof meta>;

export const White: Story = {
  args: {
    variant: 'white',
  },
};

export const Canvas: Story = {
  args: {
    variant: 'canvas',
  },
};

export const Subtle: Story = {
  args: {
    variant: 'subtle',
    children: (
      <>
        <h2 className="text-base font-semibold text-fg dark:text-fg-dark">Workspace information</h2>
        <p className="mt-1 text-sm text-fg-secondary dark:text-fg-secondary-dark">
          This card uses the subtle surface variant.
        </p>
      </>
    ),
  },
};

export const Variants: Story = {
  render: (args) => (
    <div className="flex flex-col gap-4">
      <CardApp {...args} variant="white">
        <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">White</p>
      </CardApp>
      <CardApp {...args} variant="canvas">
        <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">Canvas</p>
      </CardApp>
      <CardApp {...args} variant="subtle">
        <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">Subtle</p>
      </CardApp>
    </div>
  ),
};

export const SectionWithHeader: Story = {
  decorators: [
    (Story) => (
      <div className="w-[640px] max-w-full">
        <Story />
      </div>
    ),
  ],
  args: {
    variant: 'white',
    className: 'p-8',
    children: (
      <>
        <div className="mb-6 flex items-center">
          <BackgroundImage icon={Settings} size={40} iconSize={20} variant="marron" className="mr-4 rounded-xl" />
          <h3 className="text-xl font-semibold text-fg dark:text-fg-dark">Configuration</h3>
        </div>
        <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">
          Form fields for this section go here.
        </p>
      </>
    ),
  },
};
