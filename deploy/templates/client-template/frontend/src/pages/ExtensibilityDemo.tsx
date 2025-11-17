import React, { useState } from 'react';
import { useTheme } from '@lksnext/ai-core-tools-base';

const ExtensibilityDemo: React.FC = () => {
  const { theme, switchTheme } = useTheme();
  const [selectedTheme, setSelectedTheme] = useState('client-custom');

  const handleThemeChange = (themeName: string) => {
    setSelectedTheme(themeName);
    switchTheme(themeName);
  };

  return (
    <div className="max-w-6xl mx-auto p-6">
      {/* Header Section */}
      <div 
        className="rounded-lg p-8 mb-8 text-center client-card"
        style={{
          background: `linear-gradient(135deg, ${theme.colors?.primary}20, ${theme.colors?.secondary}20)`,
          border: `1px solid ${theme.colors?.primary}30`
        }}
      >
        <h1 
          className="text-4xl font-bold mb-4"
          style={{ color: theme.colors?.text }}
        >
          🚀 Extensibility Demo
        </h1>
        <p 
          className="text-xl mb-6"
          style={{ color: theme.colors?.text, opacity: 0.8 }}
        >
          Showcasing the new modular and extensible AI-Core-Tools library
        </p>
      </div>

      {/* Theme Demonstration */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-8">
        <div 
          className="p-6 rounded-lg shadow-lg"
          style={{
            backgroundColor: theme.colors?.surface,
            border: `1px solid ${theme.colors?.primary}20`
          }}
        >
          <h2 
            className="text-2xl font-semibold mb-4"
            style={{ color: theme.colors?.primary }}
          >
            🎨 Theme System
          </h2>
          <p 
            className="mb-4"
            style={{ color: theme.colors?.text, opacity: 0.8 }}
          >
            The library now supports multiple themes with easy switching:
          </p>
          
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span style={{ color: theme.colors?.text }}>Current Theme:</span>
              <span 
                className="px-3 py-1 rounded-full text-sm font-medium"
                style={{
                  backgroundColor: theme.colors?.primary,
                  color: '#ffffff'
                }}
              >
                {theme.name}
              </span>
            </div>
            
            <div className="flex gap-2">
              <button
                onClick={() => handleThemeChange('client-custom')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  selectedTheme === 'client-custom' 
                    ? 'client-button' 
                    : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                }`}
              >
                Custom Theme
              </button>
              <button
                onClick={() => handleThemeChange('corporate')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  selectedTheme === 'corporate' 
                    ? 'client-button' 
                    : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                }`}
              >
                Corporate Theme
              </button>
            </div>
          </div>
        </div>

        <div 
          className="p-6 rounded-lg shadow-lg"
          style={{
            backgroundColor: theme.colors?.surface,
            border: `1px solid ${theme.colors?.secondary}20`
          }}
        >
          <h2 
            className="text-2xl font-semibold mb-4"
            style={{ color: theme.colors?.secondary }}
          >
            🧩 Modular Components
          </h2>
          <p 
            className="mb-4"
            style={{ color: theme.colors?.text, opacity: 0.8 }}
          >
            Import and use individual components:
          </p>
          
          <div className="space-y-2 text-sm">
            <div className="flex items-center gap-2">
              <span className="text-green-500">✓</span>
              <code className="bg-gray-100 px-2 py-1 rounded">Header</code>
              <span style={{ color: theme.colors?.text, opacity: 0.7 }}>- Customizable header</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-green-500">✓</span>
              <code className="bg-gray-100 px-2 py-1 rounded">Sidebar</code>
              <span style={{ color: theme.colors?.text, opacity: 0.7 }}>- Navigation sidebar</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-green-500">✓</span>
              <code className="bg-gray-100 px-2 py-1 rounded">Footer</code>
              <span style={{ color: theme.colors?.text, opacity: 0.7 }}>- Configurable footer</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-green-500">✓</span>
              <code className="bg-gray-100 px-2 py-1 rounded">ThemeSelector</code>
              <span style={{ color: theme.colors?.text, opacity: 0.7 }}>- Theme switching</span>
            </div>
          </div>
        </div>
      </div>

      {/* Configuration Examples */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-8">
        <div 
          className="p-6 rounded-lg shadow-lg"
          style={{
            backgroundColor: theme.colors?.surface,
            border: `1px solid ${theme.colors?.accent}20`
          }}
        >
          <h2 
            className="text-2xl font-semibold mb-4"
            style={{ color: theme.colors?.accent }}
          >
            ⚙️ Simplified Configuration
          </h2>
          <p 
            className="mb-4"
            style={{ color: theme.colors?.text, opacity: 0.8 }}
          >
            Much easier configuration with LibraryConfig:
          </p>
          
          <pre 
            className="text-xs bg-gray-900 text-green-400 p-4 rounded-lg overflow-x-auto"
            style={{ fontFamily: 'Monaco, Consolas, monospace' }}
          >
{`const config: LibraryConfig = {
  name: 'My Client',
  themeProps: {
    defaultTheme: 'custom',
    customThemes: { custom: myTheme }
  },
  headerProps: { title: 'My App' },
  features: { showThemeSelector: true }
};`}
          </pre>
        </div>

        <div 
          className="p-6 rounded-lg shadow-lg"
          style={{
            backgroundColor: theme.colors?.surface,
            border: `1px solid ${theme.colors?.primary}20`
          }}
        >
          <h2 
            className="text-2xl font-semibold mb-4"
            style={{ color: theme.colors?.primary }}
          >
            🛣️ Route Extensibility
          </h2>
          <p 
            className="mb-4"
            style={{ color: theme.colors?.text, opacity: 0.8 }}
          >
            Add custom routes easily:
          </p>
          
          <pre 
            className="text-xs bg-gray-900 text-blue-400 p-4 rounded-lg overflow-x-auto"
            style={{ fontFamily: 'Monaco, Consolas, monospace' }}
          >
{`const extraRoutes: ExtraRoute[] = [
  {
    path: '/custom-page',
    element: <CustomPage />,
    name: 'Custom Page',
    protected: true
  }
];`}
          </pre>
        </div>
      </div>

      {/* Feature Showcase */}
      <div 
        className="p-6 rounded-lg shadow-lg"
        style={{
          backgroundColor: theme.colors?.surface,
          border: `1px solid ${theme.colors?.secondary}20`
        }}
      >
        <h2 
          className="text-2xl font-semibold mb-4"
          style={{ color: theme.colors?.secondary }}
        >
          ✨ New Features Available
        </h2>
        
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <div className="p-4 rounded-lg bg-gray-50">
            <h3 className="font-semibold mb-2" style={{ color: theme.colors?.primary }}>
              🎨 Theme System
            </h3>
            <p className="text-sm" style={{ color: theme.colors?.text, opacity: 0.8 }}>
              Multiple themes, custom CSS, easy switching
            </p>
          </div>
          
          <div className="p-4 rounded-lg bg-gray-50">
            <h3 className="font-semibold mb-2" style={{ color: theme.colors?.secondary }}>
              🧩 Modular Components
            </h3>
            <p className="text-sm" style={{ color: theme.colors?.text, opacity: 0.8 }}>
              Import individual components as needed
            </p>
          </div>
          
          <div className="p-4 rounded-lg bg-gray-50">
            <h3 className="font-semibold mb-2" style={{ color: theme.colors?.accent }}>
              ⚙️ Easy Configuration
            </h3>
            <p className="text-sm" style={{ color: theme.colors?.text, opacity: 0.8 }}>
              Simplified LibraryConfig interface
            </p>
          </div>
          
          <div className="p-4 rounded-lg bg-gray-50">
            <h3 className="font-semibold mb-2" style={{ color: theme.colors?.primary }}>
              🛣️ Route Management
            </h3>
            <p className="text-sm" style={{ color: theme.colors?.text, opacity: 0.8 }}>
              Add custom routes and pages easily
            </p>
          </div>
          
          <div className="p-4 rounded-lg bg-gray-50">
            <h3 className="font-semibold mb-2" style={{ color: theme.colors?.secondary }}>
              🔐 Auth Integration
            </h3>
            <p className="text-sm" style={{ color: theme.colors?.text, opacity: 0.8 }}>
              OIDC and session auth support
            </p>
          </div>
          
          <div className="p-4 rounded-lg bg-gray-50">
            <h3 className="font-semibold mb-2" style={{ color: theme.colors?.accent }}>
              📱 Responsive Layout
            </h3>
            <p className="text-sm" style={{ color: theme.colors?.text, opacity: 0.8 }}>
              Mobile-first responsive design
            </p>
          </div>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex flex-wrap gap-4 justify-center mt-8">
        <button 
          className="client-button px-6 py-3 rounded-lg font-semibold"
          onClick={() => window.location.href = '/apps'}
        >
          View Apps
        </button>
        <button 
          className="px-6 py-3 rounded-lg font-semibold border-2 transition-all hover:scale-105"
          style={{
            borderColor: theme.colors?.secondary,
            color: theme.colors?.secondary
          }}
          onClick={() => window.location.href = '/custom-feature'}
        >
          Custom Feature
        </button>
        <button 
          className="px-6 py-3 rounded-lg font-semibold border-2 transition-all hover:scale-105"
          style={{
            borderColor: theme.colors?.accent,
            color: theme.colors?.accent
          }}
          onClick={() => window.location.href = '/custom-page'}
        >
          Custom Page
        </button>
      </div>
    </div>
  );
};

export default ExtensibilityDemo;
