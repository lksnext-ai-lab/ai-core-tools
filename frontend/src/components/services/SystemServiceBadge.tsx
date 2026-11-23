import { useTranslation } from 'react-i18next';

/** Marks a platform-wide service (app_id NULL) listed among an app's services. */
function SystemServiceBadge() {
  const { t } = useTranslation('common');

  return (
    <span
      className="ml-1 text-xs font-medium text-blue-700 bg-blue-100 dark:text-blue-200 dark:bg-blue-900/40 px-1.5 py-0.5 rounded"
      title={t('systemServiceBadge.tooltip')}
    >
      {t('systemServiceBadge.label')}
    </span>
  );
}

export default SystemServiceBadge;
