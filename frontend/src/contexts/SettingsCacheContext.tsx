import React, { createContext, useContext, useState } from 'react';
import type { ReactNode } from 'react';

// Define interfaces for each settings type
interface AIService {
  service_id: number;
  name: string;
  provider: string;
  model_name: string;
  created_at: string;
  needs_api_key?: boolean;
}

interface APIKey {
  key_id: number;
  name: string;
  key_preview: string;
  created_at: string;
  last_used_at: string | null;
  is_active: boolean;
}

interface EmbeddingService {
  service_id: number;
  name: string;
  provider: string;
  model_name: string;
  created_at: string;
  needs_api_key?: boolean;
}

import type { MCPConfig, Skill } from '../core/types';

interface DataStructure {
  parser_id: number;
  name: string;
  description: string;
  field_count: number;
  created_at: string;
}

interface Collaborator {
  id: number;
  user_id: number;
  user_email: string;
  user_name?: string;
  role: string;
  status: string;
  invited_at: string;
  accepted_at?: string;
  invited_by_name?: string;
}

// Cache state interface
interface SettingsCacheState {
  aiServices: { [appId: string]: AIService[] };
  apiKeys: { [appId: string]: APIKey[] };
  embeddingServices: { [appId: string]: EmbeddingService[] };
  mcpConfigs: { [appId: string]: MCPConfig[] };
  skills: { [appId: string]: Skill[] };
  dataStructures: { [appId: string]: DataStructure[] };
  collaborators: { [appId: string]: Collaborator[] };
}

// Context interface
interface SettingsCacheContextType {
  // AI Services
  getAIServices: (appId: string) => AIService[] | null;
  setAIServices: (appId: string, services: AIService[]) => void;
  invalidateAIServices: (appId: string) => void;
  
  // API Keys
  getAPIKeys: (appId: string) => APIKey[] | null;
  setAPIKeys: (appId: string, keys: APIKey[]) => void;
  invalidateAPIKeys: (appId: string) => void;
  
  // Embedding Services
  getEmbeddingServices: (appId: string) => EmbeddingService[] | null;
  setEmbeddingServices: (appId: string, services: EmbeddingService[]) => void;
  invalidateEmbeddingServices: (appId: string) => void;
  
  // MCP Configs
  getMCPConfigs: (appId: string) => MCPConfig[] | null;
  setMCPConfigs: (appId: string, configs: MCPConfig[]) => void;
  invalidateMCPConfigs: (appId: string) => void;

  // Skills
  getSkills: (appId: string) => Skill[] | null;
  setSkills: (appId: string, skills: Skill[]) => void;
  invalidateSkills: (appId: string) => void;

  // Data Structures
  getDataStructures: (appId: string) => DataStructure[] | null;
  setDataStructures: (appId: string, structures: DataStructure[]) => void;
  invalidateDataStructures: (appId: string) => void;
  
  // Collaborators
  getCollaborators: (appId: string) => Collaborator[] | null;
  setCollaborators: (appId: string, collaborators: Collaborator[]) => void;
  invalidateCollaborators: (appId: string) => void;
  
  // Clear all cache for an app
  clearAppCache: (appId: string) => void;
}

const SettingsCacheContext = createContext<SettingsCacheContextType | undefined>(undefined);

export const useSettingsCache = () => {
  const context = useContext(SettingsCacheContext);
  if (context === undefined) {
    throw new Error('useSettingsCache must be used within a SettingsCacheProvider');
  }
  return context;
};

interface SettingsCacheProviderProps {
  children: ReactNode;
}

