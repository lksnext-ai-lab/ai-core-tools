import { useState } from 'react';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { SegmentedTabs, type SegmentedTab } from './SegmentedTabs';

type DetailTab = 'general' | 'endpoints' | 'connection';

const detailTabs: SegmentedTab<DetailTab>[] = [
  { id: 'general', label: 'General' },
  { id: 'endpoints', label: 'Endpoints' },
  { id: 'connection', label: 'Conexión' },
];

const meta = {
  title: 'UI/SegmentedTabs',
  component: SegmentedTabs,
  tags: ['autodocs'],
  parameters: { layout: 'centered' },
  decorators: [
    (Story) => (
      <div className="w-[480px] max-w-full">
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof SegmentedTabs>;

export default meta;
type Story = StoryObj<typeof meta>;

export const ThreeOptions: Story = {
  args: {
    tabs: detailTabs,
    activeTab: 'general',
    onChange: () => undefined,
    ariaLabel: 'MCP server details',
  },
  render: function Render() {
    const [activeTab, setActiveTab] = useState<DetailTab>('general');
    return (
      <SegmentedTabs
        tabs={detailTabs}
        activeTab={activeTab}
        onChange={setActiveTab}
        ariaLabel="MCP server details"
      />
    );
  },
};

export const TwoOptions: Story = {
  args: {
    tabs: [
      { id: 'info', label: 'Información' },
      { id: 'runs', label: 'Ejecuciones' },
    ],
    activeTab: 'info',
    onChange: () => undefined,
    ariaLabel: 'Scheduled task details',
  },
  render: function Render() {
    const tabs: SegmentedTab<'info' | 'runs'>[] = [
      { id: 'info', label: 'Información' },
      { id: 'runs', label: 'Ejecuciones' },
    ];
    const [activeTab, setActiveTab] = useState<'info' | 'runs'>('info');
    return (
      <SegmentedTabs
        tabs={tabs}
        activeTab={activeTab}
        onChange={setActiveTab}
        ariaLabel="Scheduled task details"
      />
    );
  },
};
