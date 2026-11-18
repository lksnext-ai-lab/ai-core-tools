import React from 'react';
import { Link } from 'react-router-dom';
import { useDeploymentMode } from '../contexts/DeploymentModeContext';
import { useSubscription } from '../hooks/useSubscription';
import { useTranslation } from 'react-i18next';

/**
 * Global sticky banner shown when the user has used >= 80% of their monthly system LLM quota.
 * Only rendered in SaaS mode.
 */
const QuotaWarningBanner: React.FC = () => {
  const { isSaasMode } = useDeploymentMode();
  const { usage } = useSubscription();
  const { t } = useTranslation('common');

  if (!isSaasMode || !usage) return null;

  const pct = usage.pct_used;

  if (pct < 0.8) return null;

  const isExhausted = pct >= 1;

  return (
    <div
      role={isExhausted ? 'alert' : 'status'}
      className={`sticky top-0 z-50 w-full border-b px-4 py-2 text-sm text-center font-medium ${
        isExhausted
          ? 'bg-error-bg border-error-border text-error-strong dark:bg-error-bg-dark dark:border-error-border-dark dark:text-error-strong-dark'
          : 'bg-bronze-bg border-bronze-border text-bronze-strong dark:bg-bronze-bg-dark dark:border-bronze-border-dark dark:text-bronze-strong-dark'
      }`}
    >
      {isExhausted ? (
        <>
          {t('quotaWarningBanner.exhausted')}{' '}
          <Link to="/subscription" className="underline font-bold">
            {t('quotaWarningBanner.upgradePlan')}
          </Link>{' '}
          {t('quotaWarningBanner.continueUsing')}
        </>
      ) : (
        <>
          {t('quotaWarningBanner.used', { percentage: Math.round(pct * 100) })}{' '}
          <Link to="/subscription" className="underline">
            {t('quotaWarningBanner.upgrade')}
          </Link>{' '}
          {t('quotaWarningBanner.avoidInterruptions')}
        </>
      )}
    </div>
  );
};

export default QuotaWarningBanner;
