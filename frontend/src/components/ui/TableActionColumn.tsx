import React from 'react';
import ActionDropdown from './ActionDropdown';
import type { ActionItem } from './ActionDropdown';

interface TableActionColumnProps {
  actions: ActionItem[];
  className?: string;
  size?: 'sm' | 'md' | 'lg';
  align?: 'left' | 'center' | 'right';
}

const TableActionColumn: React.FC<TableActionColumnProps> = ({
  actions,
  className = '',
  size = 'sm',
  align = 'right'
}) => {
  const getAlignmentClass = () => {
    switch (align) {
      case 'left':
        return 'text-left';
      case 'center':
        return 'text-center';
      case 'right':
        return 'text-right';
      default:
        return 'text-right';
    }
  };

  return (
    <td className={`px-6 py-4 whitespace-nowrap text-sm font-medium ${getAlignmentClass()} ${className}`}>
      <ActionDropdown
        actions={actions}
        size={size}
        className="inline-flex"
      />
    </td>
  );
};

export default TableActionColumn; 