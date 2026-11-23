import React from 'react';
import { MessageCircle, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface PlatformChatbotButtonProps {
  readonly onClick: () => void;
  readonly isOpen: boolean;
}

const PlatformChatbotButton: React.FC<PlatformChatbotButtonProps> = ({ onClick, isOpen }) => {
  const { t } = useTranslation('common');
  const label = isOpen ? t('platformChatbot.close') : t('platformChatbot.open');

  return (
    <button
      type="button"
      onClick={onClick}
      className="fixed bottom-4 right-4 z-50 w-14 h-14 rounded-full bg-surface dark:bg-surface-dark text-fg dark:text-fg-dark border border-line-strong dark:border-line-strong-dark flex items-center justify-center cursor-pointer hover:scale-105 transition-transform"
      aria-label={label}
      aria-expanded={isOpen}
    >
      {isOpen ? <X size={24} aria-hidden="true" /> : <MessageCircle size={24} aria-hidden="true" />}
    </button>
  );
};

export default PlatformChatbotButton;
