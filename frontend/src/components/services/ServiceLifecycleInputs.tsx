import { FormField } from '../ui/FormField';
import Alert from '../ui/Alert';
import {
  MAX_DEPRECATION_NOTICE_LENGTH,
  SERVICE_LIFECYCLE_STRINGS,
  isDateInputRetiredNow,
} from '../../utils/serviceLifecycle';

interface ServiceLifecycleInputsProps {
  /** `YYYY-MM-DD` or empty string. */
  readonly date: string;
  readonly notice: string;
  readonly onDateChange: (value: string) => void;
  readonly onNoticeChange: (value: string) => void;
}

/** End-of-service date + deprecation notice inputs shared by the editor and the wizard. */
function ServiceLifecycleInputs({
  date,
  notice,
  onDateChange,
  onNoticeChange,
}: Readonly<ServiceLifecycleInputsProps>) {
  return (
    <div className="space-y-3 rounded-lg border border-gray-200 dark:border-gray-700 p-3">
      <div className="space-y-2">
        <FormField
                    id="end_of_service_at"
          type="date"
          label={SERVICE_LIFECYCLE_STRINGS.endOfServiceLabel}
          value={date}
          onChange={(e) => onDateChange(e.target.value)}
          helpText={SERVICE_LIFECYCLE_STRINGS.endOfServiceHelp}
        />
        <button
          type="button"
          onClick={() => onDateChange('')}
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
