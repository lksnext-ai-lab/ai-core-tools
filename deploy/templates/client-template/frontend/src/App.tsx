import { BaseApp } from '@lksnext/ai-core-tools-base';
import type { ExtraRoute } from '@lksnext/ai-core-tools-base';
import { clientConfig } from './config/clientConfig';
import CustomPage from './pages/CustomPage';
import CustomFeature from './pages/CustomFeature';
import CustomHomePage from './pages/CustomHomePage';

function App() {
  const extraRoutes: ExtraRoute[] = [
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
    <BaseApp 
      clientConfig={clientConfig}
      extraRoutes={extraRoutes}
    />
  );
}

export default App;
