import { useMemo } from 'react';
import { useSubscription } from './useSubscription';
import { useDeploymentMode } from '../contexts/DeploymentModeContext';

type ResourceType = 'agents' | 'silos' | 'skills' | 'mcp_servers' | 'collaborators' | 'apps';

/**
 * Returns whether a resource type is at the limit for the current subscription tier.
 * Only meaningful in SaaS mode; always returns { atLimit: false } in self-managed mode.
 *
 * @param resourceType - The type of resource to check
 * @param currentCount - How many of this resource already exist
 */
export const useTierLimit = (resourceType: ResourceType, currentCount: number) => {
  const { isSaasMode } = useDeploymentMode();
  const { subscription } = useSubscription();

  const result = useMemo(() => {
    if (!isSaasMode || !subscription) {
      return { atLimit: false, limit: -1, upgradeMessage: '' };
    }

    const limitMap: Record<ResourceType, number> = {
      apps: subscription.max_apps,
      agents: subscription.agents_per_app,
      silos: subscription.silos_per_app,
      skills: subscription.skills_per_app,
      mcp_servers: subscription.mcp_servers_per_app,
      collaborators: subscription.collaborators_per_app,
    };

    const limit = limitMap[resourceType];
    const atLimit = limit >= 0 && currentCount >= limit;
    const tier = subscription.tier;

    let upgradeMessage = '';
    if (atLimit) {
      const nextTier = tier === 'free' ? 'Starter' : 'Pro';
      const label = resourceType.replace(/_/g, ' ');
      upgradeMessage = `Upgrade to ${nextTier} to add more ${label}.`;
    }

    return { atLimit, limit, upgradeMessage };
  }, [isSaasMode, subscription, resourceType, currentCount]);

  return result;
};
