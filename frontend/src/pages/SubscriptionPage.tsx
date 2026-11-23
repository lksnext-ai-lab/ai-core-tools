import React, { useState } from 'react';
import { useSubscription } from '../hooks/useSubscription';
import { apiService } from '../services/api';
import { LoadingState } from '../components/ui/LoadingState';
import { ErrorState } from '../components/ui/ErrorState';
import Alert from '../components/ui/Alert';
import { useApiMutation } from '../hooks/useApiMutation';
import { errorMessage } from '../constants/messages';
import Title from '../components/ui/Title';
import { CardApp } from '../components/ui/CardApp';
import { ButtonApp } from '../components/ui/ButtonApp';
import { useTranslation } from 'react-i18next';

type TierId = 'free' | 'starter' | 'pro';
type TierFeatureKey =
  | 'app'
  | 'apps'
  | 'agentsPerApp'
  | 'silosPerApp'
  | 'systemLlmLimited'
  | 'ownApiKeys'
  | 'trialDays'
  | 'unlimitedCollaborators';

interface TierFeature {
  readonly key: TierFeatureKey;
  readonly count?: number;
}

interface TierDescriptor {
  readonly id: TierId;
  readonly features: ReadonlyArray<TierFeature>;
}

const TIERS: ReadonlyArray<TierDescriptor> = [
  {
    id: 'free',
    features: [
      { key: 'app', count: 1 },
      { key: 'agentsPerApp', count: 3 },
      { key: 'silosPerApp', count: 2 },
      { key: 'systemLlmLimited' },
    ],
  },
  {
    id: 'starter',
    features: [
      { key: 'apps', count: 2 },
      { key: 'agentsPerApp', count: 10 },
      { key: 'silosPerApp', count: 5 },
      { key: 'ownApiKeys' },
      { key: 'trialDays', count: 7 },
    ],
  },
  {
    id: 'pro',
    features: [
      { key: 'apps', count: 10 },
      { key: 'agentsPerApp', count: 50 },
      { key: 'silosPerApp', count: 20 },
      { key: 'unlimitedCollaborators' },
      { key: 'trialDays', count: 7 },
    ],
  },
];

interface CheckoutResponse {
  readonly url?: string;
}

