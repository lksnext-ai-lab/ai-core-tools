import React, { useState } from 'react';
import { useSubscription } from '../hooks/useSubscription';
import { apiService } from '../services/api';
import { LoadingState } from '../components/ui/LoadingState';
import { ErrorState } from '../components/ui/ErrorState';
import { useApiMutation } from '../hooks/useApiMutation';
import { errorMessage } from '../constants/messages';

interface TierDescriptor {
  readonly id: 'free' | 'starter' | 'pro';
  readonly name: string;
  readonly price: string;
  readonly features: ReadonlyArray<string>;
}

const TIERS: ReadonlyArray<TierDescriptor> = [
  {
    id: 'free',
    name: 'Free',
    price: '$0',
    features: ['1 App', '3 Agents per App', '2 Silos per App', 'System LLM (limited)'],
  },
  {
    id: 'starter',
    name: 'Starter',
    price: 'From $X/mo',
    features: ['2 Apps', '10 Agents per App', '5 Silos per App', 'Own API keys', '7-day trial'],
  },
  {
    id: 'pro',
    name: 'Pro',
    price: 'From $Y/mo',
    features: ['10 Apps', '50 Agents per App', '20 Silos per App', 'Unlimited collaborators', '7-day trial'],
  },
];

interface CheckoutResponse {
  readonly url?: string;
}

const SubscriptionPage: React.FC = () => {
  const { subscription, usage, isLoading, error, refresh } = useSubscription();
  const mutate = useApiMutation();
  const [checkoutLoading, setCheckoutLoading] = useState<string | null>(null);
  const [portalLoading, setPortalLoading] = useState(false);

  async function handleUpgrade(tier: TierDescriptor['id']) {
    setCheckoutLoading(tier);
    const data = await mutate(
      () => apiService.createCheckoutSession(tier) as Promise<CheckoutResponse>,
      {
        loading: 'Starting checkout…',
        success: 'Redirecting to checkout…',
        error: (err) => errorMessage(err, 'Failed to start checkout'),
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
        loading: 'Opening billing portal…',
        success: 'Billing portal ready',
        error: (err) => errorMessage(err, 'Failed to open billing portal'),
      },
    );
    setPortalLoading(false);
    if (data?.url) {
      window.open(data.url, '_blank');
    }
  }

  if (isLoading) return <LoadingState message="Loading subscription..." />;
  if (error) return <ErrorState error={error} onRetry={refresh} />;

  const currentTier = subscription?.tier ?? 'free';
  const pctUsed = usage?.pct_used ?? 0;

  let usageBarColor = 'bg-blue-500';
  if (pctUsed >= 1) usageBarColor = 'bg-red-500';
  else if (pctUsed >= 0.8) usageBarColor = 'bg-yellow-500';

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Subscription</h1>
        <p className="text-gray-600">Manage your plan and monthly usage</p>
      </div>

      {/* Current plan summary */}
      <div className="bg-white border rounded-lg p-6 shadow-sm">
        <div className="flex justify-between items-start gap-4">
          <div>
            <p className="text-sm text-gray-500 uppercase tracking-wide">Current plan</p>
            <p className="text-xl font-semibold capitalize">{currentTier}</p>
            <p className="text-sm text-gray-500 mt-1">
              Billing:{' '}
              <span className="capitalize">{subscription?.billing_status ?? 'none'}</span>
            </p>
          </div>
          {currentTier !== 'free' && (
            <button
              type="button"
              onClick={handlePortal}
              disabled={portalLoading}
              className="text-sm border rounded px-3 py-1.5 hover:bg-gray-50 disabled:opacity-50"
            >
              {portalLoading ? 'Opening…' : 'Manage billing'}
            </button>
          )}
        </div>

        <div className="mt-4">
          {usage?.call_limit === -1 ? (
            <div className="flex justify-between text-sm text-gray-600 mb-1">
              <span>System LLM usage</span>
              <span>{usage?.call_count ?? 0} calls — Unlimited</span>
            </div>
          ) : (
            <>
              <div className="flex justify-between text-sm text-gray-600 mb-1">
                <span>System LLM usage</span>
                <span>
                  {usage?.call_count ?? 0} / {usage?.call_limit ?? 0} calls
                </span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div
                  className={`h-2 rounded-full transition-all ${usageBarColor}`}
                  style={{ width: `${Math.min(pctUsed * 100, 100)}%` }}
                />
              </div>
              {pctUsed >= 0.8 && (
                <p className="text-sm text-yellow-700 mt-1">
                  {pctUsed >= 1
                    ? 'Quota exhausted. Own API calls are unaffected.'
                    : 'Approaching quota limit.'}
                </p>
              )}
            </>
          )}
        </div>
      </div>

      {/* Tier comparison */}
      <h2 className="text-lg font-semibold text-gray-900">Plans</h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {TIERS.map((tier) => (
          <div
            key={tier.id}
            className={`border rounded-lg p-5 shadow-sm ${
              currentTier === tier.id ? 'border-blue-500 bg-blue-50' : 'bg-white'
            }`}
          >
            <h3 className="text-lg font-semibold text-gray-900">{tier.name}</h3>
            <p className="text-gray-500 text-sm mb-3">{tier.price}</p>
            <ul className="space-y-1 text-sm text-gray-600 mb-4">
              {tier.features.map((feature) => (
                <li key={feature} className="flex items-start gap-1">
                  <span className="text-green-500 mt-0.5">&#10003;</span> {feature}
                </li>
              ))}
            </ul>
            {tier.id !== 'free' && currentTier !== tier.id && (
              <button
                type="button"
                onClick={() => handleUpgrade(tier.id)}
                disabled={checkoutLoading === tier.id}
                className="w-full bg-blue-600 text-white rounded px-3 py-1.5 text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
              >
                {checkoutLoading === tier.id ? 'Redirecting…' : `Upgrade to ${tier.name}`}
              </button>
            )}
            {currentTier === tier.id && (
              <p className="text-sm text-blue-600 font-medium text-center">Current plan</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

export default SubscriptionPage;
