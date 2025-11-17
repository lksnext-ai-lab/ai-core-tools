import React, { useState, useEffect } from 'react';
import { useTheme, ThemeSelector } from '@lksnext/ai-core-tools-base';

const ThemeCustomizationDemo: React.FC = () => {
  const { theme } = useTheme();
  const [customTheme, setCustomTheme] = useState({
    primary: '#3B82F6',
    secondary: '#1E40AF',
    accent: '#F59E0B',
    background: '#F9FAFB',
    surface: '#FFFFFF',
    text: '#111827'
  });
  const [previewTheme, setPreviewTheme] = useState<any>(null);

  // Generate theme preview
  useEffect(() => {
    setPreviewTheme({
      name: 'custom-preview',
      colors: customTheme
    });
  }, [customTheme]);

  const handleColorChange = (colorKey: string, value: string) => {
    setCustomTheme(prev => ({
      ...prev,
      [colorKey]: value
    }));
  };

  const predefinedThemes = [
    {
      name: 'Ocean Blue',
      colors: {
        primary: '#0EA5E9',
        secondary: '#0284C7',
        accent: '#F59E0B',
        background: '#F0F9FF',
        surface: '#FFFFFF',
        text: '#0C4A6E'
      }
    },
    {
      name: 'Forest Green',
      colors: {
        primary: '#10B981',
        secondary: '#059669',
        accent: '#F59E0B',
        background: '#F0FDF4',
        surface: '#FFFFFF',
        text: '#064E3B'
      }
    },
    {
      name: 'Sunset Orange',
      colors: {
        primary: '#F97316',
        secondary: '#EA580C',
        accent: '#8B5CF6',
        background: '#FFF7ED',
        surface: '#FFFFFF',
        text: '#9A3412'
      }
    },
    {
      name: 'Royal Purple',
      colors: {
        primary: '#8B5CF6',
        secondary: '#7C3AED',
        accent: '#F59E0B',
        background: '#FAF5FF',
        surface: '#FFFFFF',
        text: '#581C87'
      }
    }
  ];

  const colorInputs = [
    { key: 'primary', label: 'Primary Color', description: 'Main brand color' },
    { key: 'secondary', label: 'Secondary Color', description: 'Supporting brand color' },
    { key: 'accent', label: 'Accent Color', description: 'Highlight and call-to-action color' },
    { key: 'background', label: 'Background Color', description: 'Main background color' },
    { key: 'surface', label: 'Surface Color', description: 'Card and panel background' },
    { key: 'text', label: 'Text Color', description: 'Primary text color' }
  ];

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
          🎨 Advanced Theme Customization
        </h1>
        <p 
          className="text-xl mb-6"
          style={{ color: theme.colors?.text, opacity: 0.8 }}
        >
          Create, preview, and apply custom themes with real-time updates
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Theme Builder */}
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
            🛠️ Custom Theme Builder
          </h2>
          
          <div className="space-y-4">
            {colorInputs.map(({ key, label, description }) => (
              <div key={key}>
                <label 
                  className="block text-sm font-medium mb-2"
                  style={{ color: theme.colors?.text }}
                >
                  {label}
                </label>
                <p 
                  className="text-xs mb-2"
                  style={{ color: theme.colors?.text, opacity: 0.7 }}
                >
                  {description}
                </p>
                <div className="flex items-center space-x-3">
                  <input
                    type="color"
                    value={customTheme[key as keyof typeof customTheme]}
                    onChange={(e) => handleColorChange(key, e.target.value)}
                    className="w-12 h-8 rounded border-2 border-gray-300 cursor-pointer"
                  />
                  <input
                    type="text"
                    value={customTheme[key as keyof typeof customTheme]}
                    onChange={(e) => handleColorChange(key, e.target.value)}
                    className="flex-1 px-3 py-2 border border-gray-300 rounded-md text-sm font-mono"
                    placeholder="#000000"
                  />
                </div>
              </div>
            ))}
          </div>

          <div className="mt-6 pt-6 border-t border-gray-200">
            <h3 
              className="text-lg font-semibold mb-3"
              style={{ color: theme.colors?.text }}
            >
              Generated Theme Code:
            </h3>
            <pre 
              className="text-xs bg-gray-900 text-green-400 p-4 rounded-lg overflow-x-auto"
              style={{ fontFamily: 'Monaco, Consolas, monospace' }}
            >
{`const customTheme: ThemeConfig = {
  name: 'my-custom-theme',
  colors: {
    primary: '${customTheme.primary}',
    secondary: '${customTheme.secondary}',
    accent: '${customTheme.accent}',
    background: '${customTheme.background}',
    surface: '${customTheme.surface}',
    text: '${customTheme.text}'
  }
};`}
            </pre>
          </div>
        </div>

        {/* Live Preview */}
        <div 
          className="p-6 rounded-lg shadow-lg"
          style={{
            backgroundColor: previewTheme?.colors?.surface || theme.colors?.surface,
            border: `1px solid ${previewTheme?.colors?.primary || theme.colors?.primary}20`
          }}
        >
          <h2 
            className="text-2xl font-semibold mb-6"
            style={{ color: previewTheme?.colors?.primary || theme.colors?.primary }}
          >
            👁️ Live Preview
          </h2>
          
          <div className="space-y-4">
            {/* Preview Header */}
            <div 
              className="p-4 rounded-lg"
              style={{
                backgroundColor: previewTheme?.colors?.primary || theme.colors?.primary,
                color: '#ffffff'
              }}
            >
              <h3 className="font-semibold">Preview Header</h3>
              <p className="text-sm opacity-90">This is how your header will look</p>
            </div>

            {/* Preview Card */}
            <div 
              className="p-4 rounded-lg border"
              style={{
                backgroundColor: previewTheme?.colors?.surface || theme.colors?.surface,
                borderColor: previewTheme?.colors?.primary || theme.colors?.primary,
                color: previewTheme?.colors?.text || theme.colors?.text
              }}
            >
              <h4 
                className="font-semibold mb-2"
                style={{ color: previewTheme?.colors?.primary || theme.colors?.primary }}
              >
                Preview Card
              </h4>
              <p className="text-sm mb-3">
                This card shows how your content will appear with the selected colors.
              </p>
              <button 
                className="px-4 py-2 rounded text-sm font-medium"
                style={{
                  backgroundColor: previewTheme?.colors?.accent || theme.colors?.accent,
                  color: '#ffffff'
                }}
              >
                Sample Button
              </button>
            </div>

            {/* Color Palette */}
            <div>
              <h4 
                className="font-semibold mb-3"
                style={{ color: previewTheme?.colors?.text || theme.colors?.text }}
              >
                Color Palette:
              </h4>
              <div className="grid grid-cols-2 gap-2">
                {Object.entries(previewTheme?.colors || {}).map(([key, value]) => (
                  <div key={key} className="flex items-center space-x-2">
                    <div 
                      className="w-6 h-6 rounded border"
                      style={{ backgroundColor: value as string }}
                    />
                    <span 
                      className="text-xs font-mono"
                      style={{ color: previewTheme?.colors?.text || theme.colors?.text }}
                    >
                      {key}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Predefined Themes */}
      <div className="mt-8">
        <h2 
          className="text-2xl font-semibold mb-6"
          style={{ color: theme.colors?.text }}
        >
          🎨 Predefined Theme Collection
        </h2>
        
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {predefinedThemes.map((predefinedTheme) => (
            <div 
              key={predefinedTheme.name}
              className="p-4 rounded-lg border cursor-pointer transition-all hover:scale-105 hover:shadow-lg"
              style={{
                backgroundColor: theme.colors?.surface,
                borderColor: theme.colors?.primary + '30'
              }}
              onClick={() => setCustomTheme(predefinedTheme.colors)}
            >
              <div className="mb-3">
                <h3 
                  className="font-semibold"
                  style={{ color: theme.colors?.text }}
                >
                  {predefinedTheme.name}
                </h3>
              </div>
              
              <div className="space-y-2">
                <div 
                  className="h-8 rounded"
                  style={{ backgroundColor: predefinedTheme.colors.primary }}
                />
                <div 
                  className="h-6 rounded"
                  style={{ backgroundColor: predefinedTheme.colors.secondary }}
                />
                <div 
                  className="h-4 rounded"
                  style={{ backgroundColor: predefinedTheme.colors.accent }}
                />
              </div>
              
              <button 
                className="w-full mt-3 px-3 py-2 text-sm rounded transition-all"
                style={{
                  backgroundColor: theme.colors?.primary,
                  color: '#ffffff'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.opacity = '0.9';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.opacity = '1';
                }}
              >
                Use This Theme
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Theme Selector Demo */}
      <div className="mt-8">
        <h2 
          className="text-2xl font-semibold mb-6"
          style={{ color: theme.colors?.text }}
        >
          🔄 Theme Switching
        </h2>
        
        <div 
          className="p-6 rounded-lg"
          style={{
            backgroundColor: theme.colors?.surface,
            border: `1px solid ${theme.colors?.primary}20`
          }}
        >
          <p 
            className="mb-4"
            style={{ color: theme.colors?.text, opacity: 0.8 }}
          >
            The library includes a built-in theme selector component:
          </p>
          
          <div className="flex items-center space-x-4">
            <ThemeSelector />
            <span 
              className="text-sm"
              style={{ color: theme.colors?.text, opacity: 0.7 }}
            >
              Current theme: <strong>{theme.name}</strong>
            </span>
          </div>
        </div>
      </div>

      {/* Integration Examples */}
      <div className="mt-8">
        <h2 
          className="text-2xl font-semibold mb-6"
          style={{ color: theme.colors?.text }}
        >
          🔧 Integration Examples
        </h2>
        
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
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
              Library Configuration
            </h3>
            <pre 
              className="text-xs bg-gray-900 text-blue-400 p-4 rounded-lg overflow-x-auto"
              style={{ fontFamily: 'Monaco, Consolas, monospace' }}
            >
{`const config: LibraryConfig = {
  themeProps: {
    defaultTheme: 'custom',
    customThemes: {
      custom: customTheme,
      corporate: corporateTheme
    },
    showThemeSelector: true
  }
};`}
            </pre>
          </div>
          
          <div 
            className="p-6 rounded-lg"
            style={{
              backgroundColor: theme.colors?.surface,
              border: `1px solid ${theme.colors?.secondary}20`
            }}
          >
            <h3 
              className="text-lg font-semibold mb-4"
              style={{ color: theme.colors?.secondary }}
            >
              Component Usage
            </h3>
            <pre 
              className="text-xs bg-gray-900 text-green-400 p-4 rounded-lg overflow-x-auto"
              style={{ fontFamily: 'Monaco, Consolas, monospace' }}
            >
{`import { useTheme } from '@lksnext/ai-core-tools-base';

const MyComponent = () => {
  const { theme, switchTheme } = useTheme();
  
  return (
    <div style={{ color: theme.colors?.text }}>
      <button 
        onClick={() => switchTheme('dark')}
        style={{ backgroundColor: theme.colors?.primary }}
      >
        Switch Theme
      </button>
    </div>
  );
};`}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ThemeCustomizationDemo;
