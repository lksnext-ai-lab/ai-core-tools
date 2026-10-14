
import type { Meta, StoryObj } from '@storybook/react-vite';
import { fn } from 'storybook/test';
import { CardDetailEntidad } from './CardDetailEntidad';
import type { CardDetailEntidadProps } from './CardDetailEntidad';

const meta = {
  title: 'UI/CardDetailEntidad',
  component: CardDetailEntidad,
  parameters: {
    layout: 'centered',
  },
  decorators: [
    (Story) => (
      <div className="w-[340px] max-w-full">
        <Story />
      </div>
    ),
  ],
} satisfies Meta<CardDetailEntidadProps>;

export default meta;

type Story = StoryObj<CardDetailEntidadProps>;

/* ==========================================
   1. Card básica
========================================== */

export const Default: Story = {
  args: {
    title: 'Soporte Documental',
    description: 'Aplicación para consultar y gestionar documentos.',
  },
};

/* ==========================================
   2. Cabecera con título y subtítulo
========================================== */

export const WithHeader: Story = {
  args: {
    titleCab: 'LKS Next INFO',
    subTitleCab: 'AI Agent',
    badgeText: 'AI',
    title: 'Asistente de información',
    description:
      'Consulta información de la empresa mediante inteligencia artificial.',
  },
};

/* ==========================================
   3. Imagen en la cabecera
========================================== */

export const WithImage: Story = {
  args: {
    titleCab: 'Gestión documental',
    subTitleCab: 'Application',
    imageSrc: 'https://placehold.co/100x100/png',
    imageAlt: 'Icono de la aplicación',
    title: 'Document Manager',
    description: 'Gestiona tus documentos y archivos.',
  },
};

/* ==========================================
   4. Texto en el recuadro de cabecera
========================================== */

export const WithBadgeText: Story = {
  args: {
    badgeText: 'RR',
    title: 'RR.HH. Interno',
    description: 'Gestión de recursos humanos.',
  },
};

/* ==========================================
   5. Elemento superior derecho
========================================== */

export const WithTopRight: Story = {
  args: {
    badgeText: 'SD',
    titleCab: 'Soporte Documental',
    title: 'Gestión documental',
    description: 'Consulta y administra documentación.',
    topRight: (
      <span
        className="
          inline-flex items-center justify-center
          rounded-full px-3 py-1 text-xs
          bg-success-bg text-success
          dark:bg-success-bg-dark dark:text-success-dark
        "
      >
        Active
      </span>
    ),
  },
};

/* ==========================================
   6. Card con badges
========================================== */

export const WithBadges: Story = {
  args: {
    badgeText: 'AI',
    title: 'Asistente inteligente',
    description: 'Agente especializado en consultas internas.',
    badges: [
      <span
        key="ai"
        className="
          rounded-full px-2 py-1 text-xs
          bg-bronze-bg text-bronze
          dark:bg-bronze-bg-dark dark:text-bronze-dark
        "
      >
        AI Agent
      </span>,
      <span
        key="docs"
        className="
          rounded-full px-2 py-1 text-xs
          bg-info-bg text-info
          dark:bg-info-bg-dark dark:text-info-dark
        "
      >
        Documents
      </span>,
    ],
  },
};

/* ==========================================
   7. Pie con metadata
========================================== */

export const WithMetadata: Story = {
  args: {
    badgeText: 'SD',
    title: 'Soporte Documental',
    description: 'Aplicación de gestión documental.',
    metadata: 'Última actividad: hace 2 horas',
  },
};

/* ==========================================
   8. Pie con botón
========================================== */

export const WithAction: Story = {
  args: {
    badgeText: 'AI',
    titleCab: 'LKS Next INFO',
    title: 'Asistente inteligente',
    description: 'Consulta información corporativa.',
    actionLabel: 'Iniciar chat',
    onActionClick: fn(),
  },
};

/* ==========================================
   9. Pie con metadata y botón
========================================== */

export const WithMetadataAndAction: Story = {
  args: {
    badgeText: 'AI',
    titleCab: 'LKS Next INFO',
    title: 'Asistente inteligente',
    description: 'Consulta información corporativa.',
    metadata: 'Última actividad: hace 2 horas',
    actionLabel: 'Iniciar chat',
    onActionClick: fn(),
  },
};

/* ==========================================
   10. Botón deshabilitado
========================================== */

export const WithDisabledAction: Story = {
  args: {
    badgeText: 'AI',
    title: 'Asistente no disponible',
    description: 'Este asistente no está disponible actualmente.',
    actionLabel: 'Iniciar chat',
    actionDisabled: true,
    onActionClick: fn(),
  },
};

/* ==========================================
   11. Pie con tabla de estadísticas
========================================== */

export const WithTable: Story = {
  args: {
    badgeText: 'RH',
    titleCab: 'RR.HH. Interno',
    title: 'Gestión de personas',
    description: 'Herramientas para la gestión de recursos humanos.',
    table: [
      { label: 'Agents', value: 12 },
      { label: 'Users', value: 4 },
      { label: 'Tasks', value: 8 },
    ],
  },
};

/* ==========================================
   12. Card sin acción principal
========================================== */

export const NotClickable: Story = {
  args: {
    badgeText: 'SD',
    title: 'Soporte Documental',
    description: 'Card informativa sin navegación.',
    onClick: undefined,
  },
};

/* ==========================================
   13. Card completa
========================================== */

export const Complete: Story = {
  args: {
    titleCab: 'LKS Next INFO',
    subTitleCab: 'AI Agent',
    badgeText: 'AI',
    title: 'Asistente corporativo',
    description:
      'Consulta información y documentos internos de forma rápida.',
    topRight: (
      <span
        className="
          inline-flex items-center justify-center
          rounded-full px-3 py-1 text-xs
          bg-success-bg text-success
          dark:bg-success-bg-dark dark:text-success-dark
        "
      >
        Active
      </span>
    ),
    badges: [
      <span
        key="agent"
        className="
          rounded-full px-2 py-1 text-xs
          bg-bronze-bg text-bronze
          dark:bg-bronze-bg-dark dark:text-bronze-dark
        "
      >
        AI Agent
      </span>,
    ],
    metadata: 'Última actividad: hace 2 horas',
    actionLabel: 'Iniciar chat',
    onActionClick: fn(),
  },
};
