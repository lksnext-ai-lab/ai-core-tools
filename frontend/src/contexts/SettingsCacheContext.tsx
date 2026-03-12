import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';
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

  // Setter methods — stable: only call setCache with functional updates (no cache read)
  const setAIServices = useCallback((appId: string, services: AIService[]) => {
    setCache(prev => ({
      ...prev,
      aiServices: { ...prev.aiServices, [appId]: services }
    }));
  }, []);

  const invalidateAIServices = useCallback((appId: string) => {
    setCache(prev => {
      const newAIServices = { ...prev.aiServices };
      delete newAIServices[appId];
      return { ...prev, aiServices: newAIServices };
    });
  }, []);

  const setAPIKeys = useCallback((appId: string, keys: APIKey[]) => {
    setCache(prev => ({
      ...prev,
      apiKeys: { ...prev.apiKeys, [appId]: keys }
    }));
  }, []);

  const invalidateAPIKeys = useCallback((appId: string) => {
    setCache(prev => {
      const newAPIKeys = { ...prev.apiKeys };
      delete newAPIKeys[appId];
      return { ...prev, apiKeys: newAPIKeys };
    });
  }, []);

  const setEmbeddingServices = useCallback((appId: string, services: EmbeddingService[]) => {
    setCache(prev => ({
      ...prev,
      embeddingServices: { ...prev.embeddingServices, [appId]: services }
    }));
  }, []);

  const invalidateEmbeddingServices = useCallback((appId: string) => {
    setCache(prev => {
      const newEmbeddingServices = { ...prev.embeddingServices };
      delete newEmbeddingServices[appId];
      return { ...prev, embeddingServices: newEmbeddingServices };
    });
  }, []);

  const setMCPConfigs = useCallback((appId: string, configs: MCPConfig[]) => {
    setCache(prev => ({
      ...prev,
      mcpConfigs: { ...prev.mcpConfigs, [appId]: configs }
    }));
  }, []);

  const invalidateMCPConfigs = useCallback((appId: string) => {
    setCache(prev => {
      const newMCPConfigs = { ...prev.mcpConfigs };
      delete newMCPConfigs[appId];
      return { ...prev, mcpConfigs: newMCPConfigs };
    });
  }, []);

  const setSkills = useCallback((appId: string, skills: Skill[]) => {
    setCache(prev => ({
      ...prev,
      skills: { ...prev.skills, [appId]: skills }
    }));
  }, []);

  const invalidateSkills = useCallback((appId: string) => {
    setCache(prev => {
      const newSkills = { ...prev.skills };
      delete newSkills[appId];
      return { ...prev, skills: newSkills };
    });
  }, []);

  const setDataStructures = useCallback((appId: string, structures: DataStructure[]) => {
    setCache(prev => ({
      ...prev,
      dataStructures: { ...prev.dataStructures, [appId]: structures }
    }));
  }, []);

  const invalidateDataStructures = useCallback((appId: string) => {
    setCache(prev => {
      const newDataStructures = { ...prev.dataStructures };
      delete newDataStructures[appId];
      return { ...prev, dataStructures: newDataStructures };
    });
  }, []);

  const setCollaborators = useCallback((appId: string, collaborators: Collaborator[]) => {
    setCache(prev => ({
      ...prev,
      collaborators: { ...prev.collaborators, [appId]: collaborators }
    }));
  }, []);

  const invalidateCollaborators = useCallback((appId: string) => {
    setCache(prev => {
      const newCollaborators = { ...prev.collaborators };
      delete newCollaborators[appId];
      return { ...prev, collaborators: newCollaborators };
    });
  }, []);

  const clearAppCache = useCallback((appId: string) => {
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
  }, []);

  // Context value — memoized so object reference only changes when cache or stable callbacks change
  const value = useMemo<SettingsCacheContextType>(() => ({
    // Getters inline to always reflect current cache state
    getAIServices: (appId: string) => cache.aiServices[appId] || null,
    getAPIKeys: (appId: string) => cache.apiKeys[appId] || null,
    getEmbeddingServices: (appId: string) => cache.embeddingServices[appId] || null,
    getMCPConfigs: (appId: string) => cache.mcpConfigs[appId] || null,
    getSkills: (appId: string) => cache.skills[appId] || null,
    getDataStructures: (appId: string) => cache.dataStructures[appId] || null,
    getCollaborators: (appId: string) => cache.collaborators[appId] || null,
    // Stable setter/invalidator references from useCallback
    setAIServices,
    invalidateAIServices,
    setAPIKeys,
    invalidateAPIKeys,
    setEmbeddingServices,
    invalidateEmbeddingServices,
    setMCPConfigs,
    invalidateMCPConfigs,
    setSkills,
    invalidateSkills,
    setDataStructures,
    invalidateDataStructures,
    setCollaborators,
    invalidateCollaborators,
    clearAppCache,
  }), [
    cache,
    setAIServices, invalidateAIServices,
    setAPIKeys, invalidateAPIKeys,
    setEmbeddingServices, invalidateEmbeddingServices,
    setMCPConfigs, invalidateMCPConfigs,
    setSkills, invalidateSkills,
    setDataStructures, invalidateDataStructures,
    setCollaborators, invalidateCollaborators,
    clearAppCache,
  ]);

  return (
    <SettingsCacheContext.Provider value={value}>
      {children}
    </SettingsCacheContext.Provider>
  );
};

export default SettingsCacheProvider;
