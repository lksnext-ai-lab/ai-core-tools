import { FormField } from '../ui/FormField';
import Alert from '../ui/Alert';
import {
  MAX_DEPRECATION_NOTICE_LENGTH,
  SERVICE_LIFECYCLE_STRINGS,
  dateInputValueFromIso,
  formatEndOfServiceDate,
  isDateInputRetiredNow,
  serviceOptionLabel,
} from '../../utils/serviceLifecycle';
import type { ServiceOptionLike } from '../../utils/serviceLifecycle';
import type { ServiceKind, ServiceScope } from '../../types/services';

interface ServiceLifecycleInputsProps {
  /** `YYYY-MM-DD` or empty string. */
  readonly date: string;
  readonly notice: string;
  readonly kind: ServiceKind;
  readonly scope: ServiceScope;
  readonly availableAiServices?: readonly ServiceOptionLike[];
  readonly currentServiceId?: number;
  readonly autoMoveTargetServiceId?: string;
  readonly onDateChange: (value: string) => void;
  readonly onNoticeChange: (value: string) => void;
  readonly onAutoMoveTargetChange?: (value: string) => void;
}

/** End-of-service date + deprecation notice inputs shared by the editor and the wizard. */
function ServiceLifecycleInputs({
  date,
  notice,
  kind,
  scope,
  availableAiServices = [],
  currentServiceId,
  autoMoveTargetServiceId = '',
  onDateChange,
  onNoticeChange,
  onAutoMoveTargetChange,
}: Readonly<ServiceLifecycleInputsProps>) {
  const showAutoMove = kind === 'ai' && scope === 'app' && !!date;
  const targetOptions = availableAiServices.filter(
    (service) =>
      service.service_id !== currentServiceId &&
      (service.lifecycle_status !== 'retired' ||
        String(service.service_id) === autoMoveTargetServiceId),
  );

  return (
    <div className="space-y-3 rounded-lg border border-gray-200 dark:border-gray-700 p-3">
      <div className="space-y-2">
        <FormField
                    id="end_of_service_at"
          type="date"
          label={SERVICE_LIFECYCLE_STRINGS.endOfServiceLabel}
          value={date}
          onChange={(e) => {
            onDateChange(e.target.value);
            if (!e.target.value) onAutoMoveTargetChange?.('');
          }}
          helpText={SERVICE_LIFECYCLE_STRINGS.endOfServiceHelp}
        />
        <button
          type="button"
          onClick={() => {
            onDateChange('');
            onAutoMoveTargetChange?.('');
          }}
          disabled={!date}
          aria-label={SERVICE_LIFECYCLE_STRINGS.clearDateAria}
          className="px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {SERVICE_LIFECYCLE_STRINGS.clearDate}
        </button>
      </div>
      {isDateInputRetiredNow(date) && (
        <Alert type="warning" polite message={SERVICE_LIFECYCLE_STRINGS.retireImmediately} />
      )}
      {showAutoMove && (
        <div>
          <label
            htmlFor="auto_move_to_service_id"
            className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-2"
          >
            {SERVICE_LIFECYCLE_STRINGS.autoMoveLabel}
          </label>
          <select
            id="auto_move_to_service_id"
            name="auto_move_to_service_id"
            value={autoMoveTargetServiceId}
            onChange={(e) => onAutoMoveTargetChange?.(e.target.value)}
            aria-describedby="auto_move_to_service_id-help"
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          >
            <option value="">{SERVICE_LIFECYCLE_STRINGS.noAutoMove}</option>
            {targetOptions.map((service) => {
              const targetEndDate = dateInputValueFromIso(service.end_of_service_at);
              const endsTooSoon = !!targetEndDate && targetEndDate <= date;
              const retired = service.lifecycle_status === 'retired';
              const unavailable = endsTooSoon || retired;
              const label = serviceOptionLabel(service);
              return (
                <option
                  key={service.service_id}
                  value={String(service.service_id)}
                  disabled={unavailable}
                >
                  {endsTooSoon
                    ? `${label} ${SERVICE_LIFECYCLE_STRINGS.autoMoveTargetUnavailable(
                        formatEndOfServiceDate(service.end_of_service_at || ''),
                      )}`
                    : label}
                </option>
              );
            })}
          </select>
          <p id="auto_move_to_service_id-help" className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            {targetOptions.length === 0
              ? SERVICE_LIFECYCLE_STRINGS.noAutoMoveTargets
              : SERVICE_LIFECYCLE_STRINGS.autoMoveHelp}
            {targetOptions.length > 0 && (
              <span className="block">{SERVICE_LIFECYCLE_STRINGS.autoMoveTargetHelp}</span>
            )}
          </p>
        </div>
      )}
      <div>
        <label
          htmlFor="deprecation_notice"
          className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-2"
        >
          {SERVICE_LIFECYCLE_STRINGS.deprecationNoticeLabel}
        </label>
        <textarea
          id="deprecation_notice"
          name="deprecation_notice"
          rows={3}
          maxLength={MAX_DEPRECATION_NOTICE_LENGTH}
          value={notice}
          onChange={(e) => onNoticeChange(e.target.value)}
          aria-describedby="deprecation_notice-help deprecation_notice-count"
          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        />
        <div className="mt-1 flex justify-between gap-2 text-sm text-gray-500 dark:text-gray-400">
          <p id="deprecation_notice-help">{SERVICE_LIFECYCLE_STRINGS.deprecationNoticeHelp}</p>
          <p id="deprecation_notice-count">
            {SERVICE_LIFECYCLE_STRINGS.noticeCounter(notice.length, MAX_DEPRECATION_NOTICE_LENGTH)}
          </p>
        </div>
      </div>
    </div>
  );
}

export default ServiceLifecycleInputs;
