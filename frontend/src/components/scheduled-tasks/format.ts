import i18n from '../../i18n';
import type { ScheduledTaskRun } from '../../services/api';

type ScheduleTranslator = (
  key: string,
  options?: { count?: number; day?: string; time?: string },
) => string;

function describeScheduleInSpanish(cron: string): string {
  const [minute, hour, dayOfMonth, , dayOfWeek] = cron.trim().split(/\s+/);
  if (minute?.startsWith('*/') && hour === '*') return `Cada ${minute.slice(2)} minutos`;
  if (minute === '0' && hour?.startsWith('*/')) return `Cada ${hour.slice(2)} horas`;
  const time = Number.isInteger(Number(hour)) && Number.isInteger(Number(minute))
    ? `a las ${String(Number(hour)).padStart(2, '0')}:${String(Number(minute)).padStart(2, '0')}`
    : 'en el horario configurado';
  if (dayOfWeek !== '*') return `Semanalmente ${time}`;
  if (dayOfMonth !== '*') return `Mensualmente, el día ${dayOfMonth} ${time}`;
  return `Diariamente ${time}`;
}

function describeLocalizedCalendarSchedule(
  dayOfWeek: string | undefined,
  dayOfMonth: string | undefined,
  time: string | null,
  translate: ScheduleTranslator,
): string {
  if (dayOfWeek !== '*') {
    const key = time ? 'marketplacePage.schedule.weekly' : 'marketplacePage.schedule.weeklyConfigured';
    return translate(key, { time: time ?? '' });
  }
  if (dayOfMonth !== '*') {
    const key = time ? 'marketplacePage.schedule.monthly' : 'marketplacePage.schedule.monthlyConfigured';
    return translate(key, { day: dayOfMonth ?? '', time: time ?? '' });
  }
  const key = time ? 'marketplacePage.schedule.daily' : 'marketplacePage.schedule.dailyConfigured';
  return translate(key, { time: time ?? '' });
}

function describeLocalizedSchedule(cron: string, translate: ScheduleTranslator): string {
  const [minute, hour, dayOfMonth, , dayOfWeek] = cron.trim().split(/\s+/);
  if (minute?.startsWith('*/') && hour === '*') {
    return translate('marketplacePage.schedule.everyMinutes', { count: Number(minute.slice(2)) });
  }
  if (minute === '0' && hour?.startsWith('*/')) {
    return translate('marketplacePage.schedule.everyHours', { count: Number(hour.slice(2)) });
  }
  const time = Number.isInteger(Number(hour)) && Number.isInteger(Number(minute))
    ? `${String(Number(hour)).padStart(2, '0')}:${String(Number(minute)).padStart(2, '0')}`
    : null;
  return describeLocalizedCalendarSchedule(dayOfWeek, dayOfMonth, time, translate);
}

export function describeSchedule(cron: string, translate?: ScheduleTranslator): string {
  return translate
    ? describeLocalizedSchedule(cron, translate)
    : describeScheduleInSpanish(cron);
}

export function conversationModeLabel(mode: string): string {
  return mode === 'continuous' ? 'Conversación continua' : 'Conversación nueva por ejecución';
}

export function formatDateTime(value?: string | null): string {
  return value ? new Date(value).toLocaleString(i18n.resolvedLanguage ?? i18n.language) : '—';
}

export function runDuration(run: ScheduledTaskRun): string | null {
  if (!run.started_at || !run.finished_at) return null;
  const ms = new Date(run.finished_at).getTime() - new Date(run.started_at).getTime();
  if (!Number.isFinite(ms) || ms < 0) return null;
  return ms < 60_000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms / 60_000)} min`;
}

const RUN_STATUS: Record<string, { label: string; className: string }> = {
  succeeded: { label: 'Completada', className: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300' },
  failed: { label: 'Fallida', className: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300' },
  running: { label: 'En ejecución', className: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300' },
  queued: { label: 'En cola', className: 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-200' },
};

export function runStatus(status?: string | null): { label: string; className: string } {
  return RUN_STATUS[status ?? ''] ?? { label: status ?? '—', className: RUN_STATUS.queued.className };
}

/** Plain-text preview of an output: file markers and markdown noise removed. */
export function outputPreview(text?: string | null, max = 160, imageMarker = '[image]'): string {
  if (!text) return '';
  const plain = text
    .split('\n')
    .filter((line) => !/^\s*\|?[\s:|-]+\|?\s*$/.test(line) || !line.includes('-')) // table separators
    .map((line) => line.replace(/^\s*(?:[-*+]|\d+\.)\s+/, '').replace(/\|/g, ' '))
    .join(' ')
    .replace(/!\[[^\]]*\]\(file:\/\/[^)]*\)/g, imageMarker)
    .replace(/\[📎?\s*([^\]]*)\]\(file:\/\/[^)]*\)/g, '[$1]')
    .replace(/[#*_`>]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
  return plain.length > max ? `${plain.slice(0, max)}…` : plain;
}