const SubscriptionPage: React.FC = () => {
  const { t } = useTranslation('common');
  const { subscription, usage, isLoading, error, refresh } = useSubscription();
  const mutate = useApiMutation();
  const [checkoutLoading, setCheckoutLoading] = useState<string | null>(null);
  const [portalLoading, setPortalLoading] = useState(false);

  async function handleUpgrade(tier: TierDescriptor['id']) {
    setCheckoutLoading(tier);
    const data = await mutate(
      () => apiService.createCheckoutSession(tier) as Promise<CheckoutResponse>,
      {
        loading: t('subscriptionPage.notifications.startingCheckout'),
        success: t('subscriptionPage.notifications.redirectingToCheckout'),
        error: (err) => errorMessage(err, t('subscriptionPage.notifications.checkoutFailed')),
      },
    );
    setCheckoutLoading(null);
    if (data?.url) {
      window.location.href = data.url;
    }
  }

  async function handlePortal() {
    setPortalLoading(true);
    const data = await mutate(
      () => apiService.createPortalSession() as Promise<CheckoutResponse>,
      {
        loading: t('subscriptionPage.notifications.openingBillingPortal'),
        success: t('subscriptionPage.notifications.billingPortalReady'),
        error: (err) => errorMessage(err, t('subscriptionPage.notifications.billingPortalFailed')),
      },
    );
    setPortalLoading(false);
    if (data?.url) {
      window.open(data.url, '_blank');
    }
  }

  if (isLoading) return <LoadingState message={t('subscriptionPage.loading')} />;
  if (error) return <ErrorState error={error} onRetry={refresh} />;

  const currentTier = subscription?.tier ?? 'free';
  const currentTierLabel = t(`subscriptionPage.tiers.${currentTier}.name`, { defaultValue: currentTier });
  const billingStatus = subscription?.billing_status ?? 'none';
  const billingStatusLabel = t(`subscriptionPage.billing.statuses.${billingStatus}`, { defaultValue: billingStatus });
  const pctUsed = usage?.pct_used ?? 0;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <Title
        titulo={t('subscriptionPage.title')}
        subtitulo={t('subscriptionPage.subtitle')}
      />

      {/* Current plan summary */}
      <CardApp variant="canvas">
        <div className="flex justify-between items-start gap-4">
          <div>
            <p className="text-sm text-bronze dark:text-bronze-dark uppercase tracking-wide">{t('subscriptionPage.currentPlan')}</p>
            <p className="text-md text-fg dark:text-fg-dark">{currentTierLabel}</p>
            <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark mt-1">
              {t('subscriptionPage.billing.label')}{' '}
              <span>{billingStatusLabel}</span>
            </p>
          </div>
          {currentTier !== 'free' && (
            <ButtonApp
              type="button"
              onClick={handlePortal}
              disabled={portalLoading}
              label={portalLoading
                ? t('subscriptionPage.actions.opening')
                : t('subscriptionPage.actions.manageBilling')}
              variant="secondary"
              size="medium"
            />
          )}
        </div>

        <div className="mt-4">
          {usage?.call_limit === -1 ? (
            <div className="flex justify-between text-sm text-fg-secondary dark:text-fg-secondary-dark mb-1">
              <span>{t('subscriptionPage.usage.title')}</span>
              <span>{t('subscriptionPage.usage.unlimited', { count: usage?.call_count ?? 0 })}</span>
            </div>
          ) : (
            <>
              <div className="flex justify-between text-sm text-fg-secondary dark:text-fg-secondary-dark mb-1">
                <span>{t('subscriptionPage.usage.title')}</span>
                <span>
                  {t('subscriptionPage.usage.calls', {
                    used: usage?.call_count ?? 0,
                    limit: usage?.call_limit ?? 0,
                  })}
                </span>
              </div>
              <div className="h-2 mt-1 bg-line dark:bg-line-dark rounded-full overflow-hidden">
                <div
                  className="h-full bg-accent dark:bg-fg-dark rounded-full transition-all duration-300"
                  style={{ width: `${Math.min(pctUsed * 100, 100)}%` }}
                />
              </div>
              {pctUsed >= 0.8 && (
                <Alert
                  type="warning"
                  message={pctUsed >= 1
                    ? t('subscriptionPage.usage.quotaExhausted')
                    : t('subscriptionPage.usage.approachingQuota')}
                  className="mt-1"
                />
              )}
            </>
          )}
        </div>
      </CardApp>

      {/* Tier comparison */}
      <Title variant="titTerciario" titulo={t('subscriptionPage.plans')} />
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {TIERS.map((tier) => (
          <CardApp
            key={tier.id}
            variant={currentTier === tier.id ? 'selected' : 'white'}
          >
            <h3 className="text-lg font-semibold text-fg dark:text-fg-dark">
              {t(`subscriptionPage.tiers.${tier.id}.name`)}
            </h3>
            <p className="text-fg-secondary dark:text-fg-secondary-dark text-sm mb-3">
              {t(`subscriptionPage.tiers.${tier.id}.price`)}
            </p>
            <ul className="space-y-1 text-sm text-fg-secondary dark:text-fg-secondary-dark mb-4">
              {tier.features.map(({ key, count }) => (
                <li key={`${key}-${count ?? ''}`} className="flex items-start gap-1">
                  <span className="text-success dark:text-success-dark mt-0.5">&#10003;</span>
                  {t(`subscriptionPage.features.${key}`, count === undefined ? {} : { count })}
                </li>
              ))}
            </ul>
            {tier.id !== 'free' && currentTier !== tier.id && (
              <ButtonApp
                type="button"
                onClick={() => handleUpgrade(tier.id)}
                disabled={checkoutLoading === tier.id}
                label={checkoutLoading === tier.id
                  ? t('subscriptionPage.actions.redirecting')
                  : t('subscriptionPage.actions.upgradeTo', { tier: t(`subscriptionPage.tiers.${tier.id}.name`) })}
                variant="primary"
                size="medium"
                className="w-full"
              />
            )}
            
          </CardApp>
        ))}
      </div>
    </div>
  );
};

export default SubscriptionPage;
