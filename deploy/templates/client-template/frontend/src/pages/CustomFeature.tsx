import React from 'react';
import { useTheme } from '@lksnext/ai-core-tools-base';

const CustomFeature: React.FC = () => {
  const { theme } = useTheme();

  return (
    <div className="max-w-4xl mx-auto p-6">
      <h1 className="text-3xl font-bold text-gray-900 mb-6">
        Custom Feature
      </h1>
      <div className="bg-white rounded-lg shadow p-6">
        <div className="mb-6">
          <h2 className="text-xl font-semibold text-gray-800 mb-4">
            Welcome to Your Custom Feature!
          </h2>
          <p className="text-gray-600 mb-4">
            This is a custom feature specific to your client implementation. 
            You can build unique functionality here that extends the base AI Core Tools platform.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
          <div 
            className="p-4 rounded-lg"
            style={{ 
              backgroundColor: theme.colors?.primary + '20',
              border: `1px solid ${theme.colors?.primary}40`
            }}
          >
            <h3 className="font-semibold mb-2" style={{ color: theme.colors?.primary }}>
              Feature 1
            </h3>
            <p style={{ color: theme.colors?.text }}>
              Custom functionality that uses your client's theme colors
            </p>
          </div>
          <div 
            className="p-4 rounded-lg"
            style={{ 
              backgroundColor: theme.colors?.secondary + '20',
              border: `1px solid ${theme.colors?.secondary}40`
            }}
          >
            <h3 className="font-semibold mb-2" style={{ color: theme.colors?.secondary }}>
              Feature 2
            </h3>
            <p style={{ color: theme.colors?.text }}>
              Another custom feature with theme integration
            </p>
          </div>
        </div>

        <div className="bg-gray-50 p-4 rounded-lg">
          <h3 className="font-semibold text-gray-800 mb-2">Client Information</h3>
          <p className="text-sm text-gray-600">
            <strong>Client ID:</strong> {theme.name}<br/>
            <strong>Theme:</strong> {theme.name}<br/>
            <strong>Primary Color:</strong> {theme.colors?.primary}
          </p>
        </div>
      </div>
    </div>
  );
};

export default CustomFeature;
