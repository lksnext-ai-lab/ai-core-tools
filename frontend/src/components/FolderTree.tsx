import React, { useState, useEffect } from 'react';
import { apiService } from '../services/api';

interface Folder {
  folder_id: number;
  name: string;
  parent_folder_id?: number;
  create_date?: string;
  status?: string;
  repository_id: number;
  subfolders: Folder[];
  resource_count: number;
  folder_path: string;
}

interface FolderTreeProps {
  appId: number;
  repositoryId: number;
  selectedFolderId?: number;
  onFolderSelect: (folderId: number | null, folderPath: string) => void;
  onFolderCreate?: (parentFolderId?: number) => void;
  onFolderRename?: (folderId: number, currentName: string) => void;
  onFolderDelete?: (folderId: number, folderName: string) => void;
  onFolderMove?: (folderId: number, currentParentId?: number) => void;
}

interface FolderNodeProps {
  folder: Folder;
  level: number;
  isExpanded: boolean;
  onToggle: (folderId: number) => void;
  onSelect: (folderId: number, folderPath: string) => void;
  onContextMenu: (e: React.MouseEvent, folder: Folder) => void;
  selectedFolderId?: number;
}

const FolderNode: React.FC<FolderNodeProps> = ({
  folder,
  level,
  isExpanded,
  onToggle,
  onSelect,
  onContextMenu,
  selectedFolderId
}) => {
  const hasChildren = folder.subfolders && folder.subfolders.length > 0;
  const isSelected = selectedFolderId === folder.folder_id;

  return (
    <div className="select-none">
      <div
        className={`flex items-center py-1 px-2 hover:bg-gray-100 cursor-pointer rounded ${
          isSelected ? 'bg-blue-100 text-blue-800' : ''
        }`}
        style={{ paddingLeft: `${level * 20 + 8}px` }}
        onClick={() => onSelect(folder.folder_id, folder.folder_path)}
        onContextMenu={(e) => onContextMenu(e, folder)}
      >
        {hasChildren ? (
          <button
            className="mr-2 w-4 h-4 flex items-center justify-center"
            onClick={(e) => {
              e.stopPropagation();
              onToggle(folder.folder_id);
            }}
          >
            {isExpanded ? (
              <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clipRule="evenodd" />
              </svg>
            ) : (
              <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clipRule="evenodd" />
              </svg>
            )}
          </button>
        ) : (
          <div className="mr-2 w-4 h-4" />
        )}
        
        <svg className="w-4 h-4 mr-2 text-gray-500" fill="currentColor" viewBox="0 0 20 20">
          <path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" />
        </svg>
        
        <span className="flex-1 text-sm">{folder.name}</span>
        
        {folder.resource_count > 0 && (
          <span className="text-xs text-gray-500 ml-2">
            ({folder.resource_count})
          </span>
        )}
      </div>
      
      {hasChildren && isExpanded && (
        <div>
          {folder.subfolders.map((subfolder) => (
            <FolderNode
              key={subfolder.folder_id}
              folder={subfolder}
              level={level + 1}
              isExpanded={isExpanded}
              onToggle={onToggle}
              onSelect={onSelect}
              onContextMenu={onContextMenu}
              selectedFolderId={selectedFolderId}
            />
          ))}
        </div>
      )}
    </div>
  );
};

const FolderTree: React.FC<FolderTreeProps> = ({
  appId,
  repositoryId,
  selectedFolderId,
  onFolderSelect,
  onFolderCreate,
  onFolderRename,
  onFolderDelete,
  onFolderMove
}) => {
  const [folders, setFolders] = useState<Folder[]>([]);
  const [expandedFolders, setExpandedFolders] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadFolders = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await apiService.getFolderTree(appId, repositoryId);
      setFolders(response.folders || []);
    } catch (err) {
      console.error('Error loading folders:', err);
      setError('Failed to load folders');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadFolders();
  }, [appId, repositoryId]);

  const handleToggle = (folderId: number) => {
    setExpandedFolders(prev => {
      const newSet = new Set(prev);
      if (newSet.has(folderId)) {
        newSet.delete(folderId);
      } else {
        newSet.add(folderId);
      }
      return newSet;
    });
  };

  const handleSelect = (folderId: number, folderPath: string) => {
    onFolderSelect(folderId, folderPath);
  };

  const handleContextMenu = (e: React.MouseEvent, folder: Folder) => {
    e.preventDefault();
    // Context menu implementation would go here
    // For now, we'll just show a simple alert
    const options = [
      `Rename "${folder.name}"`,
      `Delete "${folder.name}"`,
      `Move "${folder.name}"`,
      `Create subfolder in "${folder.name}"`
    ];
    
    const choice = prompt(`Choose an action for "${folder.name}":\n\n${options.map((opt, i) => `${i + 1}. ${opt}`).join('\n')}\n\nEnter number (1-4):`);
    
    if (choice) {
      const actionIndex = parseInt(choice) - 1;
      switch (actionIndex) {
        case 0:
          onFolderRename?.(folder.folder_id, folder.name);
          break;
        case 1:
          onFolderDelete?.(folder.folder_id, folder.name);
          break;
        case 2:
          onFolderMove?.(folder.folder_id, folder.parent_folder_id);
          break;
        case 3:
          onFolderCreate?.(folder.folder_id);
          break;
      }
    }
  };

  const renderFolderNode = (folder: Folder, level: number = 0) => (
    <FolderNode
      key={folder.folder_id}
      folder={folder}
      level={level}
      isExpanded={expandedFolders.has(folder.folder_id)}
      onToggle={handleToggle}
      onSelect={handleSelect}
      onContextMenu={handleContextMenu}
      selectedFolderId={selectedFolderId}
    />
  );

  if (loading) {
    return (
      <div className="p-4 text-center text-gray-500">
        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500 mx-auto mb-2"></div>
        Loading folders...
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 text-center text-red-500">
        <p>{error}</p>
        <button
          onClick={loadFolders}
          className="mt-2 px-3 py-1 bg-blue-500 text-white rounded text-sm hover:bg-blue-600"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="border rounded-lg bg-white">
      <div className="p-3 border-b bg-gray-50">
        <div className="flex items-center justify-between">
          <h3 className="font-medium text-gray-900">Folders</h3>
          <button
            onClick={() => onFolderCreate?.()}
            className="text-blue-500 hover:text-blue-700 text-sm"
            title="Create root folder"
          >
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 3a1 1 0 011 1v5h5a1 1 0 110 2h-5v5a1 1 0 11-2 0v-5H4a1 1 0 110-2h5V4a1 1 0 011-1z" clipRule="evenodd" />
            </svg>
          </button>
        </div>
      </div>
      
      <div className="max-h-96 overflow-y-auto">
        {folders.length === 0 ? (
          <div className="p-4 text-center text-gray-500">
            <p>No folders yet</p>
            <button
              onClick={() => onFolderCreate?.()}
              className="mt-2 text-blue-500 hover:text-blue-700 text-sm"
            >
              Create your first folder
            </button>
          </div>
        ) : (
          <div>
            {folders.map(folder => renderFolderNode(folder))}
          </div>
        )}
      </div>
      
      <div className="p-2 border-t bg-gray-50 text-xs text-gray-500">
        Right-click folders for options
      </div>
    </div>
  );
};

export default FolderTree;
