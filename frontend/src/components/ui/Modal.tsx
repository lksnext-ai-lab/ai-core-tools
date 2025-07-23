import { type ReactNode } from 'react';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  size?: 'small' | 'medium' | 'large' | 'xlarge';
}

function Modal({ isOpen, onClose, title, children, size = 'large' }: ModalProps) {
  if (!isOpen) return null;

  // Define size classes
  const sizeClasses = {
    small: 'max-w-md max-h-96',
    medium: 'max-w-2xl max-h-[70vh]',
    large: 'max-w-4xl max-h-[80vh]',
    xlarge: 'max-w-6xl max-h-[90vh]'
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      {/* Backdrop */}
      <div 
        className="fixed inset-0 bg-black bg-opacity-50 transition-opacity"
        onClick={onClose}
      />
      
      {/* Modal */}
      <div className="flex min-h-full items-center justify-center p-4">
        <div className={`relative bg-white rounded-lg shadow-xl w-full overflow-hidden ${sizeClasses[size]}`}>
          {/* Header */}
          <div className="flex items-center justify-between p-6 border-b bg-gray-50 sticky top-0 z-10">
            <h3 className="text-lg font-semibold text-gray-900">{title}</h3>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 text-2xl font-bold transition-colors"
            >
              ×
            </button>
          </div>
          
          {/* Content */}
          <div className="p-6 overflow-y-auto" style={{ maxHeight: 'calc(80vh - 88px)' }}>
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}

export default Modal; 