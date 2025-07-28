import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { apiService } from '../services/api';
import ChatInterface from '../components/playground/ChatInterface';
import { OCRInterface } from '../components/playground/OCRInterface';

interface Agent {
  agent_id: number;
  name: string;
  description?: string;
  status: string;
  type: string;
  silo?: {
    silo_id: number;
    name: string;
    metadata_definition?: {
      fields: Array<{
        name: string;
        type: string;
        description: string;
      }>;
    };
  };
  output_parser?: {
    parser_id: number;
    name: string;
    description?: string;
    fields: Array<{
      name: string;
      type: string;
      description: string;
    }>;
  };
}

function AgentPlaygroundPage() {
  const { appId, agentId } = useParams();
  const navigate = useNavigate();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (appId && agentId) {
      loadAgent();
    }
  }, [appId, agentId]);

  async function loadAgent() {
    if (!appId || !agentId) return;
    
    try {
      setLoading(true);
      setError(null);
      const response = await apiService.getAgent(parseInt(appId), parseInt(agentId));
      setAgent(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load agent');
      console.error('Error loading agent:', err);
    } finally {
      setLoading(false);
    }
  }

  function handleBack() {
    navigate(`/apps/${appId}/agents`);
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          <span className="ml-2">Loading agent...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <div className="flex">
            <div className="flex-shrink-0">
              <svg className="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
              </svg>
            </div>
            <div className="ml-3">
              <h3 className="text-sm font-medium text-red-800">Error loading agent</h3>
              <div className="mt-2 text-sm text-red-700">
                <p>{error}</p>
              </div>
              <div className="mt-4">
                <button
                  onClick={handleBack}
                  className="bg-red-100 text-red-800 px-3 py-2 rounded-md text-sm font-medium hover:bg-red-200"
                >
                  Go Back
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!agent) {
    return (
      <div className="space-y-6">
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
          <div className="flex">
            <div className="flex-shrink-0">
              <svg className="h-5 w-5 text-yellow-400" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
            </div>
            <div className="ml-3">
              <h3 className="text-sm font-medium text-yellow-800">Agent not found</h3>
              <div className="mt-2 text-sm text-yellow-700">
                <p>The requested agent could not be found.</p>
              </div>
              <div className="mt-4">
                <button
                  onClick={handleBack}
                  className="bg-yellow-100 text-yellow-800 px-3 py-2 rounded-md text-sm font-medium hover:bg-yellow-200"
                >
                  Go Back
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const isOCRAgent = agent.type === 'ocr' || agent.type === 'ocr_agent';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Agent Playground</h1>
          <p className="text-gray-600 mt-1">
            Test and interact with your AI agent
          </p>
        </div>
        <button
          onClick={handleBack}
          className="px-4 py-2 text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
        >
          ← Back to Agents
        </button>
      </div>

      {/* Agent Info */}
      <div className="bg-white shadow rounded-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-xl font-semibold text-gray-900">{agent.name}</h2>
            {agent.description && (
              <p className="text-gray-600 mt-1">{agent.description}</p>
            )}
          </div>
          <div className="flex items-center space-x-2">
            <span className={`px-3 py-1 rounded-full text-sm font-medium ${
              agent.status === 'active' 
                ? 'bg-green-100 text-green-800' 
                : 'bg-yellow-100 text-yellow-800'
            }`}>
              {agent.status}
            </span>
            <span className="px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-sm font-medium">
              {agent.type}
            </span>
          </div>
        </div>

        {/* Silo Information */}
        {agent.silo && (
          <div className="mt-4 p-4 bg-gray-50 rounded-lg">
            <h3 className="text-sm font-medium text-gray-700 mb-2">
              <span className="mr-2">🗄️</span>
              Connected Silo: {agent.silo.name}
            </h3>
            {agent.silo.metadata_definition && (
              <p className="text-sm text-gray-600">
                <span className="mr-2">🔍</span>
                Metadata filtering available ({agent.silo.metadata_definition.fields.length} fields)
              </p>
            )}
          </div>
        )}
      </div>

      {/* Playground Interface */}
      {isOCRAgent ? (
        <OCRInterface 
          appId={parseInt(appId!)} 
          agentId={parseInt(agentId!)} 
          agentName={agent.name}
          outputParser={agent.output_parser}
        />
      ) : (
        <ChatInterface 
          appId={parseInt(appId!)} 
          agentId={parseInt(agentId!)} 
          agentName={agent.name}
          metadataFields={agent.silo?.metadata_definition?.fields}
        />
      )}
    </div>
  );
}

export default AgentPlaygroundPage; 