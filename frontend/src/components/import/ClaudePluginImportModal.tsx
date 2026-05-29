import { useRef, useState } from 'react';
import { AlertTriangle, Bot, CheckCircle2, Package, Target, Upload } from 'lucide-react';
import Modal from '../ui/Modal';
import Alert from '../ui/Alert';
import { apiService } from '../../services/api';
import type { ClaudePluginImportResponse } from '../../types/import';

interface ClaudePluginImportModalProps {
  appId: number;
  appName?: string;
  isOpen: boolean;
  onClose: () => void;
  onImportComplete?: (result: ClaudePluginImportResponse) => void;
}

function ClaudePluginImportModal({
  appId,
  appName,
  isOpen,
  onClose,
  onImportComplete,
}: Readonly<ClaudePluginImportModalProps>) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isImporting, setIsImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ClaudePluginImportResponse | null>(null);

  function handleClose() {
    if (isImporting) return;
    setSelectedFile(null);
    setError(null);
    setResult(null);
    onClose();
  }

  async function handleImport() {
    if (!selectedFile) return;

    try {
      setIsImporting(true);
      setError(null);
      const response = await apiService.importClaudePlugin(appId, selectedFile);
      setResult(response);
      setSelectedFile(null);
      onImportComplete?.(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to import Claude plugin');
    } finally {
      setIsImporting(false);
    }
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title={`Import Claude Plugin${appName ? ` to ${appName}` : ''}`}
      size="medium"
    >
      <div className="space-y-5">
        {error && (
          <Alert
            type="error"
            message={error}
            onDismiss={() => setError(null)}
          />
        )}

        <div>
          <input
            ref={inputRef}
            type="file"
            accept=".zip,application/zip"
            className="hidden"
            onChange={(event) => {
              setSelectedFile(event.target.files?.[0] ?? null);
              setResult(null);
              setError(null);
            }}
          />
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={isImporting}
            className="w-full border border-dashed border-gray-300 rounded-lg px-4 py-5 text-left hover:border-blue-400 hover:bg-blue-50/40 transition-colors disabled:opacity-60"
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-blue-50 flex items-center justify-center shrink-0">
                <Package className="w-5 h-5 text-blue-600" />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium text-gray-900 truncate">
                  {selectedFile ? selectedFile.name : 'Choose plugin ZIP'}
                </p>
                <p className="text-xs text-gray-500 mt-0.5">
                  {selectedFile
                    ? `${Math.max(1, Math.round(selectedFile.size / 1024))} KB`
                    : 'Claude Code plugin package'}
                </p>
              </div>
            </div>
          </button>
        </div>

        {result && (
          <div className="border border-green-200 bg-green-50 rounded-lg p-4">
            <div className="flex items-start gap-3">
              <CheckCircle2 className="w-5 h-5 text-green-600 shrink-0 mt-0.5" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-green-900">
                  {result.plugin_name || 'Claude plugin'} imported
                </p>
                <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="bg-white/70 border border-green-100 rounded-lg p-3">
                    <div className="flex items-center gap-2 text-sm font-medium text-gray-800">
                      <Target className="w-4 h-4 text-purple-500" />
                      {result.imported_skills.length} skills
                    </div>
                    {result.imported_skills.length > 0 && (
                      <div className="mt-2 space-y-1">
                        {result.imported_skills.map((skill) => (
                          <div key={skill.skill_id} className="text-xs text-gray-600 truncate">
                            {skill.name} {skill.created ? '(new)' : '(updated)'}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="bg-white/70 border border-green-100 rounded-lg p-3">
                    <div className="flex items-center gap-2 text-sm font-medium text-gray-800">
                      <Bot className="w-4 h-4 text-blue-500" />
                      {result.imported_agents.length} agents
                    </div>
                    {result.imported_agents.length > 0 && (
                      <div className="mt-2 space-y-1">
                        {result.imported_agents.map((agent) => (
                          <div key={agent.agent_id} className="text-xs text-gray-600 truncate">
                            {agent.name} {agent.created ? '(new)' : '(updated)'}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {result?.warnings && result.warnings.length > 0 && (
          <div className="border border-amber-200 bg-amber-50 rounded-lg p-4">
            <div className="flex gap-3">
              <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-medium text-amber-900">Import warnings</p>
                <ul className="mt-2 space-y-1">
                  {result.warnings.map((warning, index) => (
                    <li key={`${warning}-${index}`} className="text-xs text-amber-800">
                      {warning}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        )}

        <div className="flex justify-end gap-3 pt-2">
          <button
            type="button"
            onClick={handleClose}
            disabled={isImporting}
            className="px-4 py-2 rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50 disabled:opacity-60"
          >
            {result ? 'Close' : 'Cancel'}
          </button>
          <button
            type="button"
            onClick={() => void handleImport()}
            disabled={!selectedFile || isImporting}
            className="px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60 flex items-center"
          >
            <Upload className="w-4 h-4 mr-2" />
            {isImporting ? 'Importing...' : 'Import Plugin'}
          </button>
        </div>
      </div>
    </Modal>
  );
}

export default ClaudePluginImportModal;
