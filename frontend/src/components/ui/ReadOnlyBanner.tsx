import { Lock } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface ReadOnlyBannerProps {
  userRole: string;
  minRole?: string;
}

function ReadOnlyBanner({ userRole, minRole = 'owner' }: Readonly<ReadOnlyBannerProps>) {
  const { t } = useTranslation('common');
  const getRoleDisplay = (role: string) => {
    const roleKey = `collaborationForm.roles.${role.toLowerCase()}`;
    return t(roleKey, { defaultValue: role });
  };

  return (
    <div role="status" aria-live="polite" className="mb-4 bg-bronze-bg border border-bronze-border rounded-lg p-3 dark:bg-bronze-bg-dark dark:border-bronze-border-dark">
      <div className="flex items-center">
        <Lock className="w-4 h-4 text-bronze mr-2 dark:text-bronze-dark" aria-hidden="true" />
        <p className="text-sm text-bronze dark:text-bronze-dark">
          <strong>{t('readOnlyBanner.title')}</strong>{' '}
          {t('readOnlyBanner.description', {
            minRole: getRoleDisplay(minRole),
            userRole: getRoleDisplay(userRole),
          })}
        </p>
      </div>
    </div>
  );
}

export default ReadOnlyBanner;



