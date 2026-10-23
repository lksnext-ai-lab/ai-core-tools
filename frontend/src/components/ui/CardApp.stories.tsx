import type { Meta, StoryObj } from '@storybook/react-vite';
import { Settings } from 'lucide-react';

import { CardApp } from './CardApp';

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
      options: ['white', 'canvas', 'subtle', 'selected'],
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

export const Selected: Story = {
  args: {
    variant: 'selected',
    children: (
      <>
        <p className="text-sm font-medium text-fg dark:text-fg-dark">Guardrails</p>
        <p className="text-xs font-normal text-fg-secondary dark:text-fg-secondary-dark">
          Apply safety policies to model inputs and outputs.
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
      <CardApp {...args} variant="selected">
        <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">Selected</p>
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
    icon: Settings,
    titulo: 'Configuration',
    subtitulo: 'Configure the services and behavior used by this agent.',
    children: <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">Form fields for this section go here.</p>,
  },
};

export const TitleOnly: Story = {
  args: {
    titulo: 'Title only',
  },
};

export const SubtitleOnly: Story = {
  args: {
    subtitulo: 'A subtitle can be used without an icon or title.',
  },
};
