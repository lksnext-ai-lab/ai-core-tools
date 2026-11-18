import { FileText } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import InlineFileDownload from '../playground/InlineFileDownload';
import type { ScheduledTaskRun } from '../../services/api';
import { formatDateTime } from './format';
import { CardApp } from '../ui/CardApp';

interface Props {
  runs: ScheduledTaskRun[];
  resolveFileUrl: (runId: number, fileId: string) => Promise<string>;
  /** Label each file with the run that produced it (continuous conversations). */
  showRunDate?: boolean;
}

/** Download block for the files produced by one or several runs. */
export function RunFiles({ runs, resolveFileUrl, showRunDate = false }: Readonly<Props>) {
  const { t } = useTranslation('common');
  const files = runs.flatMap((run) => (run.output_files ?? []).map((file) => ({ run, file })));
  return (
    <CardApp icon={FileText} titulo={t('scheduledTaskDetailPage.results.generatedFiles')}>
      {files.length === 0 ? (
        <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">{t('scheduledTaskDetailPage.results.noGeneratedFiles')}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {files.map(({ run, file }) => (
            <li key={`${run.id}-${file.file_id}`} className="flex min-w-0 flex-wrap items-center gap-3">
              <InlineFileDownload
                fileId={file.file_id}
                filename={file.filename}
                resolveUrl={(fileId) => resolveFileUrl(run.id, fileId)}
              />
              {showRunDate && (
                <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark">{formatDateTime(run.scheduled_time)}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </CardApp>
  );
}
