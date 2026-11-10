import Alert from '../../ui/Alert';
import { FormField } from '../../ui/FormField';
import { useTranslation } from 'react-i18next';
import type { ConflictMode } from '../../../types/import';

interface Props {
  hasConflicts: boolean;
  conflictMode: ConflictMode;
  onConflictModeChange: (mode: ConflictMode) => void;
}

const MODES: Array<{
  value: ConflictMode;
}> = [
  { value: 'fail' },
  { value: 'rename' },
  { value: 'override' },
];

function AppStepConflicts({
  hasConflicts,
  conflictMode,
  onConflictModeChange,
}: Readonly<Props>) {
  const { t } = useTranslation('common');

  if (!hasConflicts) {
    return (
      <Alert
        type="success"
        message={t('importModal.appConflicts.noConflicts')}
      />
    );
  }

  return (
    <div className="space-y-4">
      <Alert
        type="warning"
        message={t('importModal.appConflicts.conflictWarning')}
      />

      <div className="space-y-2">
        {MODES.map((m) => (
          <FormField
            key={m.value}
            id={`app-component-conflict-${m.value}`}
            type="radio"
            name="app_component_conflict_mode"
            value={m.value}
            checked={conflictMode === m.value}
            onChange={() => onConflictModeChange(m.value)}
            label={t(`importModal.conflict.options.${m.value}`)}
            helpText={t(`importModal.conflict.help.${m.value}`)}
            className="grid grid-cols-[auto_minmax(0,1fr)] items-start gap-x-3 [&>p]:col-start-2"
          />
        ))}
      </div>
    </div>
  );
}

export default AppStepConflicts;
