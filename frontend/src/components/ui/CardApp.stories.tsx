import type { Meta, StoryObj } from '@storybook/react-vite';


import { CardApp } from './CardApp';

const meta = {
  title: 'UI/CardApp',
  component: CardApp,
  parameters: {
    layout: 'centered',
  },
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

