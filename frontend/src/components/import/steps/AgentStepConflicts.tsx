import { Trans, useTranslation } from 'react-i18next';
import Alert from '../../ui/Alert';
import FormField, { FormRadio } from '../../ui/FormField';
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

const MODES: ConflictMode[] = ['fail', 'rename', 'override'];

function AgentStepConflicts({
  preview,
  conflictMode,
  onConflictModeChange,
  newName,
  onNewNameChange,
}: Readonly<Props>) {
  const { t } = useTranslation('common');

  if (!preview.agent.has_conflict) {
    return (
      <Alert
        type="success"
        message={t('importModal.agentConflict.noConflicts')}
      />
    );
  }

  return (
    <div className="space-y-4">
      <Alert
        type="warning"
        message={(
          <Trans
            i18nKey="importModal.agentConflict.conflictWarning"
            values={{ name: preview.agent.component_name }}
            components={{ strong: <strong /> }}
          />
        )}
      /> 

      <div className="space-y-2">
        {MODES.map((mode) => {
          const label = t(`importModal.conflict.options.${mode}`);
          return (
            <FormRadio
              key={mode}
              id={`agent-conflict-${mode}`}
              name="conflict_mode"
              value={mode}
              label={label}
              checked={conflictMode === mode}
              onChange={() => onConflictModeChange(mode)}
              helpText={t(`importModal.conflict.help.${mode}`)}
            />
          );
        })}
      </div>

      {conflictMode === 'rename' && (
        <FormField
          label={t('importModal.newName.label')}
          id="new-agent-name"
          type="text"
          value={newName}
          onChange={(e) => onNewNameChange(e.target.value)}
          placeholder={t('importModal.newName.placeholder')}
        />
      )}
    </div>
  );
}

export default AgentStepConflicts;
