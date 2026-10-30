import { useTranslation } from 'react-i18next';
import { runStatus } from './format';

export function RunStatusBadge({ status, label }: Readonly<{ status?: string | null; label?: string }>) {
  const { t } = useTranslation('common');
  const statusInfo = runStatus(status);
  const translatedLabel = label ?? t(`scheduledTaskDetailPage.runStatus.${status ?? 'queued'}`, { defaultValue: statusInfo.label });
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusInfo.className}`}>
      {translatedLabel}
    </span>
  );
}
