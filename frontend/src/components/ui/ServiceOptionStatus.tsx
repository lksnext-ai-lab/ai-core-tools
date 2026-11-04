import { AlertTriangle, XCircle } from 'lucide-react';
import {
  SERVICE_LIFECYCLE_STRINGS,
  selectableServiceOptions,
  serviceOptionLabel,
  formatEndOfServiceDate,
  type ServiceOptionLike,
} from '../../utils/serviceLifecycle';

interface ServiceOptionStatusProps {
  readonly options: readonly ServiceOptionLike[] | null | undefined;
  /** Currently selected service id (form value). */
  readonly selectedId: number | null | undefined;
  /** Id of the select, used to build the element id (`<id>_lifecycle`). */
  readonly selectId: string;
}

function statusOption(
  options: readonly ServiceOptionLike[] | null | undefined,
  selectedId: number | null | undefined,
): ServiceOptionLike | undefined {
  if (selectedId == null) return undefined;
  const option = options?.find((o) => o.service_id === selectedId);
  return option?.lifecycle_status === 'retired' || option?.lifecycle_status === 'deprecated' ? option : undefined;
}

/** Id of the status line when it renders for the selected option, else undefined (for `aria-describedby`). */
export function serviceStatusId(
  options: readonly ServiceOptionLike[] | null | undefined,
  selectedId: number | null | undefined,
  selectId: string,
): string | undefined {
  return statusOption(options, selectedId) ? `${selectId}_lifecycle` : undefined;
}

interface ServiceSelectOptionsProps<T extends ServiceOptionLike> {
  readonly options: readonly T[] | null | undefined;
  /** Saved value of the loaded entity (D-4): a retired service stays listed only if it matches. */
  readonly savedValue: number | null | undefined;
  /** Custom base label per option (default: the service name). */
  readonly getLabel?: (option: T) => string;
  /** Custom option value (default: the service id). */
  readonly getValue?: (option: T) => string | number;
}

/** `<option>` list for a service select: hides retired services except the saved one and labels the status. */
export function ServiceSelectOptions<T extends ServiceOptionLike>({
  options,
  savedValue,
  getLabel,
  getValue,
}: ServiceSelectOptionsProps<T>) {
  return (
    <>
      {selectableServiceOptions(options, savedValue).map((service) => (
        <option key={service.service_id} value={getValue ? getValue(service) : service.service_id}>
          {serviceOptionLabel(service, getLabel ? getLabel(service) : service.name)}
        </option>
      ))}
    </>
  );
}

/** Small status line under a service select when the selected option is deprecated or retired (D-4). */
export function ServiceOptionStatus({ options, selectedId, selectId }: ServiceOptionStatusProps) {
  const option = statusOption(options, selectedId);
  if (!option) return null;
  const date = option.end_of_service_at ? formatEndOfServiceDate(option.end_of_service_at) : null;
  const retired = option.lifecycle_status === 'retired';
  const Icon = retired ? XCircle : AlertTriangle;
  return (
    <div
      id={`${selectId}_lifecycle`}
      className={`mt-1 flex items-start gap-1 text-xs ${
        retired ? 'text-red-700 dark:text-red-300' : 'text-yellow-800 dark:text-yellow-200'
      }`}
    >
      <Icon className="w-3 h-3 mt-0.5 shrink-0" aria-hidden="true" />
      <span>
        {retired
          ? SERVICE_LIFECYCLE_STRINGS.optionStatusRetired(date)
          : SERVICE_LIFECYCLE_STRINGS.optionStatusDeprecated(date)}
        {option.deprecation_notice ? ` ${option.deprecation_notice}` : ''}
      </span>
    </div>
  );
}
