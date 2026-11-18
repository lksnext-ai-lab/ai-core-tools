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
      className="text-sm text-blue-600 hover:underline dark:text-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded"
    >
      {SERVICE_USAGE_STRINGS.action}
    </button>
  );
}

export default UsedByButton;
