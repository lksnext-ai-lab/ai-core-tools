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
}

const ActionDropdown: React.FC<ActionDropdownProps> = ({
  actions,
  triggerText = 'Actions',
  triggerIcon = '⋮',
  className = '',
  size = 'md'
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

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
      action.onClick();
      setIsOpen(false);
    }
  };

  return (
    <div className={`relative inline-block text-left ${className}`} ref={dropdownRef}>
      {/* Trigger Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
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

      {/* Dropdown Menu */}
      {isOpen && (
        <div className="absolute right-0 z-10 mt-2 w-48 origin-top-right rounded-md bg-white shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none">
          <div className="py-1">
            {actions.map((action, index) => (
              <button
                key={index}
                onClick={() => handleActionClick(action)}
                disabled={action.disabled}
                className={`flex w-full items-center ${getSizeStyles()} ${getVariantStyles(action.variant)} ${
                  action.disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'
                }`}
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