import { useRef, type ChangeEvent } from 'react';
import { FolderOpen } from 'lucide-react';
import Alert from '../../ui/Alert';
import type { AgentImportPreview } from '../../../types/import';
import {
  COMPONENT_TYPE_ICONS,
} from '../../../types/import';

interface Props {
  file: File | null;
  onFileSelect: (file: File) => void;
  preview: AgentImportPreview | null;
  isValidating: boolean;
  validationError: string | null;
}

function AgentStepUpload({
  file,
  onFileSelect,
  preview,
  isValidating,
  validationError,
}: Readonly<Props>) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) onFileSelect(f);
  };

  type InventoryItem = { label: string; icon: string; name: string };

  const inventoryItems = (
    preview
      ? [
          preview.ai_service && {
            label: 'AI Service',
            icon: COMPONENT_TYPE_ICONS.ai_service,
            name: preview.ai_service.component_name,
          },
          preview.silo && {
            label: 'Silo',
            icon: COMPONENT_TYPE_ICONS.silo,
            name: preview.silo.component_name,
          },
          preview.output_parser && {
            label: 'Output Parser',
            icon: COMPONENT_TYPE_ICONS.output_parser,
            name: preview.output_parser.component_name,
          },
          preview.mcp_configs.length > 0 && {
            label: `MCP Configs (${preview.mcp_configs.length})`,
            icon: COMPONENT_TYPE_ICONS.mcp_config,
            name: preview.mcp_configs
              .map((m) => m.component_name)
              .join(', '),
          },
          preview.agent_tools.length > 0 && {
            label: `Agent Tools (${preview.agent_tools.length})`,
            icon: COMPONENT_TYPE_ICONS.agent,
            name: preview.agent_tools
              .map((t) => t.component_name)
              .join(', '),
          },
        ]
      : []
  ).filter((item): item is InventoryItem => Boolean(item));

  return (
    <div className="space-y-4">
      <div>
        <label
          htmlFor="agent-export-file-input"
          className="block text-sm font-medium text-gray-700 mb-2"
        >
          Select Export File
        </label>
        <input
          ref={fileInputRef}
          id="agent-export-file-input"
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
          <FolderOpen className="w-5 h-5 mr-2" />
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
              {COMPONENT_TYPE_ICONS.agent}
            </span>
            <div>
              <p className="font-medium text-blue-900">
                {preview.agent.component_name}
              </p>
              <p className="text-xs text-blue-700">
                Version {preview.export_version}
              </p>
            </div>
          </div>

          {inventoryItems.length > 0 && (
            <div className="border-t border-blue-200 pt-3">
              <p className="text-xs font-medium text-blue-800 mb-2">
                Bundled Components
              </p>
              <div className="space-y-1">
                {inventoryItems.map((item) => (
                  <div
                    key={item.label}
                    className="flex items-center text-sm text-blue-800"
                  >
                    <span className="mr-2">{item.icon}</span>
                    <span className="font-medium mr-1">
                      {item.label}:
                    </span>
                    <span>{item.name}</span>
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
                  {preview.global_warnings.map((w) => (
                    <li key={w}>{w}</li>
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

export default AgentStepUpload;
