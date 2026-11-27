import Alert from '../../ui/Alert';
import { FormField, FormRadio } from '../../ui/FormField';
import type { ConflictMode } from '../../../types/import';
import { useTranslation } from 'react-i18next';

interface Props {
  appName: string;
  onAppNameChange: (name: string) => void;
  hasConflict: boolean;
  conflictMode: ConflictMode;
  onConflictModeChange: (mode: ConflictMode) => void;
}

const MODES = [
  {
    value: 'fail',
    labelKey: 'importModal.conflict.options.fail',
    descriptionKey: 'importModal.appConfig.failDescription',
  },
  {
    value: 'rename',
    labelKey: 'importModal.appConfig.rename',
    descriptionKey: 'importModal.appConfig.renameDescription',
  },
] as const;

function AppStepConfig({
  appName,
  onAppNameChange,
  hasConflict,
  conflictMode,
  onConflictModeChange,
}: Readonly<Props>) {
  const { t } = useTranslation('common');

  return (
    <div className="space-y-4">
      <FormField
        id="app-name"
        label={t('appForm.name')}
        type="text"
        value={appName}
        onChange={(e) => onAppNameChange(e.target.value)}
      />

      {hasConflict && (
        <>
          <Alert
            type="warning"
            message={t('importModal.appConfig.conflictWarning', {
              name: appName,
            })}
          /> 
          <div className="space-y-2">
            {MODES.map((m) => (
              <FormRadio
                key={m.value}
                id={`app-conflict-${m.value}`}
                name="app_conflict_mode"
                value={m.value}
                checked={conflictMode === m.value}
                onChange={() => onConflictModeChange(m.value)}
                label={
                  <span className="flex flex-col">
                    <span className="text-sm text-fg dark:text-fg-dark">
                      {t(m.labelKey)}
                    </span>
                    <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
                      {t(m.descriptionKey)}
                    </span>
                  </span>
                }
              />

            ))}
          </div>
        </>
      )}

      {!hasConflict && (
        <Alert
          type="success"
          message={t('importModal.appConfig.noConflict')}
        />
      )}
    </div>
  );
}

export default AppStepConfig;
