import React from 'react';
import { useTheme } from '@lksnext/ai-core-tools-base';
import ClientCard from '../components/ui/ClientCard';

const CustomHomePage: React.FC = () => {
  const { theme } = useTheme();

  return (
    <div className="max-w-6xl mx-auto p-6">
      {/* Hero Section */}
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
          Welcome to {theme.name}
        </h1>
        <p 
          className="text-xl mb-6"
          style={{ color: theme.colors?.text, opacity: 0.8 }}
        >
          Your custom AI-powered platform
        </p>
        <div 
          className="inline-flex items-center px-6 py-3 rounded-lg font-semibold"
          style={{
            backgroundColor: theme.colors?.primary,
            color: '#ffffff'
          }}
        >
          🚀 Get Started
        </div>
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
        <ClientCard
          title="My Apps"
          description="Manage your AI applications"
          icon="📱"
          onClick={() => window.location.href = '/apps'}
        />
        <ClientCard
          title="Custom Feature"
          description="Explore your custom features"
          icon="⭐"
          onClick={() => window.location.href = '/custom-feature'}
        />
        <ClientCard
          title="Settings"
          description="Configure your preferences"
          icon="⚙️"
          onClick={() => window.location.href = '/apps/1/settings'}
        />
      </div>

      {/* Client-specific content */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 
          className="text-2xl font-semibold mb-4"
          style={{ color: theme.colors?.text }}
        >
          Your Custom Dashboard
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div 
            className="p-4 rounded-lg"
            style={{
              backgroundColor: theme.colors?.primary + '10',
              border: `1px solid ${theme.colors?.primary}30`
            }}
          >
            <h3 
              className="font-semibold mb-2"
              style={{ color: theme.colors?.primary }}
            >
              Recent Activity
            </h3>
            <p 
              className="text-sm"
              style={{ color: theme.colors?.text, opacity: 0.8 }}
            >
              Your recent AI interactions and results will appear here.
            </p>
          </div>
          <div 
            className="p-4 rounded-lg"
            style={{
              backgroundColor: theme.colors?.secondary + '10',
              border: `1px solid ${theme.colors?.secondary}30`
            }}
          >
            <h3 
              className="font-semibold mb-2"
              style={{ color: theme.colors?.secondary }}
            >
              Quick Stats
            </h3>
            <p 
              className="text-sm"
              style={{ color: theme.colors?.text, opacity: 0.8 }}
            >
              Overview of your platform usage and performance.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default CustomHomePage;
