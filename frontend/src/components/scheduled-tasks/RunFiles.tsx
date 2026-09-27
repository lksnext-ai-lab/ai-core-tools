import { FileText } from 'lucide-react';
import InlineFileDownload from '../playground/InlineFileDownload';
import type { ScheduledTaskRun } from '../../services/api';
import { formatDateTime } from './format';

interface Props {
  runs: ScheduledTaskRun[];
  resolveFileUrl: (runId: number, fileId: string) => Promise<string>;
  /** Label each file with the run that produced it (continuous conversations). */
  showRunDate?: boolean;
}

/** Download block for the files produced by one or several runs. */
export function RunFiles({ runs, resolveFileUrl, showRunDate = false }: Readonly<Props>) {
  const files = runs.flatMap((run) => (run.output_files ?? []).map((file) => ({ run, file })));
  return (
    <section className="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-800">
      <h2 className="mb-3 flex items-center gap-2 text-base font-semibold text-gray-900 dark:text-gray-100">
        <FileText className="h-4 w-4 text-blue-600" aria-hidden="true" />
        Archivos generados
      </h2>
      {files.length === 0 ? (
        <p className="text-sm text-gray-500 dark:text-gray-400">Esta ejecución no generó archivos.</p>
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
                <span className="text-xs text-gray-500 dark:text-gray-400">{formatDateTime(run.scheduled_time)}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
