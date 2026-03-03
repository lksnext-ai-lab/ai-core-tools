import { useRef, type ChangeEvent } from 'react';
import Alert from '../../ui/Alert';
import type { AppImportPreview } from '../../../types/import';
import { COMPONENT_TYPE_ICONS } from '../../../types/import';

interface Props {
  file: File | null;
  onFileSelect: (file: File) => void;
  preview: AppImportPreview | null;
  isValidating: boolean;
  validationError: string | null;
}

function AppStepUpload({
  file,
  onFileSelect,
  preview,
  isValidating,
  validationError,
}: Props) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) onFileSelect(f);
  };

  const countRows = preview
    ? [
        {
          icon: COMPONENT_TYPE_ICONS.ai_service,
          label: 'AI Services',
          count: preview.component_counts.ai_services ?? 0,
        },
        {
          icon: COMPONENT_TYPE_ICONS.embedding_service,
          label: 'Embedding Services',
          count:
            preview.component_counts.embedding_services ?? 0,
        },
        {
          icon: COMPONENT_TYPE_ICONS.output_parser,
          label: 'Output Parsers',
          count:
            preview.component_counts.output_parsers ?? 0,
        },
        {
          icon: COMPONENT_TYPE_ICONS.mcp_config,
          label: 'MCP Configs',
          count: preview.component_counts.mcp_configs ?? 0,
        },
        {
          icon: COMPONENT_TYPE_ICONS.silo,
          label: 'Silos',
          count: preview.component_counts.silos ?? 0,
        },
        {
          icon: COMPONENT_TYPE_ICONS.repository,
          label: 'Repositories',
          count:
            preview.component_counts.repositories ?? 0,
        },
        {
          icon: COMPONENT_TYPE_ICONS.domain,
          label: 'Domains',
          count: preview.component_counts.domains ?? 0,
        },
        {
          icon: COMPONENT_TYPE_ICONS.agent,
          label: 'Agents',
          count: preview.component_counts.agents ?? 0,
        },
      ].filter((r) => r.count > 0)
    : [];

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Select App Export File
        </label>
        <input
          ref={fileInputRef}
          type="file"
          accept=".json,application/json"
          onChange={handleFileChange}
          className="hidden"
        />
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={isValidating}
          className="border border-gray-300 hover:bg-gray-50 text-gray-700 px-4 py-2 rounded-lg flex items-center disabled:opacity-50"
        >
          <span className="mr-2">📁</span>
          {file ? 'Change File' : 'Select JSON File'}
        </button>
        {file && (
          <p className="mt-1 text-sm text-gray-500">
            {file.name}
          </p>
        )}
      </div>

      {isValidating && (
        <div className="flex items-center justify-center py-8">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600" />
          <span className="ml-2 text-sm text-gray-600">
            Validating export file...
          </span>
        </div>
      )}

      {validationError && (
        <Alert type="error" message={validationError} />
      )}

      {preview && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 space-y-3">
          <h4 className="text-sm font-medium text-blue-900">
            Export File Summary
          </h4>
          <div className="flex items-center space-x-3">
            <span className="text-2xl">
              {COMPONENT_TYPE_ICONS.app}
            </span>
            <div>
              <p className="font-medium text-blue-900">
                {preview.app_name}
              </p>
              <p className="text-xs text-blue-700">
                Version {preview.export_version}
              </p>
            </div>
          </div>

          {countRows.length > 0 && (
            <div className="border-t border-blue-200 pt-3">
              <p className="text-xs font-medium text-blue-800 mb-2">
                Component Inventory
              </p>
              <div className="grid grid-cols-2 gap-1">
                {countRows.map((r) => (
                  <div
                    key={r.label}
                    className="flex items-center text-sm text-blue-800"
                  >
                    <span className="mr-2">{r.icon}</span>
                    <span>
                      {r.count} {r.label}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {preview.global_warnings.length > 0 && (
            <Alert
              type="warning"
              message={
                <ul className="list-disc list-inside space-y-1">
                  {preview.global_warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              }
            />
          )}
        </div>
      )}
    </div>
  );
}

export default AppStepUpload;
