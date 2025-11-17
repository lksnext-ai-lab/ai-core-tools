import { useState, useEffect } from 'react';
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
}: PromptModalProps) {
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

  const tabs = [
    {
      id: 'system' as const,
      label: 'System Prompt',
      description: 'Agent behavior and capabilities',
      icon: '🧠'
    },
    {
      id: 'template' as const,
      label: 'Template Prompt',
      description: 'User interaction template',
      icon: '💬'
    }
  ];

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black bg-opacity-50 transition-opacity" onClick={handleClose}></div>
      
      {/* Modal */}
      <div className="flex min-h-full items-center justify-center p-4">
        <div className="relative bg-white rounded-2xl shadow-xl max-w-4xl w-full max-h-[90vh] overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between p-6 border-b border-gray-200">
            <div>
              <h3 className="text-xl font-semibold text-gray-900">Edit Prompts</h3>
              <p className="text-sm text-gray-600 mt-1">
                {agentName}
              </p>
            </div>
            <button
              onClick={handleClose}
              className="text-gray-400 hover:text-gray-600 transition-colors"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Tab Navigation */}
          <div className="border-b border-gray-200">
            <nav className="flex">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`py-4 px-6 border-b-2 font-medium text-sm transition-colors ${
                    activeTab === tab.id
                      ? 'border-blue-500 text-blue-600 bg-blue-50'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }`}
                >
                  <div className="flex items-center space-x-2">
                    <span>{tab.icon}</span>
                    <span>{tab.label}</span>
                  </div>
                  <div className="text-xs text-gray-400 mt-1">{tab.description}</div>
                </button>
              ))}
            </nav>
          </div>

          {/* Content */}
          <div className="p-6 max-h-[60vh] overflow-y-auto">
            {/* System Prompt Tab */}
            {activeTab === 'system' && (
              <div className="space-y-4">
                <div>
                  <label htmlFor="system_prompt" className="block text-sm font-medium text-gray-700 mb-2">
                    System Prompt
                  </label>
                  <textarea
                    id="system_prompt"
                    value={promptData.system_prompt}
                    onChange={(e) => handlePromptChange('system', e.target.value)}
                    rows={12}
                    className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200 resize-none"
                    placeholder="Define the agent's behavior, capabilities, and personality..."
                  />
                </div>
              </div>
            )}

            {/* Template Prompt Tab */}
            {activeTab === 'template' && (
              <div className="space-y-4">
                <div>
                  <label htmlFor="prompt_template" className="block text-sm font-medium text-gray-700 mb-2">
                    Template Prompt
                  </label>
                  <textarea
                    id="prompt_template"
                    value={promptData.prompt_template}
                    onChange={(e) => handlePromptChange('template', e.target.value)}
                    rows={12}
                    className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200 resize-none"
                    placeholder="Define the template for user interactions..."
                  />
                </div>
              </div>
            )}

            {/* Status Messages */}
            {error && (
              <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
                <div className="flex items-center">
                  <span className="text-red-600 mr-2">⚠️</span>
                  <p className="text-red-800">{error}</p>
                </div>
              </div>
            )}

            {success && (
              <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
                <div className="flex items-center">
                  <span className="text-green-600 mr-2">✅</span>
                  <p className="text-green-800">{success}</p>
                </div>
              </div>
            )}

            {/* Help Text */}
            <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
              <h4 className="text-sm font-medium text-blue-800 mb-2">💡 Tips for Writing Effective Prompts</h4>
              <ul className="text-sm text-blue-700 space-y-1">
                <li>• Be specific about the agent's role and capabilities</li>
                <li>• Include examples of expected behavior</li>
                <li>• Use clear, concise language</li>
                <li>• Test your prompts in the playground to see how they work</li>
                <li>• <strong>Note:</strong> Saving prompts will reset the conversation to test with fresh context</li>
              </ul>
            </div>
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between p-6 border-t border-gray-200 bg-gray-50">
            <div className="text-sm text-gray-500">
              Saving prompts will also reset the conversation for fresh testing
            </div>
            <div className="flex space-x-3">
              <button
                onClick={handleClose}
                className="px-4 py-2 text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
              >
                Close
              </button>
              <button
                onClick={() => savePrompt(activeTab)}
                disabled={saving}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {saving ? 'Saving...' : `Save ${activeTab === 'system' ? 'System' : 'Template'} Prompt`}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default PromptModal;
