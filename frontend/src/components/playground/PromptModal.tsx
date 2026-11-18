import { useState, useEffect, type ReactNode } from 'react';
import { Brain, MessageCircle } from 'lucide-react';
import Alert from '../ui/Alert';
import { ButtonApp } from '../ui/ButtonApp';
import { FormTextArea } from '../ui/FormField';
import Modal from '../ui/Modal';
import { Tabs } from '../ui/Tabs';
import { apiService } from '../../services/api';
import { useTranslation } from 'react-i18next';

interface PromptModalProps {
  isOpen: boolean;
  onClose: () => void;
  appId: number;
  agentId: number;
  agentName: string;
  initialSystemPrompt?: string;
  initialPromptTemplate?: string;
  onPromptUpdate?: () => void;
}

interface PromptData {
  system_prompt: string;
  prompt_template: string;
}

function PromptModal({ 
  isOpen, 
  onClose, 
  appId, 
  agentId, 
  agentName, 
  initialSystemPrompt = '', 
  initialPromptTemplate = '',
  onPromptUpdate 
}: Readonly<PromptModalProps>) {
  const { t } = useTranslation('common');
  const [promptData, setPromptData] = useState<PromptData>({
    system_prompt: initialSystemPrompt,
    prompt_template: initialPromptTemplate
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'system' | 'template'>('system');

  useEffect(() => {
    if (isOpen) {
      setPromptData({
        system_prompt: initialSystemPrompt,
        prompt_template: initialPromptTemplate
      });
      setError(null);
      setSuccess(null);
    }
  }, [isOpen, initialSystemPrompt, initialPromptTemplate]);

  const handlePromptChange = (type: 'system' | 'template', value: string) => {
    setPromptData(prev => ({
      ...prev,
      [type === 'system' ? 'system_prompt' : 'prompt_template']: value
    }));
  };

  const savePrompt = async (type: 'system' | 'template') => {
    try {
      setSaving(true);
      setError(null);
      setSuccess(null);

      const promptValue = type === 'system' ? promptData.system_prompt : promptData.prompt_template;
      
      // Update the prompt
      await apiService.updateAgentPrompt(appId, agentId, type, promptValue);
      
      // Reset the conversation since prompts have changed
      try {
        await apiService.resetAgentConversation(appId, agentId);
      } catch (resetError) {
        console.warn('Failed to reset conversation after prompt update:', resetError);
        // Don't fail the whole operation if reset fails
      }
      
      const promptType = type === 'system'
        ? t('agentFormPage.prompts.systemPrompt')
        : t('agentFormPage.prompts.template');
      setSuccess(t('promptModal.updated', { promptType }));
      
      // Call the callback to refresh agent data if needed
      if (onPromptUpdate) {
        onPromptUpdate();
      }

      // Clear success message after 3 seconds (longer since we're doing more)
      setTimeout(() => setSuccess(null), 3000);
      setError(null);
      onClose(); // Close the modal after successful save
    } catch (err) {
      setError(err instanceof Error ? err.message : t('promptModal.updateFailed'));
      console.error('Error updating prompt:', err);
    } finally {
      setSaving(false);
    }
  };

  const handleClose = () => {
    setError(null);
    setSuccess(null);
    onClose();
  };

  const tabs: Array<{ id: 'system' | 'template'; label: string; description: string; icon: ReactNode }> = [
    {
      id: 'system' as const,
      label: t('agentFormPage.prompts.systemPrompt'),
      description: t('promptModal.systemDescription'),
      icon: <Brain className="w-4 h-4" />
    },
    {
      id: 'template' as const,
      label: t('agentFormPage.prompts.template'),
      description: t('promptModal.templateDescription'),
      icon: <MessageCircle className="w-4 h-4" />
    }
  ];

  const saveLabel = saving
    ? t('agentFormPage.saving.inProgress')
    : activeTab === 'system'
      ? t('promptModal.saveSystemPrompt')
      : t('promptModal.saveTemplatePrompt');

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title={t('agentPlayground.editPrompts')} subtitle={agentName} size="large">
      <Tabs tabs={tabs} activeTab={activeTab} onChange={(tabId) => setActiveTab(tabId as 'system' | 'template')} className="-mx-6 mb-6 px-6" />

      {activeTab === 'system' && (
        <div className="space-y-4">
          <FormTextArea
            label={t('agentFormPage.prompts.systemPrompt')}
            id="system_prompt"
            value={promptData.system_prompt}
            onChange={(e) => handlePromptChange('system', e.target.value)}
            rows={12}
            placeholder={t('agentFormPage.prompts.systemPromptPlaceholder')}
          />
        </div>
      )}

      {activeTab === 'template' && (
        <div className="space-y-4">
          <FormTextArea
            label={t('agentFormPage.prompts.template')}
            id="prompt_template"
            value={promptData.prompt_template}
            onChange={(e) => handlePromptChange('template', e.target.value)}
            rows={12}
            placeholder={t('promptModal.templatePlaceholder')}
          />
        </div>
      )}

      {error && <Alert type="error" message={error} />}
      {success && <Alert type="success" message={success} />}

      <Alert
        type="info"
        title={t('promptModal.tipsTitle')}
        message={(
          <ul className="space-y-1">
            <li>• {t('promptModal.tipSpecific')}</li>
            <li>• {t('promptModal.tipExamples')}</li>
            <li>• {t('promptModal.tipClear')}</li>
            <li>• {t('promptModal.tipTest')}</li>
            <li>• <strong>{t('promptModal.note')}:</strong> {t('promptModal.conversationResetNotice')}</li>
          </ul>
        )}
      />

      <div className="mt-6 flex flex-col gap-4 border-t border-line pt-6 dark:border-line-dark sm:flex-row sm:items-center sm:justify-between">
        <div className="text-sm text-fg-secondary dark:text-fg-secondary-dark">
          {t('promptModal.conversationResetNotice')}
        </div>
        <div className="flex justify-end gap-3">
          <ButtonApp label={t('promptModal.close')} onClick={handleClose} variant="secondary" size="medium" />
          <ButtonApp
            label={saveLabel}
            onClick={() => savePrompt(activeTab)}
            disabled={saving}
            variant="primary"
            size="medium"
          />
        </div>
      </div>
    </Modal>
  );
}

export default PromptModal;
