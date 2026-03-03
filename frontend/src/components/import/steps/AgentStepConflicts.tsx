import Alert from '../../ui/Alert';
import type {
  AgentImportPreview,
  ConflictMode,
} from '../../../types/import';

interface Props {
  preview: AgentImportPreview;
  conflictMode: ConflictMode;
  onConflictModeChange: (mode: ConflictMode) => void;
  newName: string;
  onNewNameChange: (name: string) => void;
}

const MODES: Array<{
  value: ConflictMode;
  label: string;
  desc: string;
}> = [
  {
    value: 'fail',
    label: 'Fail on Conflict',
    desc: 'Import will be cancelled if name exists',
  },
  {
    value: 'rename',
    label: 'Rename',
    desc: 'Import with a new name',
  },
  {
    value: 'override',
    label: 'Override',
    desc: 'Replace the existing agent configuration',
  },
];

function AgentStepConflicts({
  preview,
  conflictMode,
  onConflictModeChange,
  newName,
  onNewNameChange,
}: Props) {
  if (!preview.agent.has_conflict) {
    return (
      <Alert
        type="success"
        message='No conflicts detected. The agent name does not exist in this app.'
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
        <p className="text-sm text-amber-900">
          An agent named{' '}
          <strong>"{preview.agent.component_name}"</strong>{' '}
          already exists in this app. Choose how to resolve
          this conflict.
        </p>
      </div>

      <div className="space-y-2">
        {MODES.map((m) => (
          <label
            key={m.value}
            className={`flex items-start space-x-3 p-3 rounded-lg border cursor-pointer ${
              conflictMode === m.value
                ? 'border-blue-400 bg-blue-50'
                : 'border-gray-200 hover:bg-gray-50'
            }`}
          >
            <input
              type="radio"
              name="conflict_mode"
              value={m.value}
              checked={conflictMode === m.value}
              onChange={() => onConflictModeChange(m.value)}
              className="mt-0.5 text-blue-600"
            />
            <div>
              <span className="text-sm font-medium text-gray-900">
                {m.label}
              </span>
              <p className="text-xs text-gray-500">
                {m.desc}
              </p>
            </div>
          </label>
        ))}
      </div>

      {conflictMode === 'rename' && (
        <div>
          <label
            htmlFor="new-agent-name"
            className="block text-sm font-medium text-gray-700 mb-1"
          >
            New Name
          </label>
          <input
            id="new-agent-name"
            type="text"
            value={newName}
            onChange={(e) => onNewNameChange(e.target.value)}
            placeholder="Enter a new name"
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      )}
    </div>
  );
}

export default AgentStepConflicts;
