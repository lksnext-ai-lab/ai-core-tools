import React, { useState, useEffect } from 'react';
import { useTheme } from '@lksnext/ai-core-tools-base';

interface ConfigOption {
  key: string;
  label: string;
  type: 'text' | 'color' | 'boolean' | 'select';
  value: any;
  options?: string[];
  description?: string;
}

const InteractiveDemo: React.FC = () => {
  const { theme } = useTheme();
  const [config, setConfig] = useState<Record<string, any>>({
    name: 'My Custom App',
    primaryColor: '#3B82F6',
    secondaryColor: '#1E40AF',
    accentColor: '#F59E0B',
    showHeader: true,
    showSidebar: true,
    showFooter: true,
    showThemeSelector: true,
    headerTitle: 'My App',
    footerCopyright: '© 2024 My Company',
    theme: 'light'
  });

  const [generatedCode, setGeneratedCode] = useState('');
  const [previewMode, setPreviewMode] = useState<'config' | 'code' | 'preview'>('config');

  const configOptions: ConfigOption[] = [
    {
      key: 'name',
      label: 'App Name',
      type: 'text',
      value: config.name,
      description: 'The name of your application'
    },
    {
      key: 'primaryColor',
      label: 'Primary Color',
      type: 'color',
      value: config.primaryColor,
      description: 'Main brand color'
    },
    {
      key: 'secondaryColor',
      label: 'Secondary Color',
      type: 'color',
      value: config.secondaryColor,
      description: 'Supporting brand color'
    },
    {
      key: 'accentColor',
      label: 'Accent Color',
      type: 'color',
      value: config.accentColor,
      description: 'Highlight and call-to-action color'
    },
    {
      key: 'headerTitle',
      label: 'Header Title',
      type: 'text',
      value: config.headerTitle,
      description: 'Title displayed in the header'
    },
    {
      key: 'footerCopyright',
      label: 'Footer Copyright',
      type: 'text',
      value: config.footerCopyright,
      description: 'Copyright text in the footer'
    },
    {
      key: 'showHeader',
      label: 'Show Header',
      type: 'boolean',
      value: config.showHeader,
      description: 'Display the header component'
    },
    {
      key: 'showSidebar',
      label: 'Show Sidebar',
      type: 'boolean',
      value: config.showSidebar,
      description: 'Display the sidebar component'
    },
    {
      key: 'showFooter',
      label: 'Show Footer',
      type: 'boolean',
      value: config.showFooter,
      description: 'Display the footer component'
    },
    {
      key: 'showThemeSelector',
      label: 'Show Theme Selector',
      type: 'boolean',
      value: config.showThemeSelector,
      description: 'Display the theme selector in header'
    },
    {
      key: 'theme',
      label: 'Default Theme',
      type: 'select',
      value: config.theme,
      options: ['light', 'dark', 'corporate', 'custom'],
      description: 'Default theme for the application'
    }
  ];

  const updateConfig = (key: string, value: any) => {
    setConfig(prev => ({
      ...prev,
      [key]: value
    }));
  };

  const generateLibraryConfig = () => {
    return `const libraryConfig: LibraryConfig = {
  // Basic configuration
  name: '${config.name}',
  logo: '/mattin-small.png',
  favicon: '/favicon.ico',
  
  // Theme configuration
  themeProps: {
    defaultTheme: '${config.theme}',
    customThemes: {
      custom: {
        name: 'custom',
        colors: {
          primary: '${config.primaryColor}',
          secondary: '${config.secondaryColor}',
          accent: '${config.accentColor}',
          background: '#F9FAFB',
          surface: '#FFFFFF',
          text: '#111827'
        }
      }
    },
    showThemeSelector: ${config.showThemeSelector}
  },
  
  // Header configuration
  headerProps: {
    title: '${config.headerTitle}',
    logoUrl: '/mattin-small.png'
  },
  
  // Footer configuration
  footerProps: {
    copyright: '${config.footerCopyright}',
    showVersion: true
  },
  
  // Feature configuration
  features: {
    showHeader: ${config.showHeader},
    showSidebar: ${config.showSidebar},
    showFooter: ${config.showFooter},
    showThemeSelector: ${config.showThemeSelector}
  }
};`;
  };

  const generateAppCode = () => {
    return `import { ExtensibleBaseApp } from '@lksnext/ai-core-tools-base';
import type { ExtraRoute } from '@lksnext/ai-core-tools-base';
import { libraryConfig } from './config/libraryConfig';

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
    <ExtensibleBaseApp 
      config={libraryConfig}
      extraRoutes={extraRoutes}
    />
  );
}

export default App;`;
  };

  useEffect(() => {
    setGeneratedCode(generateLibraryConfig());
  }, [config]);

  const renderConfigOption = (option: ConfigOption) => {
    const { key, label, type, value, options, description } = option;

    return (
      <div key={key} className="space-y-2">
        <label 
          className="block text-sm font-medium"
          style={{ color: theme.colors?.text }}
        >
          {label}
        </label>
        {description && (
          <p 
            className="text-xs"
            style={{ color: theme.colors?.text, opacity: 0.7 }}
          >
            {description}
          </p>
        )}
        
        {type === 'text' && (
          <input
            type="text"
            value={value}
            onChange={(e) => updateConfig(key, e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
            style={{
              backgroundColor: theme.colors?.surface,
              borderColor: theme.colors?.primary + '30',
              color: theme.colors?.text
            }}
          />
        )}
        
        {type === 'color' && (
          <div className="flex items-center space-x-3">
            <input
              type="color"
              value={value}
              onChange={(e) => updateConfig(key, e.target.value)}
              className="w-12 h-8 rounded border-2 border-gray-300 cursor-pointer"
            />
            <input
              type="text"
              value={value}
              onChange={(e) => updateConfig(key, e.target.value)}
              className="flex-1 px-3 py-2 border border-gray-300 rounded-md text-sm font-mono"
              style={{
                backgroundColor: theme.colors?.surface,
                borderColor: theme.colors?.primary + '30',
                color: theme.colors?.text
              }}
            />
          </div>
        )}
        
        {type === 'boolean' && (
          <label className="flex items-center">
            <input
              type="checkbox"
              checked={value}
              onChange={(e) => updateConfig(key, e.target.checked)}
              className="mr-2"
            />
            <span 
              className="text-sm"
              style={{ color: theme.colors?.text }}
            >
              {value ? 'Enabled' : 'Disabled'}
            </span>
          </label>
        )}
        
        {type === 'select' && (
          <select
            value={value}
            onChange={(e) => updateConfig(key, e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
            style={{
              backgroundColor: theme.colors?.surface,
              borderColor: theme.colors?.primary + '30',
              color: theme.colors?.text
            }}
          >
            {options?.map(option => (
              <option key={option} value={option}>
                {option.charAt(0).toUpperCase() + option.slice(1)}
              </option>
            ))}
          </select>
        )}
      </div>
    );
  };

  const renderPreview = () => {
    return (
      <div className="space-y-4">
        <h3 
          className="text-xl font-semibold"
          style={{ color: theme.colors?.primary }}
        >
          Live Preview
        </h3>
        
        <div 
          className="border-2 border-dashed p-4 rounded-lg min-h-96"
          style={{ borderColor: theme.colors?.primary + '40' }}
        >
          <div className="min-h-96 flex flex-col">
            {/* Header Preview */}
            {config.showHeader && (
              <div 
                className="p-4 border-b"
                style={{
                  backgroundColor: config.primaryColor,
                  color: '#ffffff'
                }}
              >
                <div className="flex justify-between items-center">
                  <h1 className="text-xl font-bold">{config.headerTitle}</h1>
                  {config.showThemeSelector && (
                    <div className="text-sm opacity-90">Theme Selector</div>
                  )}
                </div>
              </div>
            )}
            
            {/* Body Preview */}
            <div className="flex flex-1">
              {/* Sidebar Preview */}
              {config.showSidebar && (
                <div 
                  className="w-64 p-4 border-r"
                  style={{
                    backgroundColor: theme.colors?.surface,
                    borderColor: config.primaryColor + '30'
                  }}
                >
                  <h4 
                    className="font-semibold mb-4"
                    style={{ color: config.primaryColor }}
                  >
                    Navigation
                  </h4>
                  <nav className="space-y-2">
                    <div 
                      className="px-3 py-2 rounded text-sm"
                      style={{
                        backgroundColor: config.primaryColor + '10',
                        color: config.primaryColor
                      }}
                    >
                      Dashboard
                    </div>
                    <div className="px-3 py-2 text-sm text-gray-600">Settings</div>
                    <div className="px-3 py-2 text-sm text-gray-600">Profile</div>
                  </nav>
                </div>
              )}
              
              {/* Content Preview */}
              <div className="flex-1 p-6">
                <h2 
                  className="text-2xl font-bold mb-4"
                  style={{ color: config.primaryColor }}
                >
                  Welcome to {config.name}
                </h2>
                <p 
                  className="mb-4"
                  style={{ color: theme.colors?.text, opacity: 0.8 }}
                >
                  This is a preview of how your application will look with the current configuration.
                </p>
                
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div 
                    className="p-4 rounded-lg"
                    style={{
                      backgroundColor: config.primaryColor + '10',
                      border: `1px solid ${config.primaryColor}30`
                    }}
                  >
                    <h3 
                      className="font-semibold mb-2"
                      style={{ color: config.primaryColor }}
                    >
                      Primary Feature
                    </h3>
                    <p 
                      className="text-sm"
                      style={{ color: theme.colors?.text, opacity: 0.8 }}
                    >
                      This card uses your primary color
                    </p>
                  </div>
                  
                  <div 
                    className="p-4 rounded-lg"
                    style={{
                      backgroundColor: config.secondaryColor + '10',
                      border: `1px solid ${config.secondaryColor}30`
                    }}
                  >
                    <h3 
                      className="font-semibold mb-2"
                      style={{ color: config.secondaryColor }}
                    >
                      Secondary Feature
                    </h3>
                    <p 
                      className="text-sm"
                      style={{ color: theme.colors?.text, opacity: 0.8 }}
                    >
                      This card uses your secondary color
                    </p>
                  </div>
                </div>
                
                <div className="mt-4">
                  <button 
                    className="px-4 py-2 rounded text-sm font-medium"
                    style={{
                      backgroundColor: config.accentColor,
                      color: '#ffffff'
                    }}
                  >
                    Call to Action
                  </button>
                </div>
              </div>
            </div>
            
            {/* Footer Preview */}
            {config.showFooter && (
              <div 
                className="p-4 border-t text-center text-sm"
                style={{
                  backgroundColor: theme.colors?.surface,
                  borderColor: config.primaryColor + '20',
                  color: theme.colors?.text
                }}
              >
                {config.footerCopyright}
              </div>
            )}
          </div>
        </div>
      </div>
    );
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
          🛠️ Interactive Configuration Builder
        </h1>
        <p 
          className="text-xl mb-6"
          style={{ color: theme.colors?.text, opacity: 0.8 }}
        >
          Build your AI-Core-Tools configuration interactively and see live previews
        </p>
      </div>

      {/* Mode Selector */}
      <div className="mb-8">
        <div className="flex justify-center space-x-4">
          {[
            { id: 'config', name: 'Configuration', icon: '⚙️' },
            { id: 'preview', name: 'Live Preview', icon: '👁️' },
            { id: 'code', name: 'Generated Code', icon: '💻' }
          ].map((mode) => (
            <button
              key={mode.id}
              onClick={() => setPreviewMode(mode.id as any)}
              className={`px-6 py-3 rounded-lg font-medium transition-all ${
                previewMode === mode.id
                  ? 'client-button'
                  : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
              }`}
            >
              <span className="mr-2">{mode.icon}</span>
              {mode.name}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      {previewMode === 'config' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <div 
            className="p-6 rounded-lg shadow-lg"
            style={{
              backgroundColor: theme.colors?.surface,
              border: `1px solid ${theme.colors?.primary}20`
            }}
          >
            <h2 
              className="text-2xl font-semibold mb-6"
              style={{ color: theme.colors?.primary }}
            >
              Configuration Options
            </h2>
            
            <div className="space-y-6">
              {configOptions.map(renderConfigOption)}
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
              className="text-2xl font-semibold mb-6"
              style={{ color: theme.colors?.secondary }}
            >
              Current Configuration
            </h2>
            
            <div className="space-y-3">
              {Object.entries(config).map(([key, value]) => (
                <div key={key} className="flex justify-between">
                  <span 
                    className="font-medium"
                    style={{ color: theme.colors?.text }}
                  >
                    {key}:
                  </span>
                  <span 
                    className="text-sm font-mono"
                    style={{ color: theme.colors?.text, opacity: 0.8 }}
                  >
                    {typeof value === 'boolean' ? value.toString() : value}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {previewMode === 'preview' && (
        <div 
          className="p-6 rounded-lg shadow-lg"
          style={{
            backgroundColor: theme.colors?.surface,
            border: `1px solid ${theme.colors?.primary}20`
          }}
        >
          {renderPreview()}
        </div>
      )}

      {previewMode === 'code' && (
        <div className="space-y-6">
          <div 
            className="p-6 rounded-lg shadow-lg"
            style={{
              backgroundColor: theme.colors?.surface,
              border: `1px solid ${theme.colors?.primary}20`
            }}
          >
            <h2 
              className="text-2xl font-semibold mb-6"
              style={{ color: theme.colors?.primary }}
            >
              Generated Library Configuration
            </h2>
            
            <pre 
              className="text-xs bg-gray-900 text-green-400 p-4 rounded-lg overflow-x-auto"
              style={{ fontFamily: 'Monaco, Consolas, monospace' }}
            >
              {generatedCode}
            </pre>
          </div>
          
          <div 
            className="p-6 rounded-lg shadow-lg"
            style={{
              backgroundColor: theme.colors?.surface,
              border: `1px solid ${theme.colors?.secondary}20`
            }}
          >
            <h2 
              className="text-2xl font-semibold mb-6"
              style={{ color: theme.colors?.secondary }}
            >
              Generated App Component
            </h2>
            
            <pre 
              className="text-xs bg-gray-900 text-blue-400 p-4 rounded-lg overflow-x-auto"
              style={{ fontFamily: 'Monaco, Consolas, monospace' }}
            >
              {generateAppCode()}
            </pre>
          </div>
        </div>
      )}

      {/* Action Buttons */}
      <div className="mt-8 flex justify-center space-x-4">
        <button 
          className="client-button px-6 py-3 rounded-lg font-semibold"
          onClick={() => {
            navigator.clipboard.writeText(generatedCode);
            alert('Configuration copied to clipboard!');
          }}
        >
          📋 Copy Configuration
        </button>
        <button 
          className="px-6 py-3 rounded-lg font-semibold border-2 transition-all hover:scale-105"
          style={{
            borderColor: theme.colors?.secondary,
            color: theme.colors?.secondary
          }}
          onClick={() => {
            const blob = new Blob([generatedCode], { type: 'text/plain' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'libraryConfig.ts';
            a.click();
            URL.revokeObjectURL(url);
          }}
        >
          💾 Download Config
        </button>
      </div>
    </div>
  );
};

export default InteractiveDemo;
