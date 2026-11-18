import Alert from '../../ui/Alert';
import { FormRadio } from '../../ui/FormField';
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
          <FormRadio
            key={m.value}
            id={`app-component-conflict-${m.value}`}
            name="app_component_conflict_mode"
            value={m.value}
            checked={conflictMode === m.value}
            onChange={() => onConflictModeChange(m.value)}
            label={t(`importModal.conflict.options.${m.value}`)}
            helpText={t(`importModal.conflict.help.${m.value}`)}
          />
        ))}
      </div>
    </div>
  );
}

export default AppStepConflicts;
