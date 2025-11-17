import React from 'react';
import ClientCard from '../components/ui/ClientCard';

const CustomPage: React.FC = () => {
  return (
    <div className="max-w-4xl mx-auto p-6">
      <h1 className="text-3xl font-bold text-gray-900 mb-6">
        Custom Client Page
      </h1>
      <div className="bg-white rounded-lg shadow p-6">
        <p className="text-gray-600 mb-6">
          This is a custom page specific to your client implementation. 
          It demonstrates how to use custom components and integrate with the theme system.
        </p>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <ClientCard
            title="Custom Feature 1"
            description="A reusable component that adapts to your theme"
            icon="🚀"
            onClick={() => alert('Feature 1 clicked!')}
          />
          <ClientCard
            title="Custom Feature 2"
            description="Another example of theme integration"
            icon="⚡"
            onClick={() => alert('Feature 2 clicked!')}
          />
        </div>
      </div>
    </div>
  );
};

export default CustomPage;
