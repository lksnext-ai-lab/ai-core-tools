import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { FormActions } from '../ui/FormActions';
import { FormCheckbox, FormField, FormTextArea } from '../ui/FormField';
import Alert from '../ui/Alert';
import ButtonApp from '../ui/ButtonApp';
import { apiService } from '../../services/api';

interface MCPConfigFormData {
  name: string;
  description: string;
  config: string;
  ssl_verify: boolean;
}

interface MCPConfig {
  config_id: number;
  name: string;
  description: string;
  config: string;
  ssl_verify?: boolean;
  created_at: string;
}

interface MCPConfigFormProps {
  mcpConfig?: MCPConfig | null;
  onSubmit: (data: MCPConfigFormData) => Promise<void>;
  onCancel: () => void;
}

function MCPConfigForm({ mcpConfig, onSubmit, onCancel }: Readonly<MCPConfigFormProps>) {
  const { appId } = useParams();
  const { t } = useTranslation('common');
  const [formData, setFormData] = useState<MCPConfigFormData>({
    name: '',
    description: '',
    config: '{}',
    ssl_verify: true
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<any>(null);
  const [isTesting, setIsTesting] = useState(false);

  const isEditing = !!mcpConfig && mcpConfig.config_id !== 0;

  // Initialize form with existing config data
  useEffect(() => {
    if (mcpConfig) {
      setFormData({
        name: mcpConfig.name || '',
        description: mcpConfig.description || '',
        config: mcpConfig.config || '{}',
        ssl_verify: mcpConfig.ssl_verify ?? true
      });
    }
  }, [mcpConfig]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));
  };

  const handleTestConnection = async () => {
    if (!appId) return;
    
    // Validate JSON config before testing
    try {
      JSON.parse(formData.config);
    } catch {
      setError(t('mcpConfigsPage.form.invalidJson'));
      return;
    }
    
    setIsTesting(true);
    setTestResult(null);
    setError(null);
    
    try {
      const result = await apiService.testMCPConnectionWithConfig(Number.parseInt(appId), {
        name: formData.name,
        description: formData.description,
        config: formData.config,
        ssl_verify: formData.ssl_verify
      });
      setTestResult(result);
    } catch (err) {
      setTestResult({ status: 'error', message: err instanceof Error ? err.message : t('mcpConfigsPage.form.testFailed') });
    } finally {
      setIsTesting(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    // Basic validation
    if (!formData.name.trim()) {
      setError(t('mcpConfigsPage.form.nameRequired'));
      return;
    }
    
    if (!formData.config.trim()) {
      setError(t('mcpConfigsPage.form.configRequired'));
      return;
    }

    // Validate JSON config
    try {
      JSON.parse(formData.config);
    } catch {
      setError(t('mcpConfigsPage.form.invalidJson'));
      return;
    }

    try {
      setIsSubmitting(true);
      setError(null);
      await onSubmit(formData);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('mcpConfigsPage.form.saveFailed'));
    } finally {
      setIsSubmitting(false);
    }
  };

  const isValid = formData.name.trim() !== '' && formData.config.trim() !== '';

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {error && <Alert type="error" message={error} />}

      {/* Config Name */}
      <FormField
        id="name"
        label={t('mcpConfigsPage.form.configurationName')}
        value={formData.name}
        onChange={handleChange}
        placeholder={t('mcpConfigsPage.form.namePlaceholder')}
        required
      />

      {/* Description */}
      <FormTextArea
        id="description"
        label={t('mcpConfigsPage.form.description')}
        value={formData.description}
        onChange={handleChange}
        rows={2}
        placeholder={t('mcpConfigsPage.form.descriptionPlaceholder')}
      />

      {/* Config JSON */}
      <FormTextArea
        id="config"
        label={t('mcpConfigsPage.form.configurationJson')}
        value={formData.config}
        onChange={handleChange}
        rows={12}
        textareaClassName="font-mono"
        placeholder={'{\n  "playwright": {\n    "command": "npx",\n    "args": ["@playwright/mcp@latest", "--isolated"]\n  }\n}'}
        required
        helpText={t('mcpConfigsPage.form.configurationHelp')}
      />

      {/* SSL Verify */}
      <FormCheckbox
        id="ssl_verify"
        label={t('mcpConfigsPage.form.verifySsl')}
        checked={formData.ssl_verify}
        onChange={(e) =>
          setFormData((prev) => ({ ...prev, ssl_verify: e.target.checked }))
        }
        variant="toggle"
        helpText={t('mcpConfigsPage.form.verifySslHelp')}
      />

      {/* Test Result */}
      {testResult && (
        <Alert
          type={testResult.status === 'success' ? 'success' : 'error'}
          title={testResult.status === 'success' ? t('mcpConfigsPage.form.connectionSuccessful') : t('mcpConfigsPage.form.connectionFailed')}
          message={(
            <>
              {testResult.message}
              {testResult.tools && testResult.tools.length > 0 && (
                <div className="mt-3">
                  <h4 className="text-xs font-semibold uppercase tracking-wider mb-2">{t('mcpConfigsPage.form.availableTools')}</h4>
                  <div className="bg-surface dark:bg-surface-dark rounded border border-success-border dark:border-success-border-dark max-h-40 overflow-y-auto">
                    <table className="min-w-full divide-y divide-line dark:divide-line-dark">
                      <tbody className="divide-y divide-line dark:divide-line-dark">
                        {testResult.tools.map((tool: any) => (
                          <tr key={tool.name}>
                            <td className="px-3 py-2 text-xs font-medium text-fg dark:text-fg-dark">{tool.name}</td>
                            <td className="px-3 py-2 text-xs text-fg-tertiary dark:text-fg-tertiary-dark">{tool.description}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}
        />
      )}

      {/* MCP Info Box */}
      <Alert
        type="info"
        title={t('mcpConfigsPage.form.aboutTitle')}
        message={(
          <div className="text-xs space-y-2">
            <p>
              {t('mcpConfigsPage.form.aboutDescription')}
            </p>
            <p className="font-mono bg-surface-ash dark:bg-surface-hover-dark p-2 rounded text-xs">
              {t('mcpConfigsPage.form.stdioExample')}<br/>
              &#123;"server-name": &#123;"command": "npx", "args": ["package@latest"]&#125;&#125;
            </p>
            <p className="font-mono bg-surface-ash dark:bg-surface-hover-dark p-2 rounded text-xs">
              {t('mcpConfigsPage.form.sseExample')}<br/>
              &#123;"server-name": &#123;"url": "https://server.com", "transport": "sse"&#125;&#125;
            </p>
          </div>
        )}
      />

      <div className="flex justify-between items-center pt-4 border-t border-line dark:border-line-dark">
        <div>
          <ButtonApp
            type="button"
            label={isTesting ? t('mcpConfigsPage.form.testing') : t('mcpConfigsPage.form.testConnection')}
            onClick={handleTestConnection}
            disabled={isTesting || isSubmitting}
            loading={isTesting}
            variant="muted"
            size="medium"
          />
        </div>
        <FormActions
          onCancel={onCancel}
          isSubmitting={isSubmitting}
          isEditing={isEditing}
          submitDisabled={!isValid}
          containerClassName="!border-t-0 !pt-0"
        />
      </div>
    </form>
  );
}

export default MCPConfigForm; 