import type { Meta, StoryObj } from '@storybook/react-vite';
import { fn } from 'storybook/test';
import { Bot } from 'lucide-react';

import ButtonTab from './ButtonTab';
import ButtonTabItem from './ButtonTabItem';

const meta = {
  title: 'UI/ButtonTab',
  component: ButtonTab,
  parameters: {
    layout: 'padded',
  },
  tags: ['autodocs'],
} satisfies Meta<typeof ButtonTab>;

export default meta;
type Story = StoryObj<typeof meta>;

export const ConversacionesRecientes: Story = {
  render: (args) => (
    <div className="mx-auto max-w-3xl">
      <ButtonTab {...args}>
        <ButtonTabItem
          title="Planificación de producto"
          subtitle="Mattin AI · Asistente de producto"
          description="He preparado una propuesta inicial para el próximo sprint."
          dateLabel="10 min"
          dateTime="2026-10-09T10:00:00Z"
          icon={<Bot className="h-[17px] w-[17px] text-[#816729]" aria-hidden="true" />}
          onEdit={fn()}
          onDelete={fn()}
        />
        <ButtonTabItem
          title="Análisis de documentación"
          subtitle="Workspace · Asistente de investigación"
          description="Encontré tres documentos relacionados con la consulta."
          dateLabel="Ayer"
          dateTime="2026-10-08T10:00:00Z"
          icon={<Bot className="h-[17px] w-[17px] text-[#816729]" aria-hidden="true" />}
          onEdit={fn()}
          onDelete={fn()}
        />
      </ButtonTab>
    </div>
  ),
  args: {
    children: null,
    ariaLabel: 'Conversaciones recientes',
  },
};