import React from 'react';
import { usePlatformChatbot } from '../../contexts/PlatformChatbotContext';
import PlatformChatbotButton from './PlatformChatbotButton';
import PlatformChatbotPanel from './PlatformChatbotPanel';

const PlatformChatbotWidget: React.FC = () => {
  const { config, isConfigLoading, isOpen, openChat, closeChat, startNewConversation } =
    usePlatformChatbot();

  // Don't render anything while loading or when chatbot is disabled
  if (isConfigLoading || !config?.enabled) {
    return null;
  }

  return (
    <>
      {isOpen && (
        <PlatformChatbotPanel
          agentName={config.agent_name}
          onClose={closeChat}
          onNewConversation={startNewConversation}
        />
      )}
      <PlatformChatbotButton
        onClick={isOpen ? closeChat : openChat}
        isOpen={isOpen}
      />
    </>
  );
};

export default PlatformChatbotWidget;
