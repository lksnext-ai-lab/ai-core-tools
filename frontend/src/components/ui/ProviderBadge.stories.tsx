import type { Meta, StoryObj } from '@storybook/react-vite';

import { ProviderBadge } from './Badge';

const meta = {
  title: 'UI/ProviderBadge',
  component: ProviderBadge,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
} satisfies Meta<typeof ProviderBadge>;

export default meta;
type Story = StoryObj<typeof meta>;

export const OpenAI: Story = { args: { provider: 'OpenAI' } };
export const Azure: Story = { args: { provider: 'Azure' } };
export const MistralAI: Story = { args: { provider: 'MistralAI' } };
export const Ollama: Story = { args: { provider: 'Ollama' } };
export const Custom: Story = { args: { provider: 'Custom' } };
export const Anthropic: Story = { args: { provider: 'Anthropic' } };
export const Google: Story = { args: { provider: 'Google' } };