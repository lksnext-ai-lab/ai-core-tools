import { BaseApp } from '@lksnext/ai-core-tools-base';
import type { ExtraRoute } from '@lksnext/ai-core-tools-base';
import { clientConfig } from './config/clientConfig';
import CustomPage from './components/CustomPage';

function App() {
  const extraRoutes: ExtraRoute[] = [
    {
      path: '/custom-page',
      element: <CustomPage />,
      name: 'Custom Page',
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
