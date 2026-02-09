import { useState, useRef, type ChangeEvent } from 'react';
import Modal from './Modal';
import { FormSelect } from './FormField';
import Alert from './Alert';
import { FormActions } from './FormActions';

interface ImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onImport: (file: File, conflictMode: ConflictMode, newName?: string) => Promise<ImportResponse>;
  componentType: ComponentType;
  componentLabel: string; // e.g., "AI Service", "Embedding Service"
}

export type ConflictMode = 'fail' | 'rename' | 'override';

export type ComponentType = 
  | 'ai_service'
  | 'embedding_service'
  | 'output_parser'
  | 'mcp_config'
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

const CONFLICT_MODE_OPTIONS = [
  { 
    value: 'fail', 
    label: 'Fail on Conflict',
  },
  { 
    value: 'rename', 
    label: 'Rename if Exists',
  },
  { 
    value: 'override', 
    label: 'Override Existing',
  },
];

function ImportModal({
  isOpen,
  onClose,
  onImport,
  componentType,
  componentLabel,
}: ImportModalProps) {
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
      setError('Please select a valid JSON file');
      setSelectedFile(null);
      setFilePreviewName(null);
      return;
    }

    setSelectedFile(file);
    setError(null);
    setImportResult(null);

    // Try to parse and preview the component name
    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const content = JSON.parse(event.target?.result as string);
        // Extract name from metadata or component data
        const name = content.metadata?.name || content[componentType]?.name || 'Unknown';
        setFilePreviewName(name);
      } catch (err) {
        setFilePreviewName(file.name);
      }
    };
    reader.readAsText(file);
  };

  const handleImport = async () => {
    if (!selectedFile) {
      setError('Please select a file to import');
      return;
    }

    if (conflictMode === 'rename' && !newName.trim()) {
      setError('Please provide a new name for rename mode');
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
      setError(err instanceof Error ? err.message : 'Import failed');
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

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title={`Import ${componentLabel}`} size="medium">
      <form onSubmit={(e) => { e.preventDefault(); void handleImport(); }} className="space-y-4">
        {/* File Selection */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Select File <span className="text-red-500">*</span>
          </label>
          <input
            ref={fileInputRef}
            id="import-file"
            type="file"
            accept=".json,application/json"
            onChange={handleFileSelect}
            disabled={importing}
            className="hidden"
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={importing}
            className="border border-gray-300 hover:bg-gray-50 text-gray-700 px-4 py-2 rounded-lg flex items-center disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <span className="mr-2">📁</span>
            {selectedFile ? 'Change File' : 'Select File'}
          </button>
          {filePreviewName && (
            <p className="mt-2 text-sm text-gray-600">
              Component to import: <span className="font-medium">{filePreviewName}</span>
            </p>
          )}
        </div>

        {/* Conflict Resolution Mode */}
        <FormSelect
          label="Conflict Resolution"
          id="conflict-mode"
          value={conflictMode}
          onChange={handleConflictModeChange}
          options={CONFLICT_MODE_OPTIONS}
          disabled={importing}
          required
          helpText={
            conflictMode === 'fail'
              ? 'Import will fail if a component with the same name already exists'
              : conflictMode === 'rename'
              ? 'Component will be imported with a new name if it already exists'
              : 'Existing component will be updated with the imported configuration'
          }
        />

        {/* New Name Input (only for rename mode) */}
        {conflictMode === 'rename' && (
          <div>
            <label htmlFor="new-name" className="block text-sm font-medium text-gray-700 mb-2">
              New Name <span className="text-red-500">*</span>
            </label>
            <input
              id="new-name"
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              disabled={importing}
              placeholder="Enter a new name for the component"
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
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
            title="Import Successful"
            message={importResult.message}
          />
        )}

        {/* Import Summary with Warnings */}
        {importResult?.summary && (
          <div className="space-y-3">
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
              <h4 className="text-sm font-medium text-blue-900 mb-2">Import Summary</h4>
              <ul className="text-sm text-blue-800 space-y-1">
                <li>
                  <strong>Component:</strong> {importResult.summary.component_name}
                </li>
                <li>
                  <strong>Action:</strong> {importResult.summary.created ? 'Created' : 'Updated'}
                </li>
                {importResult.summary.dependencies_created && importResult.summary.dependencies_created.length > 0 && (
                  <li>
                    <strong>Dependencies Created:</strong> {importResult.summary.dependencies_created.join(', ')}
                  </li>
                )}
              </ul>
            </div>

            {/* Warnings */}
            {importResult.summary.warnings && importResult.summary.warnings.length > 0 && (
              <Alert
                type="warning"
                title="Warnings"
                message={
                  <ul className="list-disc list-inside space-y-1">
                    {importResult.summary.warnings.map((warning, idx) => (
                      <li key={idx}>{warning}</li>
                    ))}
                  </ul>
                }
              />
            )}

            {/* Next Steps */}
            {importResult.summary.next_steps && importResult.summary.next_steps.length > 0 && (
              <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
                <h4 className="text-sm font-medium text-gray-900 mb-2">Next Steps</h4>
                <ul className="list-disc list-inside text-sm text-gray-700 space-y-1">
                  {importResult.summary.next_steps.map((step, idx) => (
                    <li key={idx}>{step}</li>
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
          submitLabel={importing ? 'Importing...' : 'Import'}
          cancelLabel={importResult?.success ? 'Close' : 'Cancel'}
          showCancel={!importing}
        />
      </form>
    </Modal>
  );
}

export default ImportModal;
