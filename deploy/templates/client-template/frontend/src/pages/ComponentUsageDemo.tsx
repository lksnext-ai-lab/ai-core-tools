import React, { useState } from 'react';
import { 
  Header, 
  Sidebar, 
  Footer, 
  Layout, 
  ThemeSelector,
  useTheme,
  type ExtraRoute
} from '@lksnext/ai-core-tools-base';

const ComponentUsageDemo: React.FC = () => {
  const { theme } = useTheme();
  const [selectedDemo, setSelectedDemo] = useState('layout');
  const [showCode, setShowCode] = useState(false);

  const demos = [
    { id: 'layout', name: 'Layout System', icon: '🏗️' },
    { id: 'header', name: 'Header Component', icon: '📋' },
    { id: 'sidebar', name: 'Sidebar Component', icon: '📂' },
    { id: 'footer', name: 'Footer Component', icon: '🦶' },
    { id: 'theme', name: 'Theme System', icon: '🎨' },
    { id: 'custom', name: 'Custom Layout', icon: '⚙️' }
  ];

  const renderDemo = () => {
    switch (selectedDemo) {
      case 'layout':
        return (
          <div className="space-y-4">
            <h3 
              className="text-xl font-semibold"
              style={{ color: theme.colors?.primary }}
            >
              Complete Layout System
            </h3>
            <p style={{ color: theme.colors?.text, opacity: 0.8 }}>
              The Layout component provides a complete page structure with header, sidebar, and footer.
            </p>
            <div 
              className="border-2 border-dashed p-4 rounded-lg"
              style={{ borderColor: theme.colors?.primary + '40' }}
            >
              <Layout
                headerProps={{
                  title: "Demo Header",
                  logoUrl: "/mattin-small.png"
                }}
                sidebarProps={{
                  children: (
                    <div className="p-4">
                      <h4 className="font-semibold mb-2">Demo Sidebar</h4>
                      <ul className="space-y-1 text-sm">
                        <li><a href="#" className="text-blue-600 hover:underline">Menu Item 1</a></li>
                        <li><a href="#" className="text-blue-600 hover:underline">Menu Item 2</a></li>
                        <li><a href="#" className="text-blue-600 hover:underline">Menu Item 3</a></li>
                      </ul>
                    </div>
                  )
                }}
                footerProps={{
                  copyright: "© 2024 Demo Company",
                  showVersion: true
                }}
              >
                <div className="p-6">
                  <h2 className="text-2xl font-bold mb-4">Layout Content</h2>
                  <p>This is the main content area of the layout.</p>
                </div>
              </Layout>
            </div>
          </div>
        );

      case 'header':
        return (
          <div className="space-y-4">
            <h3 
              className="text-xl font-semibold"
              style={{ color: theme.colors?.primary }}
            >
              Header Component Variations
            </h3>
            <p style={{ color: theme.colors?.text, opacity: 0.8 }}>
              Different header configurations and customizations.
            </p>
            
            <div className="space-y-4">
              <div>
                <h4 className="font-semibold mb-2">Basic Header</h4>
                <div 
                  className="border rounded-lg overflow-hidden"
                  style={{ borderColor: theme.colors?.primary + '30' }}
                >
                  <Header
                    title="Basic Header"
                    logoUrl="/client-logo.png"
                  />
                </div>
              </div>
              
              <div>
                <h4 className="font-semibold mb-2">Header with Custom Content</h4>
                <div 
                  className="border rounded-lg overflow-hidden"
                  style={{ borderColor: theme.colors?.primary + '30' }}
                >
                  <Header
                    title="Custom Header"
                    children={
                      <div className="flex items-center space-x-4">
                        <ThemeSelector />
                        <button 
                          className="px-4 py-2 rounded text-sm"
                          style={{
                            backgroundColor: theme.colors?.primary,
                            color: '#ffffff'
                          }}
                        >
                          Action Button
                        </button>
                      </div>
                    }
                  />
                </div>
              </div>
              
              <div>
                <h4 className="font-semibold mb-2">Styled Header</h4>
                <div 
                  className="border rounded-lg overflow-hidden"
                  style={{ borderColor: theme.colors?.primary + '30' }}
                >
                  <Header
                    title="Styled Header"
                    className="bg-gradient-to-r from-blue-600 to-purple-600 text-white"
                    children={
                      <div className="text-white">
                        <span className="text-sm opacity-90">Welcome back!</span>
                      </div>
                    }
                  />
                </div>
              </div>
            </div>
          </div>
        );

      case 'sidebar':
        return (
          <div className="space-y-4">
            <h3 
              className="text-xl font-semibold"
              style={{ color: theme.colors?.primary }}
            >
              Sidebar Component Variations
            </h3>
            <p style={{ color: theme.colors?.text, opacity: 0.8 }}>
              Different sidebar configurations and navigation patterns.
            </p>
            
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div>
                <h4 className="font-semibold mb-2">Basic Sidebar</h4>
                <div 
                  className="border rounded-lg h-64 overflow-hidden"
                  style={{ borderColor: theme.colors?.primary + '30' }}
                >
                  <Sidebar
                    children={
                      <div className="p-4">
                        <h4 className="font-semibold mb-4">Navigation</h4>
                        <nav className="space-y-2">
                          <a href="#" className="block px-3 py-2 rounded hover:bg-gray-100">Dashboard</a>
                          <a href="#" className="block px-3 py-2 rounded hover:bg-gray-100">Projects</a>
                          <a href="#" className="block px-3 py-2 rounded hover:bg-gray-100">Settings</a>
                        </nav>
                      </div>
                    }
                  />
                </div>
              </div>
              
              <div>
                <h4 className="font-semibold mb-2">Sidebar with Icons</h4>
                <div 
                  className="border rounded-lg h-64 overflow-hidden"
                  style={{ borderColor: theme.colors?.primary + '30' }}
                >
                  <Sidebar
                    children={
                      <div className="p-4">
                        <h4 className="font-semibold mb-4 flex items-center">
                          <span className="mr-2">📊</span>
                          Analytics
                        </h4>
                        <nav className="space-y-2">
                          <a href="#" className="flex items-center px-3 py-2 rounded hover:bg-gray-100">
                            <span className="mr-2">📈</span>
                            Reports
                          </a>
                          <a href="#" className="flex items-center px-3 py-2 rounded hover:bg-gray-100">
                            <span className="mr-2">👥</span>
                            Users
                          </a>
                          <a href="#" className="flex items-center px-3 py-2 rounded hover:bg-gray-100">
                            <span className="mr-2">⚙️</span>
                            Settings
                          </a>
                        </nav>
                      </div>
                    }
                  />
                </div>
              </div>
            </div>
          </div>
        );

      case 'footer':
        return (
          <div className="space-y-4">
            <h3 
              className="text-xl font-semibold"
              style={{ color: theme.colors?.primary }}
            >
              Footer Component Variations
            </h3>
            <p style={{ color: theme.colors?.text, opacity: 0.8 }}>
              Different footer configurations and content layouts.
            </p>
            
            <div className="space-y-4">
              <div>
                <h4 className="font-semibold mb-2">Basic Footer</h4>
                <div 
                  className="border rounded-lg overflow-hidden"
                  style={{ borderColor: theme.colors?.primary + '30' }}
                >
                  <Footer
                    copyright="© 2024 Demo Company. All rights reserved."
                    showVersion={true}
                  />
                </div>
              </div>
              
              <div>
                <h4 className="font-semibold mb-2">Footer with Custom Content</h4>
                <div 
                  className="border rounded-lg overflow-hidden"
                  style={{ borderColor: theme.colors?.primary + '30' }}
                >
                  <Footer
                    copyright="© 2024 Demo Company"
                    children={
                      <div className="flex justify-between items-center">
                        <div className="text-sm">
                          <a href="#" className="text-blue-600 hover:underline mr-4">Privacy</a>
                          <a href="#" className="text-blue-600 hover:underline mr-4">Terms</a>
                          <a href="#" className="text-blue-600 hover:underline">Contact</a>
                        </div>
                        <div className="text-sm text-gray-500">
                          Version 1.0.0
                        </div>
                      </div>
                    }
                  />
                </div>
              </div>
              
              <div>
                <h4 className="font-semibold mb-2">Styled Footer</h4>
                <div 
                  className="border rounded-lg overflow-hidden"
                  style={{ borderColor: theme.colors?.primary + '30' }}
                >
                  <Footer
                    copyright="© 2024 Demo Company"
                    className="bg-gray-900 text-white"
                    children={
                      <div className="text-center">
                        <p className="text-sm opacity-90">Built with AI-Core-Tools</p>
                      </div>
                    }
                  />
                </div>
              </div>
            </div>
          </div>
        );

      case 'theme':
        return (
          <div className="space-y-4">
            <h3 
              className="text-xl font-semibold"
              style={{ color: theme.colors?.primary }}
            >
              Theme System Integration
            </h3>
            <p style={{ color: theme.colors?.text, opacity: 0.8 }}>
              How to integrate the theme system with your components.
            </p>
            
            <div 
              className="p-6 rounded-lg"
              style={{
                backgroundColor: theme.colors?.surface,
                border: `1px solid ${theme.colors?.primary}20`
              }}
            >
              <h4 className="font-semibold mb-4">Theme Selector Component</h4>
              <div className="flex items-center space-x-4 mb-4">
                <ThemeSelector />
                <span 
                  className="text-sm"
                  style={{ color: theme.colors?.text, opacity: 0.7 }}
                >
                  Current: <strong>{theme.name}</strong>
                </span>
              </div>
              
              <div className="grid grid-cols-2 gap-4">
                <div 
                  className="p-4 rounded"
                  style={{
                    backgroundColor: theme.colors?.primary + '10',
                    border: `1px solid ${theme.colors?.primary}30`
                  }}
                >
                  <h5 
                    className="font-semibold mb-2"
                    style={{ color: theme.colors?.primary }}
                  >
                    Primary Color
                  </h5>
                  <div 
                    className="w-full h-8 rounded"
                    style={{ backgroundColor: theme.colors?.primary }}
                  />
                </div>
                
                <div 
                  className="p-4 rounded"
                  style={{
                    backgroundColor: theme.colors?.secondary + '10',
                    border: `1px solid ${theme.colors?.secondary}30`
                  }}
                >
                  <h5 
                    className="font-semibold mb-2"
                    style={{ color: theme.colors?.secondary }}
                  >
                    Secondary Color
                  </h5>
                  <div 
                    className="w-full h-8 rounded"
                    style={{ backgroundColor: theme.colors?.secondary }}
                  />
                </div>
              </div>
            </div>
          </div>
        );

      case 'custom':
        return (
          <div className="space-y-4">
            <h3 
              className="text-xl font-semibold"
              style={{ color: theme.colors?.primary }}
            >
              Custom Layout Example
            </h3>
            <p style={{ color: theme.colors?.text, opacity: 0.8 }}>
              Building a completely custom layout using individual components.
            </p>
            
            <div 
              className="border-2 border-dashed p-4 rounded-lg"
              style={{ borderColor: theme.colors?.primary + '40' }}
            >
              <div className="min-h-96 flex flex-col">
                {/* Custom Header */}
                <div 
                  className="p-4 border-b"
                  style={{
                    backgroundColor: theme.colors?.primary,
                    color: '#ffffff'
                  }}
                >
                  <div className="flex justify-between items-center">
                    <h1 className="text-xl font-bold">Custom App Layout</h1>
                    <div className="flex items-center space-x-2">
                      <ThemeSelector />
                      <button className="px-3 py-1 bg-white bg-opacity-20 rounded text-sm">
                        Profile
                      </button>
                    </div>
                  </div>
                </div>
                
                {/* Custom Body */}
                <div className="flex flex-1">
                  {/* Custom Sidebar */}
                  <div 
                    className="w-64 p-4 border-r"
                    style={{
                      backgroundColor: theme.colors?.surface,
                      borderColor: theme.colors?.primary + '20'
                    }}
                  >
                    <nav className="space-y-2">
                      <a href="#" className="block px-3 py-2 rounded hover:bg-gray-100">
                        🏠 Dashboard
                      </a>
                      <a href="#" className="block px-3 py-2 rounded hover:bg-gray-100">
                        📊 Analytics
                      </a>
                      <a href="#" className="block px-3 py-2 rounded hover:bg-gray-100">
                        ⚙️ Settings
                      </a>
                    </nav>
                  </div>
                  
                  {/* Custom Content */}
                  <div className="flex-1 p-6">
                    <h2 className="text-2xl font-bold mb-4">Custom Content Area</h2>
                    <p style={{ color: theme.colors?.text, opacity: 0.8 }}>
                      This demonstrates how you can create completely custom layouts
                      using the individual components from the library.
                    </p>
                  </div>
                </div>
                
                {/* Custom Footer */}
                <div 
                  className="p-4 border-t text-center text-sm"
                  style={{
                    backgroundColor: theme.colors?.surface,
                    borderColor: theme.colors?.primary + '20',
                    color: theme.colors?.text
                  }}
                >
                  Custom Footer - © 2024 Demo Company
                </div>
              </div>
            </div>
          </div>
        );

      default:
        return null;
    }
  };

  const getCodeExample = () => {
    switch (selectedDemo) {
      case 'layout':
        return `import { Layout } from '@lksnext/ai-core-tools-base';

<Layout
  headerProps={{
    title: "My App",
    logoUrl: "/mattin-small.png"
  }}
  sidebarProps={{
    children: <NavigationMenu />
  }}
  footerProps={{
    copyright: "© 2024 My Company"
  }}
>
  <div>Your content here</div>
</Layout>`;

      case 'header':
        return `import { Header } from '@lksnext/ai-core-tools-base';

<Header
  title="My App"
  logoUrl="/logo.png"
  className="bg-blue-600 text-white"
  children={
    <div className="flex items-center space-x-4">
      <ThemeSelector />
      <button>Action</button>
    </div>
  }
/>`;

      case 'sidebar':
        return `import { Sidebar } from '@lksnext/ai-core-tools-base';

<Sidebar
  children={
    <div className="p-4">
      <h4 className="font-semibold mb-4">Navigation</h4>
      <nav className="space-y-2">
        <a href="/dashboard">Dashboard</a>
        <a href="/settings">Settings</a>
      </nav>
    </div>
  }
/>`;

      case 'footer':
        return `import { Footer } from '@lksnext/ai-core-tools-base';

<Footer
  copyright="© 2024 My Company"
  showVersion={true}
  children={
    <div className="flex justify-between">
      <div>Links</div>
      <div>Version</div>
    </div>
  }
/>`;

      case 'theme':
        return `import { useTheme, ThemeSelector } from '@lksnext/ai-core-tools-base';

const MyComponent = () => {
  const { theme, switchTheme } = useTheme();
  
  return (
    <div style={{ color: theme.colors?.text }}>
      <ThemeSelector />
      <button 
        onClick={() => switchTheme('dark')}
        style={{ backgroundColor: theme.colors?.primary }}
      >
        Switch Theme
      </button>
    </div>
  );
};`;

      case 'custom':
        return `import { 
  Header, 
  Sidebar, 
  Footer, 
  useTheme 
} from '@lksnext/ai-core-tools-base';

const CustomLayout = () => {
  const { theme } = useTheme();
  
  return (
    <div className="min-h-screen flex flex-col">
      <Header title="Custom App" />
      <div className="flex flex-1">
        <Sidebar children={<Navigation />} />
        <main className="flex-1 p-6">
          {/* Your content */}
        </main>
      </div>
      <Footer copyright="© 2024" />
    </div>
  );
};`;

      default:
        return '';
    }
  };

  return (
    <div className="max-w-7xl mx-auto p-6">
      {/* Header */}
      <div 
        className="rounded-lg p-8 mb-8 text-center"
        style={{
          background: `linear-gradient(135deg, ${theme.colors?.primary}20, ${theme.colors?.secondary}20)`,
          border: `1px solid ${theme.colors?.primary}30`
        }}
      >
        <h1 
          className="text-4xl font-bold mb-4"
          style={{ color: theme.colors?.text }}
        >
          🧩 Component Usage Examples
        </h1>
        <p 
          className="text-xl mb-6"
          style={{ color: theme.colors?.text, opacity: 0.8 }}
        >
          Learn how to use individual components from the AI-Core-Tools library
        </p>
      </div>

      {/* Demo Selector */}
      <div className="mb-8">
        <div className="flex flex-wrap gap-2 mb-4">
          {demos.map((demo) => (
            <button
              key={demo.id}
              onClick={() => setSelectedDemo(demo.id)}
              className={`px-4 py-2 rounded-lg font-medium transition-all ${
                selectedDemo === demo.id
                  ? 'client-button'
                  : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
              }`}
            >
              <span className="mr-2">{demo.icon}</span>
              {demo.name}
            </button>
          ))}
        </div>
        
        <div className="flex items-center justify-between">
          <h2 
            className="text-2xl font-semibold"
            style={{ color: theme.colors?.text }}
          >
            {demos.find(d => d.id === selectedDemo)?.name}
          </h2>
          <button
            onClick={() => setShowCode(!showCode)}
            className="px-4 py-2 rounded-lg border transition-all hover:bg-gray-50"
            style={{
              borderColor: theme.colors?.primary,
              color: theme.colors?.primary
            }}
          >
            {showCode ? 'Hide' : 'Show'} Code
          </button>
        </div>
      </div>

      {/* Demo Content */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div>
          {renderDemo()}
        </div>
        
        {showCode && (
          <div 
            className="p-6 rounded-lg"
            style={{
              backgroundColor: theme.colors?.surface,
              border: `1px solid ${theme.colors?.primary}20`
            }}
          >
            <h3 
              className="text-lg font-semibold mb-4"
              style={{ color: theme.colors?.primary }}
            >
              Code Example
            </h3>
            <pre 
              className="text-xs bg-gray-900 text-green-400 p-4 rounded-lg overflow-x-auto"
              style={{ fontFamily: 'Monaco, Consolas, monospace' }}
            >
              {getCodeExample()}
            </pre>
          </div>
        )}
      </div>

      {/* Integration Tips */}
      <div className="mt-8">
        <h2 
          className="text-2xl font-semibold mb-6"
          style={{ color: theme.colors?.text }}
        >
          💡 Integration Tips
        </h2>
        
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <div 
            className="p-6 rounded-lg"
            style={{
              backgroundColor: theme.colors?.surface,
              border: `1px solid ${theme.colors?.primary}20`
            }}
          >
            <h3 
              className="font-semibold mb-3"
              style={{ color: theme.colors?.primary }}
            >
              🎨 Theme Integration
            </h3>
            <p 
              className="text-sm"
              style={{ color: theme.colors?.text, opacity: 0.8 }}
            >
              Use the useTheme hook to access theme colors and apply them consistently across your components.
            </p>
          </div>
          
          <div 
            className="p-6 rounded-lg"
            style={{
              backgroundColor: theme.colors?.surface,
              border: `1px solid ${theme.colors?.secondary}20`
            }}
          >
            <h3 
              className="font-semibold mb-3"
              style={{ color: theme.colors?.secondary }}
            >
              🧩 Component Composition
            </h3>
            <p 
              className="text-sm"
              style={{ color: theme.colors?.text, opacity: 0.8 }}
            >
              Mix and match individual components to create custom layouts that fit your specific needs.
            </p>
          </div>
          
          <div 
            className="p-6 rounded-lg"
            style={{
              backgroundColor: theme.colors?.surface,
              border: `1px solid ${theme.colors?.accent}20`
            }}
          >
            <h3 
              className="font-semibold mb-3"
              style={{ color: theme.colors?.accent }}
            >
              ⚙️ Customization
            </h3>
            <p 
              className="text-sm"
              style={{ color: theme.colors?.text, opacity: 0.8 }}
            >
              All components accept className and children props for maximum customization flexibility.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ComponentUsageDemo;
