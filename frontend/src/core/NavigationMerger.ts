import type { 
  NavigationConfig, 
  ExtensibleNavigationConfig, 
  NavigationItem, 
  NavigationOverride,
  NavigationAdditions
} from './types';
import { defaultNavigation } from './defaultNavigation';

/**
 * Merges default navigation with client overrides and additions
 */
export function mergeNavigationConfig(
  extensibleConfig?: ExtensibleNavigationConfig
): NavigationConfig {
  // Start with default navigation
  const merged: NavigationConfig = {
    mainFeatures: [...(defaultNavigation.mainFeatures || [])],
    appNavigation: [...(defaultNavigation.appNavigation || [])],
    admin: [...(defaultNavigation.admin || [])],
    custom: []
  };

  if (!extensibleConfig) {
    return merged;
  }

  // Apply overrides
  if (extensibleConfig.override) {
    extensibleConfig.override.forEach(override => {
      // Find and update existing items
      Object.keys(merged).forEach(section => {
        const items = merged[section as keyof NavigationConfig] as NavigationItem[];
        if (Array.isArray(items)) {
          const itemIndex = items.findIndex(item => item.path === override.path);
          if (itemIndex !== -1) {
            if (override.hidden) {
              // Remove the item
              items.splice(itemIndex, 1);
            } else {
              // Update the item
              items[itemIndex] = { ...items[itemIndex], ...override };
            }
          }
        }
      });
    });
  }

  // Apply removals
  if (extensibleConfig.remove) {
    extensibleConfig.remove.forEach(pathToRemove => {
      Object.keys(merged).forEach(section => {
        const items = merged[section as keyof NavigationConfig] as NavigationItem[];
        if (Array.isArray(items)) {
          const itemIndex = items.findIndex(item => item.path === pathToRemove);
          if (itemIndex !== -1) {
            items.splice(itemIndex, 1);
          }
        }
      });
    });
  }

  // Apply additions
  if (extensibleConfig.add) {
    if (extensibleConfig.add.mainFeatures) {
      merged.mainFeatures = [...(merged.mainFeatures || []), ...extensibleConfig.add.mainFeatures];
    }
    if (extensibleConfig.add.appNavigation) {
      merged.appNavigation = [...(merged.appNavigation || []), ...extensibleConfig.add.appNavigation];
    }
    if (extensibleConfig.add.admin) {
      merged.admin = [...(merged.admin || []), ...extensibleConfig.add.admin];
    }
    if (extensibleConfig.add.custom) {
      merged.custom = [...(merged.custom || []), ...extensibleConfig.add.custom];
    }
    if (extensibleConfig.add.settings) {
      merged.settings = [...(merged.settings || []), ...extensibleConfig.add.settings];
    }
  }

  return merged;
}

/**
 * Helper function to create navigation overrides
 */
export function createNavigationOverride(path: string, overrides: Partial<NavigationOverride>): NavigationOverride {
  return { path, ...overrides };
}

/**
 * Helper function to create navigation additions
 */
export function createNavigationAdditions(additions: NavigationAdditions): NavigationAdditions {
  return additions;
}
