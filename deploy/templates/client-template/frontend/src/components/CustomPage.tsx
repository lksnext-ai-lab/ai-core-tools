import React from 'react';

const CustomPage: React.FC = () => {
  return (
    <div className="max-w-4xl mx-auto p-6">
      <h1 className="text-3xl font-bold text-gray-900 mb-6">
        Custom Client Page
      </h1>
      <div className="bg-white rounded-lg shadow p-6">
        <p className="text-gray-600 mb-4">
          This is a custom page specific to your client implementation.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="bg-blue-50 p-4 rounded-lg">
            <h3 className="font-semibold text-blue-900 mb-2">Feature 1</h3>
            <p className="text-blue-700">Custom functionality for your client</p>
          </div>
          <div className="bg-green-50 p-4 rounded-lg">
            <h3 className="font-semibold text-green-900 mb-2">Feature 2</h3>
            <p className="text-green-700">Another custom feature</p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default CustomPage;
