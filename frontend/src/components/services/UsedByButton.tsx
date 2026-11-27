import { ArrowUpRight } from 'lucide-react';
import { SERVICE_USAGE_STRINGS } from '../../utils/serviceLifecycle';

export interface UsedByButtonProps {
  readonly serviceName: string;
  readonly onClick: () => void;
}

function UsedByButton({ serviceName, onClick }: Readonly<UsedByButtonProps>) {
  return (
    <button
      type="button"
      aria-label={`${SERVICE_USAGE_STRINGS.action}: ${serviceName}`}
      onClick={onClick}
      className="inline-flex items-center gap-1 whitespace-nowrap text-xs text-bronze dark:text-bronze-dark"
    >
      {SERVICE_USAGE_STRINGS.action}
      <ArrowUpRight className="w-4 h-4 " aria-hidden="true" />
    </button>
  );
}

export default UsedByButton;
