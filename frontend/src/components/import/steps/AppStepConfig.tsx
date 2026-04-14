import Alert from '../../ui/Alert';
import type { ConflictMode } from '../../../types/import';

interface Props {
  appName: string;
  onAppNameChange: (name: string) => void;
  hasConflict: boolean;
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
    desc: 'Import will be cancelled if name exists',
  },
  {
    value: 'rename',
    label: 'Rename',
    desc: 'Import with the name you specify below',
  },
];

function AppStepConfig({
  appName,
  onAppNameChange,
  hasConflict,
  conflictMode,
  onConflictModeChange,
}: Readonly<Props>) {
  return (
    <div className="space-y-4">
      <div>
        <label
          htmlFor="app-name"
          className="block text-sm font-medium text-gray-700 mb-1"
        >
          App Name
        </label>
        <input
          id="app-name"
          type="text"
          value={appName}
          onChange={(e) => onAppNameChange(e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      {hasConflict && (
        <>
          <Alert
            type="warning"
            message={`An app named "${appName}" already exists. Choose how to handle the conflict.`}
          />
          <div className="space-y-2">
            {MODES.map((m) => (
              <label
                key={m.value}
                aria-label={m.label}
                className={`flex items-start space-x-3 p-3 rounded-lg border cursor-pointer ${
                  conflictMode === m.value
                    ? 'border-blue-400 bg-blue-50'
                    : 'border-gray-200 hover:bg-gray-50'
                }`}
              >
                <input
                  type="radio"
                  name="app_conflict_mode"
                  value={m.value}
                  checked={conflictMode === m.value}
                  onChange={() =>
                    onConflictModeChange(m.value)
                  }
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
        </>
      )}

      {!hasConflict && (
        <Alert
          type="success"
          message="No conflicts detected. This app name is available."
        />
      )}
    </div>
  );
}

export default AppStepConfig;
