import { useState, useEffect, type ReactNode } from 'react';
import { Brain, MessageCircle } from 'lucide-react';
import Alert from '../ui/Alert';
import { ButtonApp } from '../ui/ButtonApp';
import { FormTextArea } from '../ui/FormField';
import Modal from '../ui/Modal';
import { Tabs } from '../ui/Tabs';
import { apiService } from '../../services/api';

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
      
      setSuccess(`${type === 'system' ? 'System' : 'Template'} prompt updated and conversation reset!`);
      
      // Call the callback to refresh agent data if needed
      if (onPromptUpdate) {
        onPromptUpdate();
      }

      // Clear success message after 3 seconds (longer since we're doing more)
      setTimeout(() => setSuccess(null), 3000);
      setError(null);
      onClose(); // Close the modal after successful save
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update prompt');
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
      label: 'System Prompt',
      description: 'Agent behavior and capabilities',
      icon: <Brain className="w-4 h-4" />
    },
    {
      id: 'template' as const,
      label: 'Template Prompt',
      description: 'User interaction template',
      icon: <MessageCircle className="w-4 h-4" />
    }
  ];

  const promptTypeLabel = activeTab === 'system' ? 'System' : 'Template';
  const saveLabel = saving ? 'Saving...' : `Save ${promptTypeLabel} Prompt`;

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Edit Prompts" subtitle={agentName} size="large">
      <Tabs tabs={tabs} activeTab={activeTab} onChange={(tabId) => setActiveTab(tabId as 'system' | 'template')} className="-mx-6 mb-6 px-6" />

      {activeTab === 'system' && (
        <div className="space-y-4">
          <FormTextArea
            label="System Prompt"
            id="system_prompt"
            value={promptData.system_prompt}
            onChange={(e) => handlePromptChange('system', e.target.value)}
            rows={12}
            placeholder="Define the agent's behavior, capabilities, and personality..."
          />
        </div>
      )}

      {activeTab === 'template' && (
        <div className="space-y-4">
          <FormTextArea
            label="Template Prompt"
            id="prompt_template"
            value={promptData.prompt_template}
            onChange={(e) => handlePromptChange('template', e.target.value)}
            rows={12}
            placeholder="Define the template for user interactions..."
          />
        </div>
      )}

      {error && <Alert type="error" message={error} />}
      {success && <Alert type="success" message={success} />}

      <Alert
        type="info"
        title="Tips for Writing Effective Prompts"
        message={(
          <ul className="space-y-1">
            <li>• Be specific about the agent's role and capabilities</li>
            <li>• Include examples of expected behavior</li>
            <li>• Use clear, concise language</li>
            <li>• Test your prompts in the playground to see how they work</li>
            <li>• <strong>Note:</strong> Saving prompts will reset the conversation to test with fresh context</li>
          </ul>
        )}
      />

      <div className="mt-6 flex flex-col gap-4 border-t border-line pt-6 dark:border-line-dark sm:flex-row sm:items-center sm:justify-between">
        <div className="text-sm text-fg-secondary dark:text-fg-secondary-dark">
          Saving prompts will also reset the conversation for fresh testing
        </div>
        <div className="flex justify-end gap-3">
          <ButtonApp label="Close" onClick={handleClose} variant="secondary" size="medium" />
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
