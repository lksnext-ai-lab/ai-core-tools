import React, { useState, useEffect } from 'react';

export interface HelloWorldPageProps {
  welcomeMessage?: string;
}

/**
 * Hello World Page Component
 * 
 * This is a sample page component that demonstrates:
 * - Basic React component structure
 * - State management with hooks
 * - Interactive UI elements
 * - Plugin integration patterns
 */
export const HelloWorldPage: React.FC<HelloWorldPageProps> = ({ 
  welcomeMessage = 'Welcome to the Hello World Plugin!' 
}) => {
  const [count, setCount] = useState(0);
  const [currentTime, setCurrentTime] = useState(new Date());
  const [userName, setUserName] = useState('');

  // Update time every second
  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentTime(new Date());
    }, 1000);

    return () => clearInterval(timer);
  }, []);

  const handleIncrement = () => {
    setCount(prev => prev + 1);
  };

  const handleReset = () => {
    setCount(0);
  };

  const handleNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setUserName(e.target.value);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 p-8">
      <div className="max-w-4xl mx-auto">
        {/* Header Section */}
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-gray-900 mb-4">
            {welcomeMessage}
          </h1>
          <p className="text-lg text-gray-600">
            This is a sample plugin demonstrating the AI-Core-Tools plugin architecture
          </p>
        </div>

        {/* Main Content Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-8">
          {/* Interactive Counter Card */}
          <div className="bg-white rounded-lg shadow-lg p-6">
            <h2 className="text-2xl font-semibold text-gray-800 mb-4 flex items-center">
              <span className="mr-2">🔢</span>
              Interactive Counter
            </h2>
            <div className="text-center">
              <div className="text-6xl font-bold text-blue-600 mb-4">
                {count}
              </div>
              <div className="space-x-4">
                <button
                  onClick={handleIncrement}
                  className="bg-blue-500 hover:bg-blue-600 text-white font-semibold py-2 px-4 rounded-lg transition-colors"
                >
                  Increment
                </button>
                <button
                  onClick={handleReset}
                  className="bg-gray-500 hover:bg-gray-600 text-white font-semibold py-2 px-4 rounded-lg transition-colors"
                >
                  Reset
                </button>
              </div>
            </div>
          </div>

          {/* Real-time Clock Card */}
          <div className="bg-white rounded-lg shadow-lg p-6">
            <h2 className="text-2xl font-semibold text-gray-800 mb-4 flex items-center">
              <span className="mr-2">🕐</span>
              Real-time Clock
            </h2>
            <div className="text-center">
              <div className="text-3xl font-mono text-green-600 mb-2">
                {currentTime.toLocaleTimeString()}
              </div>
              <div className="text-lg text-gray-600">
                {currentTime.toLocaleDateString()}
              </div>
            </div>
          </div>
        </div>

        {/* User Input Section */}
        <div className="bg-white rounded-lg shadow-lg p-6 mb-8">
          <h2 className="text-2xl font-semibold text-gray-800 mb-4 flex items-center">
            <span className="mr-2">👤</span>
            Personal Greeting
          </h2>
          <div className="max-w-md mx-auto">
            <input
              type="text"
              placeholder="Enter your name..."
              value={userName}
              onChange={handleNameChange}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
            {userName && (
              <div className="mt-4 text-center">
                <p className="text-lg text-gray-700">
                  Hello, <span className="font-semibold text-blue-600">{userName}</span>! 👋
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Plugin Information */}
        <div className="bg-gradient-to-r from-purple-500 to-pink-500 rounded-lg shadow-lg p-6 text-white">
          <h2 className="text-2xl font-semibold mb-4 flex items-center">
            <span className="mr-2">🔌</span>
            Plugin Information
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-center">
            <div>
              <div className="text-sm opacity-90">Plugin Name</div>
              <div className="font-semibold">Hello World Plugin</div>
            </div>
            <div>
              <div className="text-sm opacity-90">Version</div>
              <div className="font-semibold">1.0.0</div>
            </div>
            <div>
              <div className="text-sm opacity-90">Status</div>
              <div className="font-semibold text-green-200">Active</div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="text-center mt-8 text-gray-500">
          <p>
            This plugin demonstrates how to create custom pages for the AI-Core-Tools framework.
            Check out the admin page for more advanced features!
          </p>
        </div>
      </div>
    </div>
  );
};
