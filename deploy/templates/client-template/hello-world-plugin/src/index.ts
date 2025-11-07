// Export main plugin creation function
export { createHelloWorldPlugin } from './config/pluginConfig';

// Export components for advanced usage
export { HelloWorldPage } from './pages/HelloWorldPage';
export { HelloWorldAdminPage } from './pages/HelloWorldAdminPage';

// Export types
export type { 
  HelloWorldPluginConfig, 
  HelloWorldPluginModule
} from './config/pluginConfig';
export type { HelloWorldPageProps } from './pages/HelloWorldPage';
export type { HelloWorldAdminPageProps } from './pages/HelloWorldAdminPage';

