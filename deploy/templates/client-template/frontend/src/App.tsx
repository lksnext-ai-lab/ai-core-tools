import { ExtensibleBaseApp } from '@lksnext/ai-core-tools-base';
import type { ExtraRoute } from '@lksnext/ai-core-tools-base';
import { libraryConfig } from './config/libraryConfig';
import CustomPage from './pages/CustomPage';
import CustomFeature from './pages/CustomFeature';
import ExtensibilityDemo from './pages/ExtensibilityDemo';

function App() {
  const extraRoutes: ExtraRoute[] = [
    {
      path: '/extensibility-demo',
      element: <ExtensibilityDemo />,
      name: 'Extensibility Demo',
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
