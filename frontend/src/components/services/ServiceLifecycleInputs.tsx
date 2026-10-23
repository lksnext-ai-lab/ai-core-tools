import { FormField, FormTextArea } from '../ui/FormField';
import Alert from '../ui/Alert';
import { ButtonApp } from '../ui/ButtonApp';
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
        <ButtonApp
          label={SERVICE_LIFECYCLE_STRINGS.clearDate}
          type="button"
          onClick={() => onDateChange('')}
          disabled={!date}
          ariaLabel={SERVICE_LIFECYCLE_STRINGS.clearDateAria}
          variant="muted"
          size="medium"
        />
      </div>
      {isDateInputRetiredNow(date) && (
        <Alert type="warning" polite message={SERVICE_LIFECYCLE_STRINGS.retireImmediately} />
      )}
      <div>
        <FormTextArea
          id="deprecation_notice"
          label={SERVICE_LIFECYCLE_STRINGS.deprecationNoticeLabel}
          value={notice}
          onChange={(e) => onNoticeChange(e.target.value)}
          maxLength={MAX_DEPRECATION_NOTICE_LENGTH}
          rows={3}
          helpText={SERVICE_LIFECYCLE_STRINGS.deprecationNoticeHelp}
          ariaDescribedBy="deprecation_notice-count"
        />
        <div className="mt-1 flex justify-end text-xs text-fg-tertiary dark:text-fg-tertiary-dark">
          <p id="deprecation_notice-count">
            {SERVICE_LIFECYCLE_STRINGS.noticeCounter(notice.length, MAX_DEPRECATION_NOTICE_LENGTH)}
          </p>
        </div>
      </div>
    </div>
  );
}

export default ServiceLifecycleInputs;
