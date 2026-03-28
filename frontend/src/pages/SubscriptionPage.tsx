import React, { useState } from 'react';
import { useSubscription } from '../hooks/useSubscription';
import { apiService } from '../services/api';

const TIERS = [
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

const SubscriptionPage: React.FC = () => {
  const { subscription, usage, isLoading, error, refresh } = useSubscription();
  const [checkoutLoading, setCheckoutLoading] = useState<string | null>(null);
  const [portalLoading, setPortalLoading] = useState(false);

  const handleUpgrade = async (tier: string) => {
    setCheckoutLoading(tier);
    try {
      const data: any = await apiService.createCheckoutSession(tier);
      if (data?.url) {
        window.location.href = data.url;
      }
    } catch (err: any) {
      alert(err?.message || 'Failed to start checkout');
    } finally {
      setCheckoutLoading(null);
    }
  };

  const handlePortal = async () => {
    setPortalLoading(true);
    try {
      const data: any = await apiService.createPortalSession();
      if (data?.url) {
        window.open(data.url, '_blank');
      }
    } catch (err: any) {
      alert(err?.message || 'Failed to open billing portal');
    } finally {
      setPortalLoading(false);
    }
  };

  if (isLoading) return <div className="p-8 text-gray-500">Loading subscription...</div>;
  if (error) return <div className="p-8 text-red-600">{error}</div>;

  const currentTier = subscription?.tier ?? 'free';
  const pctUsed = usage?.pct_used ?? 0;

  return (
    <div className="max-w-4xl mx-auto p-8">
      <h1 className="text-2xl font-bold mb-6">Subscription</h1>

      {/* Current plan summary */}
      <div className="bg-white border rounded-lg p-6 mb-8 shadow-sm">
        <div className="flex justify-between items-start">
          <div>
            <p className="text-sm text-gray-500 uppercase tracking-wide">Current plan</p>
            <p className="text-xl font-semibold capitalize">{currentTier}</p>
            <p className="text-sm text-gray-500 mt-1">
              Billing: <span className="capitalize">{subscription?.billing_status ?? 'none'}</span>
            </p>
          </div>
          {currentTier !== 'free' && (
            <button
              onClick={handlePortal}
              disabled={portalLoading}
              className="text-sm border rounded px-3 py-1 hover:bg-gray-50 disabled:opacity-50"
            >
              {portalLoading ? 'Opening...' : 'Manage billing'}
            </button>
          )}
        </div>

        {/* Usage bar */}
        <div className="mt-4">
          <div className="flex justify-between text-sm text-gray-600 mb-1">
            <span>System LLM usage</span>
            <span>{usage?.call_count ?? 0} / {usage?.call_limit ?? 0} calls</span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div
              className={`h-2 rounded-full transition-all ${pctUsed >= 1 ? 'bg-red-500' : pctUsed >= 0.8 ? 'bg-yellow-500' : 'bg-blue-500'}`}
              style={{ width: `${Math.min(pctUsed * 100, 100)}%` }}
            />
          </div>
          {pctUsed >= 0.8 && (
            <p className="text-sm text-yellow-700 mt-1">
              {pctUsed >= 1 ? 'Quota exhausted. Own API calls are unaffected.' : 'Approaching quota limit.'}
            </p>
          )}
        </div>
      </div>

      {/* Tier comparison */}
      <h2 className="text-lg font-semibold mb-4">Plans</h2>
      <div className="grid grid-cols-3 gap-4">
        {TIERS.map(tier => (
          <div
            key={tier.id}
            className={`border rounded-lg p-5 shadow-sm ${currentTier === tier.id ? 'border-blue-500 bg-blue-50' : 'bg-white'}`}
          >
            <h3 className="text-lg font-semibold">{tier.name}</h3>
            <p className="text-gray-500 text-sm mb-3">{tier.price}</p>
            <ul className="space-y-1 text-sm text-gray-600 mb-4">
              {tier.features.map(f => (
                <li key={f} className="flex items-start gap-1">
                  <span className="text-green-500 mt-0.5">&#10003;</span> {f}
                </li>
              ))}
            </ul>
            {tier.id !== 'free' && currentTier !== tier.id && (
              <button
                onClick={() => handleUpgrade(tier.id)}
                disabled={checkoutLoading === tier.id}
                className="w-full bg-blue-600 text-white rounded px-3 py-1.5 text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
              >
                {checkoutLoading === tier.id ? 'Redirecting...' : `Upgrade to ${tier.name}`}
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
