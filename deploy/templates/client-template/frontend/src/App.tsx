import { ExtensibleBaseApp } from '@lksnext/ai-core-tools-base';
import type { ExtraRoute } from '@lksnext/ai-core-tools-base';
import { libraryConfig } from './config/libraryConfig';
import CustomPage from './pages/CustomPage';
import CustomFeature from './pages/CustomFeature';
import ExtensibilityDemo from './pages/ExtensibilityDemo';
import ThemeCustomizationDemo from './pages/ThemeCustomizationDemo';
import ComponentUsageDemo from './pages/ComponentUsageDemo';
import InteractiveDemo from './pages/InteractiveDemo';

function App() {
  const extraRoutes: ExtraRoute[] = [
    {
      path: '/extensibility-demo',
      element: <ExtensibilityDemo />,
      name: 'Extensibility Demo',
      protected: true
    },
    {
      path: '/theme-customization',
      element: <ThemeCustomizationDemo />,
      name: 'Theme Customization',
      protected: true
    },
    {
      path: '/component-usage',
      element: <ComponentUsageDemo />,
      name: 'Component Usage',
      protected: true
    },
    {
      path: '/interactive-demo',
      element: <InteractiveDemo />,
      name: 'Interactive Builder',
      protected: true
    },
    {
      path: '/custom-page',
      element: <CustomPage />,
      name: 'Custom Page',
      protected: true
    },
    {
      path: '/custom-feature',
      element: <CustomFeature />,
      name: 'Custom Feature',
      protected: true
    }
  ];

  return (
    <ExtensibleBaseApp 
      config={libraryConfig}
      extraRoutes={extraRoutes}
    />
  );
}

export default App;
