import React, { useState, useRef, useEffect } from 'react';

export interface ActionItem {
  label: string;
  onClick: () => void;
  icon?: string;
  variant?: 'default' | 'primary' | 'secondary' | 'success' | 'warning' | 'danger';
  disabled?: boolean;
}

interface ActionDropdownProps {
  actions: ActionItem[];
  triggerText?: string;
  triggerIcon?: string;
  className?: string;
  size?: 'sm' | 'md' | 'lg';
  position?: { x: number; y: number } | null;
  isOpen?: boolean;
  onClose?: () => void;
}

const ActionDropdown: React.FC<ActionDropdownProps> = ({
  actions,
  triggerText = 'Actions',
  triggerIcon = '⋮',
  className = '',
  size = 'md',
  position = null,
  isOpen: externalIsOpen,
  onClose
}) => {
  const [internalIsOpen, setInternalIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const [dropdownStyle, setDropdownStyle] = useState<React.CSSProperties>({});

  const isOpen = externalIsOpen !== undefined ? externalIsOpen : internalIsOpen;
  const setIsOpen = externalIsOpen !== undefined ? (open: boolean) => {
    if (!open && onClose) onClose();
  } : setInternalIsOpen;

  useEffect(() => {
    if (isOpen && !position) {
      setTimeout(() => {
        setDropdownStyle(calculateRegularDropdownStyle());
      }, 0);
    }
  }, [isOpen, position]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [setIsOpen]);

  // Calculate dropdown position to avoid going off-screen for regular dropdown
  const calculateRegularDropdownStyle = () => {
    if (!menuRef.current || !dropdownRef.current) {
      return {};
    }

    const triggerRect = dropdownRef.current.getBoundingClientRect();
    const menuRect = menuRef.current.getBoundingClientRect();
    const viewportHeight = window.innerHeight;
    const viewportWidth = window.innerWidth;
    
    // Check if dropdown would go below viewport
    const spaceBelow = viewportHeight - triggerRect.bottom;
    const spaceAbove = triggerRect.top;
    const dropdownHeight = menuRect.height || 200; // Estimate if not available

    // Check if this is likely the last row by looking at the table structure
    const tableRow = dropdownRef.current.closest('tr');
    const tableBody = dropdownRef.current.closest('tbody');
    const isLastRow = tableRow && tableBody && tableRow === tableBody.lastElementChild;

    let style: React.CSSProperties = {};

    // If it's the last row or not enough space below, position above
    if (isLastRow || (spaceBelow < dropdownHeight && spaceAbove > spaceBelow)) {
      style.bottom = '100%';
      style.top = 'auto';
      style.marginBottom = '0.5rem';
      style.marginTop = '0';
    } else {
      style.top = '100%';
      style.bottom = 'auto';
      style.marginTop = '0.5rem';
      style.marginBottom = '0';
    }

    // Check horizontal position
    const spaceRight = viewportWidth - triggerRect.right;
    if (spaceRight < 192) { // 192px is w-48
      style.right = '0';
      style.left = 'auto';
    } else {
      style.right = '0';
      style.left = 'auto';
    }

    return style;
  };

  // Calculate dropdown position to avoid going off-screen
  const calculateDropdownStyle = () => {
    if (!position || !menuRef.current) {
      return {};
    }

    const menuRect = menuRef.current.getBoundingClientRect();
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    
    let left = position.x;
    let top = position.y;

    // Adjust horizontal position if dropdown would go off-screen
    if (left + menuRect.width > viewportWidth) {
      left = viewportWidth - menuRect.width - 10;
    }

    // Adjust vertical position if dropdown would go off-screen
    if (top + menuRect.height > viewportHeight) {
      top = position.y - menuRect.height;
    }

    return {
      position: 'fixed' as const,
      left: `${left}px`,
      top: `${top}px`,
      zIndex: 9999
    };
  };

  const getVariantStyles = (variant: ActionItem['variant']) => {
    switch (variant) {
      case 'primary':
        return 'text-blue-600 hover:text-blue-900 hover:bg-blue-50';
      case 'secondary':
        return 'text-gray-600 hover:text-gray-900 hover:bg-gray-50';
      case 'success':
        return 'text-green-600 hover:text-green-900 hover:bg-green-50';
      case 'warning':
        return 'text-yellow-600 hover:text-yellow-900 hover:bg-yellow-50';
      case 'danger':
        return 'text-red-600 hover:text-red-900 hover:bg-red-50';
      default:
        return 'text-gray-700 hover:text-gray-900 hover:bg-gray-50';
    }
  };

  const getSizeStyles = () => {
    switch (size) {
      case 'sm':
        return 'px-2 py-1 text-xs';
      case 'lg':
        return 'px-4 py-2 text-base';
      default:
        return 'px-3 py-1.5 text-sm';
    }
  };

  const handleActionClick = (action: ActionItem) => {
    if (!action.disabled) {
      setIsOpen(false);
      // Use setTimeout to ensure the dropdown closes before executing the action
      setTimeout(() => {
        action.onClick();
      }, 0);
    }
  };

  const handleTriggerClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsOpen(!isOpen);
  };

  return (
    <div className={`relative inline-block text-left ${className}`} ref={dropdownRef}>
      {/* Trigger Button - only show if no external position */}
      {!position && (
        <button
          onClick={handleTriggerClick}
          className={`inline-flex items-center justify-center rounded-md border border-gray-300 bg-white ${getSizeStyles()} font-medium text-gray-700 shadow-sm hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2`}
        >
          {triggerIcon && <span className="mr-1">{triggerIcon}</span>}
          {triggerText}
          <svg
            className={`ml-1 h-4 w-4 transition-transform ${isOpen ? 'rotate-180' : ''}`}
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path
              fillRule="evenodd"
              d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z"
              clipRule="evenodd"
            />
          </svg>
        </button>
      )}

      {/* Dropdown Menu */}
      {isOpen && (
        <div 
          ref={menuRef}
          className={`${position || (dropdownStyle.position === 'fixed') ? '' : 'absolute'} w-48 origin-top-right rounded-md bg-white shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none`}
          style={position ? calculateDropdownStyle() : { zIndex: 9999, ...dropdownStyle }}
        >
          <div className="py-1">
            {actions.map((action, index) => (
              <button
                key={index}
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  handleActionClick(action);
                }}
                disabled={action.disabled}
                className={`flex w-full items-center text-left ${getSizeStyles()} ${getVariantStyles(action.variant)} ${
                  action.disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'
                } transition-colors duration-200`}
              >
                {action.icon && <span className="mr-2">{action.icon}</span>}
                {action.label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default ActionDropdown; 