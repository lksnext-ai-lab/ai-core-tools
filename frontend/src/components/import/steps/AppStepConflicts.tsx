import Alert from '../../ui/Alert';
import type { ConflictMode } from '../../../types/import';

interface Props {
  hasConflicts: boolean;
  conflictMode: ConflictMode;
  onConflictModeChange: (mode: ConflictMode) => void;
}

const MODES: Array<{
  value: ConflictMode;
  label: string;
  desc: string;
}> = [
  {
    value: 'fail',
    label: 'Fail on Conflict',
    desc: 'Import will stop if a component name already exists',
  },
  {
    value: 'rename',
    label: 'Rename',
    desc: 'Automatically rename conflicting components',
  },
  {
    value: 'override',
    label: 'Override',
    desc: 'Replace existing component configurations',
  },
];

function AppStepConflicts({
  hasConflicts,
  conflictMode,
  onConflictModeChange,
}: Props) {
  if (!hasConflicts) {
    return (
      <Alert
        type="success"
        message="No conflicts detected. A new app will be created with all selected components."
      />
    );
  }

  return (
    <div className="space-y-4">
      <Alert
        type="warning"
        message="Some component names may conflict with existing ones. Choose a strategy for handling conflicts."
      />

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
              name="app_component_conflict_mode"
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
    </div>
  );
}

export default AppStepConflicts;