export const SettingsCacheProvider: React.FC<SettingsCacheProviderProps> = ({ children }) => {
  const [cache, setCache] = useState<SettingsCacheState>({
    aiServices: {},
    apiKeys: {},
    embeddingServices: {},
    mcpConfigs: {},
    skills: {},
    dataStructures: {},
    collaborators: {},
  });

  // AI Services methods
  const getAIServices = (appId: string): AIService[] | null => {
    return cache.aiServices[appId] || null;
  };

  const setAIServices = (appId: string, services: AIService[]) => {
    setCache(prev => ({
      ...prev,
      aiServices: { ...prev.aiServices, [appId]: services }
    }));
  };

  const invalidateAIServices = (appId: string) => {
    setCache(prev => {
      const newAIServices = { ...prev.aiServices };
      delete newAIServices[appId];
      return { ...prev, aiServices: newAIServices };
    });
  };

  // API Keys methods
  const getAPIKeys = (appId: string): APIKey[] | null => {
    return cache.apiKeys[appId] || null;
  };

  const setAPIKeys = (appId: string, keys: APIKey[]) => {
    setCache(prev => ({
      ...prev,
      apiKeys: { ...prev.apiKeys, [appId]: keys }
    }));
  };

  const invalidateAPIKeys = (appId: string) => {
    setCache(prev => {
      const newAPIKeys = { ...prev.apiKeys };
      delete newAPIKeys[appId];
      return { ...prev, apiKeys: newAPIKeys };
    });
  };

  // Embedding Services methods
  const getEmbeddingServices = (appId: string): EmbeddingService[] | null => {
    return cache.embeddingServices[appId] || null;
  };

  const setEmbeddingServices = (appId: string, services: EmbeddingService[]) => {
    setCache(prev => ({
      ...prev,
      embeddingServices: { ...prev.embeddingServices, [appId]: services }
    }));
  };

  const invalidateEmbeddingServices = (appId: string) => {
    setCache(prev => {
      const newEmbeddingServices = { ...prev.embeddingServices };
      delete newEmbeddingServices[appId];
      return { ...prev, embeddingServices: newEmbeddingServices };
    });
  };

  // MCP Configs methods
  const getMCPConfigs = (appId: string): MCPConfig[] | null => {
    return cache.mcpConfigs[appId] || null;
  };

  const setMCPConfigs = (appId: string, configs: MCPConfig[]) => {
    setCache(prev => ({
      ...prev,
      mcpConfigs: { ...prev.mcpConfigs, [appId]: configs }
    }));
  };

  const invalidateMCPConfigs = (appId: string) => {
    setCache(prev => {
      const newMCPConfigs = { ...prev.mcpConfigs };
      delete newMCPConfigs[appId];
      return { ...prev, mcpConfigs: newMCPConfigs };
    });
  };

  // Skills methods
  const getSkills = (appId: string): Skill[] | null => {
    return cache.skills[appId] || null;
  };

  const setSkills = (appId: string, skills: Skill[]) => {
    setCache(prev => ({
      ...prev,
      skills: { ...prev.skills, [appId]: skills }
    }));
  };

  const invalidateSkills = (appId: string) => {
    setCache(prev => {
      const newSkills = { ...prev.skills };
      delete newSkills[appId];
      return { ...prev, skills: newSkills };
    });
  };

  // Data Structures methods
  const getDataStructures = (appId: string): DataStructure[] | null => {
    return cache.dataStructures[appId] || null;
  };

  const setDataStructures = (appId: string, structures: DataStructure[]) => {
    setCache(prev => ({
      ...prev,
      dataStructures: { ...prev.dataStructures, [appId]: structures }
    }));
  };

  const invalidateDataStructures = (appId: string) => {
    setCache(prev => {
      const newDataStructures = { ...prev.dataStructures };
      delete newDataStructures[appId];
      return { ...prev, dataStructures: newDataStructures };
    });
  };

  // Collaborators methods
  const getCollaborators = (appId: string): Collaborator[] | null => {
    return cache.collaborators[appId] || null;
  };

  const setCollaborators = (appId: string, collaborators: Collaborator[]) => {
    setCache(prev => ({
      ...prev,
      collaborators: { ...prev.collaborators, [appId]: collaborators }
    }));
  };

  const invalidateCollaborators = (appId: string) => {
    setCache(prev => {
      const newCollaborators = { ...prev.collaborators };
      delete newCollaborators[appId];
      return { ...prev, collaborators: newCollaborators };
    });
  };

  // Clear all cache for an app
  const clearAppCache = (appId: string) => {
    setCache(prev => {
      const newAIServices = { ...prev.aiServices };
      const newAPIKeys = { ...prev.apiKeys };
      const newEmbeddingServices = { ...prev.embeddingServices };
      const newMCPConfigs = { ...prev.mcpConfigs };
      const newSkills = { ...prev.skills };
      const newDataStructures = { ...prev.dataStructures };
      const newCollaborators = { ...prev.collaborators };

      delete newAIServices[appId];
      delete newAPIKeys[appId];
      delete newEmbeddingServices[appId];
      delete newMCPConfigs[appId];
      delete newSkills[appId];
      delete newDataStructures[appId];
      delete newCollaborators[appId];

      return {
        aiServices: newAIServices,
        apiKeys: newAPIKeys,
        embeddingServices: newEmbeddingServices,
        mcpConfigs: newMCPConfigs,
        skills: newSkills,
        dataStructures: newDataStructures,
        collaborators: newCollaborators,
      };
    });
  };

  const value: SettingsCacheContextType = {
    getAIServices,
    setAIServices,
    invalidateAIServices,
    getAPIKeys,
    setAPIKeys,
    invalidateAPIKeys,
    getEmbeddingServices,
    setEmbeddingServices,
    invalidateEmbeddingServices,
    getMCPConfigs,
    setMCPConfigs,
    invalidateMCPConfigs,
    getSkills,
    setSkills,
    invalidateSkills,
    getDataStructures,
    setDataStructures,
    invalidateDataStructures,
    getCollaborators,
    setCollaborators,
    invalidateCollaborators,
    clearAppCache,
  };

  return (
    <SettingsCacheContext.Provider value={value}>
      {children}
    </SettingsCacheContext.Provider>
  );
};

export default SettingsCacheProvider;
