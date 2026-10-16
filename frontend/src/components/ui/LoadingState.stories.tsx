import type { Meta, StoryObj } from '@storybook/react-vite';

import { LoadingState } from './LoadingState';

const meta = {
  title: 'UI/LoadingState',
  component: LoadingState,
  parameters: {
    layout: 'padded',
  },
  tags: ['autodocs'],
  argTypes: {
    variant: {
      control: 'select',
      options: ['inline', 'section', 'page', 'fullScreen'],
    },
  },
} satisfies Meta<typeof LoadingState>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Section: Story = {
  args: { variant: 'section', message: 'Cargando servicios de IA…' },
};

export const Inline: Story = {
  args: { variant: 'inline', message: 'Loading...' },
};

export const Page: Story = {
  args: { variant: 'page', message: 'Cargando agentes…' },
};

export const FullScreen: Story = {
  args: { variant: 'fullScreen', message: 'Comprobando tu sesión…' },
  parameters: { layout: 'fullscreen' },
};

export const InsideCard: Story = {
  args: { variant: 'section', message: 'Cargando URLs…' },
  render: (args) => (
    <div className="w-[480px] rounded-lg border border-line bg-surface dark:border-line-dark dark:bg-surface-dark">
      <LoadingState {...args} />
    </div>
  ),
};
