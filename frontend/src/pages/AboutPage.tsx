import React from 'react';
import { Link } from 'react-router-dom';

const AboutPage: React.FC = () => {
  return (
    <div className="max-w-6xl mx-auto p-8">
      {/* Hero Section */}
      <div className="text-center mb-12">
        <div className="flex justify-center mb-6">
          <div className="w-24 h-24 bg-gradient-to-br from-blue-500 to-purple-600 rounded-2xl flex items-center justify-center shadow-lg">
            <span className="text-4xl">🤖</span>
          </div>
        </div>
        <h1 className="text-5xl font-bold text-gray-900 mb-4">
          Mattin AI
        </h1>
        <p className="text-xl text-gray-600 mb-6">
          Your Comprehensive AI Toolbox
        </p>
        <p className="text-lg text-gray-700 max-w-3xl mx-auto">
          A powerful, extensible platform that simplifies the integration and use of AI technologies, 
          providing a unified solution for building intelligent applications with ease.
        </p>
      </div>

      {/* Overview Section */}
      <div className="bg-white rounded-xl shadow-lg border p-8 mb-8">
        <h2 className="text-3xl font-bold text-gray-900 mb-6">What is Mattin AI?</h2>
        <div className="grid md:grid-cols-2 gap-8">
          <div>
            <p className="text-lg text-gray-700 mb-4">
              Mattin AI is a comprehensive AI toolbox developed by LKS Next that provides a wide range 
              of artificial intelligence capabilities and tools. Built with modern technologies and 
              designed for scalability, it offers everything you need to build, deploy, and manage 
              AI-powered applications.
            </p>
            <p className="text-lg text-gray-700 mb-4">
              Whether you're a developer looking to integrate AI into your applications, a data scientist 
              working with vector databases, or an organization seeking to leverage AI agents and 
              automation, Mattin AI provides the tools and infrastructure you need.
            </p>
          </div>
          <div className="bg-gradient-to-br from-blue-50 to-purple-50 rounded-lg p-6">
            <h3 className="text-xl font-semibold text-gray-900 mb-4">Key Highlights</h3>
            <ul className="space-y-3">
              <li className="flex items-center">
                <span className="w-2 h-2 bg-blue-500 rounded-full mr-3" />
                <span className="text-gray-700">Open source with commercial licensing options</span>
              </li>
              <li className="flex items-center">
                <span className="w-2 h-2 bg-blue-500 rounded-full mr-3" />
                <span className="text-gray-700">Extensible architecture for custom solutions</span>
              </li>
              <li className="flex items-center">
                <span className="w-2 h-2 bg-blue-500 rounded-full mr-3" />
                <span className="text-gray-700">Multi-provider AI service integration</span>
              </li>
              <li className="flex items-center">
                <span className="w-2 h-2 bg-blue-500 rounded-full mr-3" />
                <span className="text-gray-700">Production-ready with enterprise features</span>
              </li>
            </ul>
          </div>
        </div>
      </div>

      {/* Features Section */}
      <div className="bg-white rounded-xl shadow-lg border p-8 mb-8">
        <h2 className="text-3xl font-bold text-gray-900 mb-8 text-center">Core Features</h2>
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          <div className="bg-gradient-to-br from-green-50 to-emerald-50 rounded-lg p-6 border border-green-200">
            <div className="w-12 h-12 bg-green-500 rounded-lg flex items-center justify-center mb-4">
              <span className="text-2xl">🧠</span>
            </div>
            <h3 className="text-xl font-semibold text-gray-900 mb-3">LLM Integration</h3>
            <p className="text-gray-700">
              Easy access and management of various Large Language Models including OpenAI, Anthropic, 
              Azure OpenAI, Mistral AI, and Ollama for local deployment.
            </p>
          </div>

          <div className="bg-gradient-to-br from-blue-50 to-cyan-50 rounded-lg p-6 border border-blue-200">
            <div className="w-12 h-12 bg-blue-500 rounded-lg flex items-center justify-center mb-4">
              <span className="text-2xl">🔍</span>
            </div>
            <h3 className="text-xl font-semibold text-gray-900 mb-3">RAG Systems</h3>
            <p className="text-gray-700">
              Implementation of Retrieval-Augmented Generation for enhanced AI responses with 
              semantic search capabilities and intelligent document processing.
            </p>
          </div>

          <div className="bg-gradient-to-br from-purple-50 to-pink-50 rounded-lg p-6 border border-purple-200">
            <div className="w-12 h-12 bg-purple-500 rounded-lg flex items-center justify-center mb-4">
              <span className="text-2xl">🗄️</span>
            </div>
            <h3 className="text-xl font-semibold text-gray-900 mb-3">Vector Databases</h3>
            <p className="text-gray-700">
              Efficient storage and retrieval of vector embeddings using PostgreSQL with pgvector 
              extension for high-performance semantic search.
            </p>
          </div>

          <div className="bg-gradient-to-br from-orange-50 to-red-50 rounded-lg p-6 border border-orange-200">
            <div className="w-12 h-12 bg-orange-500 rounded-lg flex items-center justify-center mb-4">
              <span className="text-2xl">🤖</span>
            </div>
            <h3 className="text-xl font-semibold text-gray-900 mb-3">AI Agents</h3>
            <p className="text-gray-700">
              Framework for building and deploying intelligent AI agents with customizable 
              workflows, tool integration, and automated decision-making capabilities.
            </p>
          </div>

          <div className="bg-gradient-to-br from-indigo-50 to-blue-50 rounded-lg p-6 border border-indigo-200">
            <div className="w-12 h-12 bg-indigo-500 rounded-lg flex items-center justify-center mb-4">
              <span className="text-2xl">🔧</span>
            </div>
            <h3 className="text-xl font-semibold text-gray-900 mb-3">Modular Architecture</h3>
            <p className="text-gray-700">
              Easy to extend and customize for specific needs with a plugin-based architecture 
              and comprehensive API for third-party integrations.
            </p>
          </div>

          <div className="bg-gradient-to-br from-teal-50 to-green-50 rounded-lg p-6 border border-teal-200">
            <div className="w-12 h-12 bg-teal-500 rounded-lg flex items-center justify-center mb-4">
              <span className="text-2xl">⚡</span>
            </div>
            <h3 className="text-xl font-semibold text-gray-900 mb-3">High Performance</h3>
            <p className="text-gray-700">
              Built with FastAPI and React for optimal performance, with async processing, 
              caching, and scalable infrastructure for enterprise workloads.
            </p>
          </div>
        </div>
      </div>

      {/* Architecture Section */}
      <div className="bg-white rounded-xl shadow-lg border p-8 mb-8">
        <h2 className="text-3xl font-bold text-gray-900 mb-8 text-center">Architecture Overview</h2>
        <div className="grid lg:grid-cols-2 gap-8">
          <div>
            <h3 className="text-xl font-semibold text-gray-900 mb-4">Technology Stack</h3>
            <div className="space-y-4">
              <div className="flex items-center p-4 bg-gray-50 rounded-lg">
                <div className="w-10 h-10 bg-green-500 rounded-lg flex items-center justify-center mr-4">
                  <span className="text-white font-bold">P</span>
                </div>
                <div>
                  <h4 className="font-semibold text-gray-900">Backend</h4>
                  <p className="text-gray-600">FastAPI with Python 3.11+</p>
                </div>
              </div>
              <div className="flex items-center p-4 bg-gray-50 rounded-lg">
                <div className="w-10 h-10 bg-blue-500 rounded-lg flex items-center justify-center mr-4">
                  <span className="text-white font-bold">R</span>
                </div>
                <div>
                  <h4 className="font-semibold text-gray-900">Frontend</h4>
                  <p className="text-gray-600">React with TypeScript</p>
                </div>
              </div>
              <div className="flex items-center p-4 bg-gray-50 rounded-lg">
                <div className="w-10 h-10 bg-purple-500 rounded-lg flex items-center justify-center mr-4">
                  <span className="text-white font-bold">DB</span>
                </div>
                <div>
                  <h4 className="font-semibold text-gray-900">Database</h4>
                  <p className="text-gray-600">PostgreSQL with pgvector</p>
                </div>
              </div>
              <div className="flex items-center p-4 bg-gray-50 rounded-lg">
                <div className="w-10 h-10 bg-orange-500 rounded-lg flex items-center justify-center mr-4">
                  <span className="text-white font-bold">AI</span>
                </div>
                <div>
                  <h4 className="font-semibold text-gray-900">AI Services</h4>
                  <p className="text-gray-600">Multi-provider LLM integration</p>
                </div>
              </div>
            </div>
          </div>
          <div>
            <h3 className="text-xl font-semibold text-gray-900 mb-4">Key Components</h3>
            <div className="space-y-3">
              <div className="flex items-start">
                <div className="w-3 h-3 bg-blue-500 rounded-full mt-2 mr-3"></div>
                <div>
                  <h4 className="font-semibold text-gray-900">REST API</h4>
                  <p className="text-gray-600 text-sm">Comprehensive API for all platform functionality</p>
                </div>
              </div>
              <div className="flex items-start">
                <div className="w-3 h-3 bg-green-500 rounded-full mt-2 mr-3"></div>
                <div>
                  <h4 className="font-semibold text-gray-900">Authentication</h4>
                  <p className="text-gray-600 text-sm">Secure user management and session handling</p>
                </div>
              </div>
              <div className="flex items-start">
                <div className="w-3 h-3 bg-purple-500 rounded-full mt-2 mr-3"></div>
                <div>
                  <h4 className="font-semibold text-gray-900">Vector Storage</h4>
                  <p className="text-gray-600 text-sm">High-performance semantic search capabilities</p>
                </div>
              </div>
              <div className="flex items-start">
                <div className="w-3 h-3 bg-orange-500 rounded-full mt-2 mr-3"></div>
                <div>
                  <h4 className="font-semibold text-gray-900">Agent Framework</h4>
                  <p className="text-gray-600 text-sm">Extensible AI agent development platform</p>
                </div>
              </div>
              <div className="flex items-start">
                <div className="w-3 h-3 bg-teal-500 rounded-full mt-2 mr-3"></div>
                <div>
                  <h4 className="font-semibold text-gray-900">Web Interface</h4>
                  <p className="text-gray-600 text-sm">Intuitive React-based user interface</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Licensing Section */}
      <div className="bg-white rounded-xl shadow-lg border p-8 mb-8">
        <h2 className="text-3xl font-bold text-gray-900 mb-6 text-center">Licensing & Commercial Options</h2>
        <div className="grid md:grid-cols-2 gap-8">
          <div className="bg-gradient-to-br from-green-50 to-emerald-50 rounded-lg p-6 border border-green-200">
            <div className="flex items-center mb-4">
              <div className="w-12 h-12 bg-green-500 rounded-lg flex items-center justify-center mr-4">
                <span className="text-2xl">🌱</span>
              </div>
              <h3 className="text-2xl font-bold text-gray-900">Open Source</h3>
            </div>
            <p className="text-gray-700 mb-4">
              <strong>GNU Affero General Public License v3.0 (AGPL 3.0)</strong>
            </p>
            <ul className="space-y-2 text-gray-700">
              <li className="flex items-center">
                <span className="w-2 h-2 bg-green-500 rounded-full mr-3" />
                <span className="text-gray-700">Free for development and personal use</span>
              </li>
              <li className="flex items-center">
                <span className="w-2 h-2 bg-green-500 rounded-full mr-3" />
                <span className="text-gray-700">Community contributions welcome</span>
              </li>
              <li className="flex items-center">
                <span className="w-2 h-2 bg-green-500 rounded-full mr-3" />
                <span className="text-gray-700">Source code disclosure required for network use</span>
              </li>
              <li className="flex items-center">
                <span className="w-2 h-2 bg-green-500 rounded-full mr-3" />
                <span className="text-gray-700">Copyleft obligations for modifications</span>
              </li>
            </ul>
          </div>

          <div className="bg-gradient-to-br from-blue-50 to-indigo-50 rounded-lg p-6 border border-blue-200">
            <div className="flex items-center mb-4">
              <div className="w-12 h-12 bg-blue-500 rounded-lg flex items-center justify-center mr-4">
                <span className="text-2xl">🏢</span>
              </div>
              <h3 className="text-2xl font-bold text-gray-900">Commercial</h3>
            </div>
            <p className="text-gray-700 mb-4">
              <strong>Proprietary License with Enhanced Rights</strong>
            </p>
            <ul className="space-y-2 text-gray-700">
              <li className="flex items-center">
                <span className="w-2 h-2 bg-blue-500 rounded-full mr-3" />
                <span className="text-gray-700">Full functionality without restrictions</span>
              </li>
              <li className="flex items-center">
                <span className="w-2 h-2 bg-blue-500 rounded-full mr-3" />
                <span className="text-gray-700">Commercial use rights without copyleft obligations</span>
              </li>
              <li className="flex items-center">
                <span className="w-2 h-2 bg-blue-500 rounded-full mr-3" />
                <span className="text-gray-700">Client modification rights for specific projects</span>
              </li>
              <li className="flex items-center">
                <span className="w-2 h-2 bg-blue-500 rounded-full mr-3" />
                <span className="text-gray-700">Enterprise features and support</span>
              </li>
              <li className="flex items-center">
                <span className="w-2 h-2 bg-blue-500 rounded-full mr-3" />
                <span className="text-gray-700">No source code disclosure requirements</span>
              </li>
            </ul>
          </div>
        </div>
        <div className="mt-6 text-center">
          <p className="text-gray-600 mb-4">
            <strong>Contact LKS Next for commercial licensing inquiries.</strong>
          </p>
          <div className="flex justify-center space-x-4">
            <a 
              href="https://github.com/lksnext-ai-lab/ai-core-tools" 
              target="_blank" 
              rel="noopener noreferrer"
              className="bg-gray-800 hover:bg-gray-900 text-white px-6 py-3 rounded-lg transition-colors"
            >
              View on GitHub
            </a>
            <Link 
              to="/settings/ai-services" 
              className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg transition-colors"
            >
              Get Started
            </Link>
          </div>
        </div>
      </div>

      {/* Getting Started Section */}
      <div className="bg-gradient-to-r from-blue-50 to-purple-50 rounded-xl p-8 mb-8">
        <h2 className="text-3xl font-bold text-gray-900 mb-6 text-center">Ready to Get Started?</h2>
        <div className="text-center">
          <p className="text-lg text-gray-700 mb-6">
            Join the community of developers and organizations building the future with AI.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link 
              to="/apps" 
              className="bg-blue-600 hover:bg-blue-700 text-white px-8 py-3 rounded-lg font-semibold transition-colors"
            >
              Create Your First App
            </Link>
            <Link 
              to="/settings/ai-services" 
              className="bg-white hover:bg-gray-50 text-blue-600 px-8 py-3 rounded-lg font-semibold border border-blue-600 transition-colors"
            >
              Configure AI Services
            </Link>
          </div>
        </div>
      </div>

      {/* Footer Info */}
      <div className="text-center text-gray-500 text-sm">
        <p>© 2024 Mattin AI - Powered by LKS Next</p>
        <p className="mt-2">
          Built with ❤️ using FastAPI, React, and PostgreSQL
        </p>
      </div>
    </div>
  );
};

export default AboutPage;
