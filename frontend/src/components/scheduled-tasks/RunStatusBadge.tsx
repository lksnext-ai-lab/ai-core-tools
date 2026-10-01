import { runStatus } from './format';

export function RunStatusBadge({ status }: Readonly<{ status?: string | null }>) {
  const { label, className } = runStatus(status);
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${className}`}>{label}</span>;
}
