import React from 'react';
import { Link } from 'react-router-dom';
import { useDeploymentMode } from '../contexts/DeploymentModeContext';
import { useSubscription } from '../hooks/useSubscription';

/**
 * Global sticky banner shown when the user has used >= 80% of their monthly system LLM quota.
 * Only rendered in SaaS mode.
 */
const QuotaWarningBanner: React.FC = () => {
  const { isSaasMode } = useDeploymentMode();
  const { usage } = useSubscription();

  if (!isSaasMode || !usage) return null;

  const pct = usage.pct_used;

  if (pct < 0.8) return null;

  const isExhausted = pct >= 1;

  return (
    <div
      className={`sticky top-0 z-50 w-full px-4 py-2 text-sm text-center font-medium ${
        isExhausted ? 'bg-red-600 text-white' : 'bg-yellow-400 text-yellow-900'
      }`}
    >
      {isExhausted ? (
        <>
          Your monthly system LLM quota is exhausted.{' '}
          <Link to="/subscription" className="underline font-bold">
            Upgrade your plan
          </Link>{' '}
          to continue using system LLM.
        </>
      ) : (
        <>
          You have used {Math.round(pct * 100)}% of your monthly system LLM quota.{' '}
          <Link to="/subscription" className="underline">
            Upgrade
          </Link>{' '}
          to avoid interruptions.
        </>
      )}
    </div>
  );
};

export default QuotaWarningBanner;
