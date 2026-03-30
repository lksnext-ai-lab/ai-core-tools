import React from 'react';
import { MessageCircle, X } from 'lucide-react';

interface PlatformChatbotButtonProps {
  onClick: () => void;
  isOpen: boolean;
}

const PlatformChatbotButton: React.FC<PlatformChatbotButtonProps> = ({ onClick, isOpen }) => {
  return (
    <button
      onClick={onClick}
      className="fixed bottom-4 right-4 z-50 w-14 h-14 rounded-full bg-primary text-primary-foreground shadow-lg flex items-center justify-center cursor-pointer hover:scale-105 transition-transform"
      aria-label={isOpen ? 'Close chat' : 'Open chat'}
    >
      {isOpen ? <X size={24} /> : <MessageCircle size={24} />}
    </button>
  );
};

export default PlatformChatbotButton;
