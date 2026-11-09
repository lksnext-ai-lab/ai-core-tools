import { useState, useRef, type ChangeEvent } from 'react';
import { useTranslation } from 'react-i18next';
import Modal from './Modal';
import { FormField, FormSelect } from './FormField';
import Alert from './Alert';
import { FormActions } from './FormActions';
import {
  selectableServiceOptions,
  serviceOptionLabel,
  type ServiceOptionLike,
} from '../../utils/serviceLifecycle';

interface ImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onImport: (file: File, conflictMode: ConflictMode, newName?: string) => Promise<ImportResponse>;
  componentType: ComponentType;
  componentLabel: string; // e.g., "AI Service", "Embedding Service"
  // Optional: For silo imports that need embedding service selection
  requiresEmbeddingServiceSelection?: boolean;
  availableEmbeddingServices?: readonly ServiceOptionLike[];
  selectedEmbeddingServiceId?: number;
  onEmbeddingServiceChange?: (id: number) => void;
}

export type ConflictMode = 'fail' | 'rename' | 'override';

export type ComponentType = 
  | 'ai_service'
  | 'embedding_service'
  | 'output_parser'
  | 'mcp_config'
  | 'middleware'
  | 'silo'
  | 'repository'
  | 'agent'
  | 'app';

export interface ImportResponse {
  success: boolean;
  message: string;
  summary?: {
    component_type: string;
    component_id: number;
    component_name: string;
    mode: ConflictMode;
    created: boolean;
    dependencies_created?: string[];
    warnings?: string[];
    next_steps?: string[];
  };
}

