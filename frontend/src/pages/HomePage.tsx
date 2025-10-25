import React from 'react';
import { Link } from 'react-router-dom';
import { useUser } from '../contexts/UserContext';

function HomePage() {
  const { user } = useUser();

  return (
    <div className="max-w-6xl mx-auto p-6">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-4">
          Welcome to AI Core Tools
        </h1>
        <p className="text-lg text-gray-600">
          {user?.name ? `Hello ${user.name}!` : 'Hello!'} Manage your AI applications, agents, and data sources from one central location.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
        {/* Quick Actions */}
        <div className="bg-white rounded-lg shadow-md border p-6">
          <div className="flex items-center mb-4">
            <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center">
              <span className="text-2xl">📱</span>
            </div>
            <h3 className="text-lg font-semibold text-gray-900 ml-4">My Apps</h3>
          </div>
          <p className="text-gray-600 text-sm mb-4">
            View and manage all your AI applications in one place.
          </p>
          <Link 
            to="/apps"
            className="block w-full bg-blue-600 hover:bg-blue-700 text-white text-center py-2 px-4 rounded-lg transition-colors"
          >
            Go to Apps →
          </Link>
        </div>

        {/* Administration */}
        {user?.is_admin && (
          <div className="bg-white rounded-lg shadow-md border p-6">
            <div className="flex items-center mb-4">
              <div className="w-12 h-12 bg-green-100 rounded-lg flex items-center justify-center">
                <span className="text-2xl">👥</span>
              </div>
              <h3 className="text-lg font-semibold text-gray-900 ml-4">Users</h3>
            </div>
            <p className="text-gray-600 text-sm mb-4">
              Manage user accounts and permissions.
            </p>
            <Link 
              to="/admin/users"
              className="block w-full bg-green-600 hover:bg-green-700 text-white text-center py-2 px-4 rounded-lg transition-colors"
            >
              Manage Users →
            </Link>
          </div>
        )}

        {/* Statistics */}
        {user?.is_admin && (
          <div className="bg-white rounded-lg shadow-md border p-6">
            <div className="flex items-center mb-4">
              <div className="w-12 h-12 bg-purple-100 rounded-lg flex items-center justify-center">
                <span className="text-2xl">📊</span>
              </div>
              <h3 className="text-lg font-semibold text-gray-900 ml-4">Statistics</h3>
            </div>
            <p className="text-gray-600 text-sm mb-4">
              View system usage and performance metrics.
            </p>
            <Link 
              to="/admin/stats"
              className="block w-full bg-purple-600 hover:bg-purple-700 text-white text-center py-2 px-4 rounded-lg transition-colors"
            >
              View Stats →
            </Link>
          </div>
        )}

        {/* About */}
        <div className="bg-white rounded-lg shadow-md border p-6">
          <div className="flex items-center mb-4">
            <div className="w-12 h-12 bg-gray-100 rounded-lg flex items-center justify-center">
              <span className="text-2xl">ℹ️</span>
            </div>
            <h3 className="text-lg font-semibold text-gray-900 ml-4">About</h3>
          </div>
          <p className="text-gray-600 text-sm mb-4">
            Learn more about AI Core Tools and its features.
          </p>
          <Link 
            to="/about"
            className="block w-full bg-gray-600 hover:bg-gray-700 text-white text-center py-2 px-4 rounded-lg transition-colors"
          >
            Learn More →
          </Link>
        </div>
      </div>

      {/* Getting Started Section */}
      <div className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg p-6">
        <h2 className="text-xl font-semibold text-gray-900 mb-4">Getting Started</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="flex items-start space-x-3">
            <div className="w-6 h-6 bg-blue-500 text-white rounded-full flex items-center justify-center text-sm font-medium">1</div>
            <div>
              <h3 className="font-medium text-gray-900">Create Your First App</h3>
              <p className="text-sm text-gray-600">Start by creating an AI application to organize your projects.</p>
            </div>
          </div>
          <div className="flex items-start space-x-3">
            <div className="w-6 h-6 bg-blue-500 text-white rounded-full flex items-center justify-center text-sm font-medium">2</div>
            <div>
              <h3 className="font-medium text-gray-900">Add AI Agents</h3>
              <p className="text-sm text-gray-600">Configure intelligent agents to handle specific tasks.</p>
            </div>
          </div>
          <div className="flex items-start space-x-3">
            <div className="w-6 h-6 bg-blue-500 text-white rounded-full flex items-center justify-center text-sm font-medium">3</div>
            <div>
              <h3 className="font-medium text-gray-900">Connect Data Sources</h3>
              <p className="text-sm text-gray-600">Link repositories, silos, and domains to your agents.</p>
            </div>
          </div>
          <div className="flex items-start space-x-3">
            <div className="w-6 h-6 bg-blue-500 text-white rounded-full flex items-center justify-center text-sm font-medium">4</div>
            <div>
              <h3 className="font-medium text-gray-900">Deploy & Monitor</h3>
              <p className="text-sm text-gray-600">Launch your AI solutions and track their performance.</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default HomePage;