function ImportModal({
  isOpen,
  onClose,
  onImport,
  componentType,
  componentLabel,
  requiresEmbeddingServiceSelection = false,
  availableEmbeddingServices = [],
  selectedEmbeddingServiceId,
  onEmbeddingServiceChange,
}: Readonly<ImportModalProps>) {
  const { t } = useTranslation('common');
  const conflictModeOptions = [
    { value: 'fail', label: t('importModal.conflict.options.fail') },
    { value: 'rename', label: t('importModal.conflict.options.rename') },
    { value: 'override', label: t('importModal.conflict.options.override') },
  ];
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [conflictMode, setConflictMode] = useState<ConflictMode>('fail');
  const [newName, setNewName] = useState('');
  const [filePreviewName, setFilePreviewName] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [importResult, setImportResult] = useState<ImportResponse | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Validate file type
    if (!file.name.endsWith('.json')) {
      setError(t('importModal.errors.invalidJsonFile'));
      setSelectedFile(null);
      setFilePreviewName(null);
      return;
    }

    setSelectedFile(file);
    setError(null);
    setImportResult(null);

    // Try to parse and preview the component name
    void file.text().then((text) => {
      try {
        const content = JSON.parse(text) as Record<string, { name?: string }>;
        const name = content.metadata?.name ?? content[componentType]?.name ?? t('importModal.unknown');
        setFilePreviewName(name);
      } catch {
        setFilePreviewName(file.name);
      }
    }).catch(() => {
      setFilePreviewName(file.name);
    });
  };

  const handleImport = async () => {
    if (!selectedFile) {
      setError(t('importModal.errors.selectFileRequired'));
      return;
    }

    if (conflictMode === 'rename' && !newName.trim()) {
      setError(t('importModal.errors.renameRequiresName'));
      return;
    }

    setImporting(true);
    setError(null);
    setImportResult(null);

    try {
      const result = await onImport(
        selectedFile,
        conflictMode,
        conflictMode === 'rename' ? newName : undefined
      );

      // Parent component handles success (closing modal + notification)
      // We only set the result for error cases or warnings
      if (!result.success || (result.summary?.warnings && result.summary.warnings.length > 0)) {
        setImportResult(result);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t('importModal.errors.importFailed'));
    } finally {
      setImporting(false);
    }
  };

  const handleClose = () => {
    if (importing) return;
    
    setSelectedFile(null);
    setConflictMode('fail');
    setNewName('');
    setFilePreviewName(null);
    setError(null);
    setImportResult(null);
    
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
    
    onClose();
  };

  const handleConflictModeChange = (e: ChangeEvent<HTMLSelectElement>) => {
    const mode = e.target.value as ConflictMode;
    setConflictMode(mode);
    if (mode !== 'rename') {
      setNewName('');
    }
  };

  let conflictModeHelpText: string;
  if (conflictMode === 'fail') {
    conflictModeHelpText = t('importModal.conflict.help.fail');
  } else if (conflictMode === 'rename') {
    conflictModeHelpText = t('importModal.conflict.help.rename');
  } else {
    conflictModeHelpText = t('importModal.conflict.help.override');
  }

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title={t('importModal.title', { component: componentLabel })} size="medium">
      <form onSubmit={(e) => { e.preventDefault(); void handleImport(); }} className="space-y-4">
        <div>
          <FormField
            ref={fileInputRef}
            id="import-file"
            type="file"
            label={<>{t('importModal.file.select')} <span className="text-red-500">*</span></>}
            accept=".json,application/json"
            onChange={handleFileSelect}
            disabled={importing}
            helpText={filePreviewName ? (
              <>{t('importModal.file.componentToImport')}: <span className="font-medium">{filePreviewName}</span></>
            ) : undefined}
            helpTextAriaLive="polite"
          />
        </div>

        {/* Conflict Resolution Mode */}
        <FormSelect
          label={t('importModal.conflict.label')}
          id="conflict-mode"
          value={conflictMode}
          onChange={handleConflictModeChange}
          options={conflictModeOptions}
          disabled={importing}
          required
          helpText={conflictModeHelpText}
        />

        {/* New Name Input (only for rename mode) */}
        {conflictMode === 'rename' && (
          <FormField
            id="new-name"
            label={t('importModal.newName.label')}
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            disabled={importing}
            placeholder={t('importModal.newName.placeholder')}
            required
          />
        )}

        {/* Embedding Service Selection (for silos without bundled service) */}
        {requiresEmbeddingServiceSelection && (
          <div className="space-y-3">
            <Alert
              type="warning"
              message={t('importModal.embedding.warning')}
            />
            <FormSelect
              label={t('importModal.embedding.label')}
              id="embedding-service-select"
              value={selectedEmbeddingServiceId?.toString() || ''}
              onChange={(e) => {
                const id = Number.parseInt(e.target.value, 10);
                if (onEmbeddingServiceChange && !Number.isNaN(id)) {
                  onEmbeddingServiceChange(id);
                }
              }}
              options={[
                { value: '', label: t('importModal.embedding.select') },
                ...selectableServiceOptions(availableEmbeddingServices, undefined).map((svc) => ({
                  value: svc.service_id.toString(),
                  label: serviceOptionLabel(svc),
                })),
              ]}
              disabled={importing}
              required
              helpText={t('importModal.embedding.help')}
            />
          </div>
        )}

        {/* Error Display */}
        {error && (
          <Alert type="error" message={error} onDismiss={() => setError(null)} />
        )}

        {/* Success Result */}
        {importResult?.success && (
          <Alert
            type="success"
            title={t('importModal.result.success')}
            message={importResult.message}
          />
        )}

        {/* Import Summary with Warnings */}
        {importResult?.summary && (
          <div className="space-y-3">
            <Alert
              type="info"
              title={t('importModal.result.summary')}
              message={(
                <ul className="space-y-1">
                  <li>
                    <strong>{t('importModal.result.component')}:</strong> {importResult.summary.component_name}
                  </li>
                  <li>
                    <strong>{t('importModal.result.action')}:</strong> {importResult.summary.created ? t('importModal.result.created') : t('importModal.result.updated')}
                  </li>
                  {importResult.summary.dependencies_created && importResult.summary.dependencies_created.length > 0 && (
                    <li>
                      <strong>{t('importModal.result.dependenciesCreated')}:</strong> {importResult.summary.dependencies_created.join(', ')}
                    </li>
                  )}
                </ul>
              )}
            />

            {/* Warnings */}
            {importResult.summary.warnings && importResult.summary.warnings.length > 0 && (
              <Alert
                type="warning"
                title={t('importModal.result.warnings')}
                message={
                  <ul className="list-disc list-inside space-y-1">
                    {importResult.summary.warnings.map((warning) => (
                      <li key={warning}>{warning}</li>
                    ))}
                  </ul>
                }
              />
            )}

            {/* Next Steps */}
            {importResult.summary.next_steps && importResult.summary.next_steps.length > 0 && (
              <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
                <h4 className="text-sm font-medium text-gray-900 mb-2">{t('importModal.result.nextSteps')}</h4>
                <ul className="list-disc list-inside text-sm text-gray-700 space-y-1">
                  {importResult.summary.next_steps.map((step) => (
                    <li key={step}>{step}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {/* Actions */}
        <FormActions
          onCancel={handleClose}
          isSubmitting={importing}
          submitLabel={t('importModal.actions.import')}
          submittingLabel={t('importModal.actions.importing')}
          cancelLabel={importResult?.success ? t('importModal.actions.close') : t('importModal.actions.cancel')}
          showCancel={!importing}
          submitDisabled={!selectedFile || (requiresEmbeddingServiceSelection && !selectedEmbeddingServiceId)}
        />
      </form>
    </Modal>
  );
}

export default ImportModal;
