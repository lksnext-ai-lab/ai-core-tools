import React, { useState, useEffect, useRef } from 'react';
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
  onAction: (action: string, folder: Folder) => void;
  selectedFolderId?: number;
  openDropdown: number | null;
  onToggleDropdown: (folderId: number, e: React.MouseEvent) => void;
  dropdownRefs: React.MutableRefObject<{ [key: number]: HTMLDivElement | null }>;
}

const FolderNode: React.FC<FolderNodeProps> = ({
  folder,
  level,
  isExpanded,
  onToggle,
  onSelect,
  onAction,
  selectedFolderId,
  openDropdown,
  onToggleDropdown,
  dropdownRefs
}) => {
  const hasChildren = folder.subfolders && folder.subfolders.length > 0;
  const isSelected = selectedFolderId === folder.folder_id;
  const folderPath = folder.folder_path || folder.name;

  return (
    <div className="select-none">
      <div className="relative">
        <div
          className={`flex items-center p-2 rounded-md cursor-pointer hover:bg-gray-100 transition-colors ${
            isSelected ? 'bg-blue-100 text-blue-800' : ''
          }`}
          style={{ paddingLeft: `${level * 16 + 8}px` }}
          onClick={() => onSelect(folder.folder_id, folderPath)}
        >
          <button
            onClick={(e) => {
              e.stopPropagation();
              onToggle(folder.folder_id);
            }}
            className="mr-2 text-gray-500 hover:text-gray-700 w-4 h-4 flex items-center justify-center"
          >
            {hasChildren ? (
              isExpanded ? (
                <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clipRule="evenodd" />
                </svg>
              ) : (
                <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clipRule="evenodd" />
                </svg>
              )
            ) : (
              <span className="w-3 h-3"></span>
            )}
          </button>
          
          <svg className="w-4 h-4 mr-2 text-gray-500" fill="currentColor" viewBox="0 0 20 20">
            <path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" />
          </svg>
          
          <span className="flex-1 text-sm truncate">{folder.name}</span>
          
          {folder.resource_count > 0 && (
            <span className="text-xs text-gray-500 ml-2">
              ({folder.resource_count})
            </span>
          )}

          {/* Dropdown Menu Button */}
          <button
            onClick={(e) => onToggleDropdown(folder.folder_id, e)}
            className="ml-2 p-1 text-gray-500 hover:text-gray-700 hover:bg-gray-200 rounded transition-all duration-200"
            title="Folder actions"
          >
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z" />
            </svg>
          </button>
        </div>

        {/* Dropdown Menu */}
        {openDropdown === folder.folder_id && (
          <div
            ref={(el) => { dropdownRefs.current[folder.folder_id] = el; }}
            className="absolute right-0 mt-1 w-48 bg-white rounded-md shadow-lg z-50 border border-gray-200"
            style={{ top: '100%' }}
          >
            <div className="py-1">
              <button
                onClick={() => onAction('create', folder)}
                className="flex items-center w-full px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
              >
                <svg className="w-4 h-4 mr-3 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                </svg>
                Create subfolder
              </button>
              
              <button
                onClick={() => onAction('rename', folder)}
                className="flex items-center w-full px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
              >
                <svg className="w-4 h-4 mr-3 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                </svg>
                Rename folder
              </button>
              
              <button
                onClick={() => onAction('move', folder)}
                className="flex items-center w-full px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
              >
                <svg className="w-4 h-4 mr-3 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4" />
                </svg>
                Move folder
              </button>
              
              <div className="border-t border-gray-100"></div>
              
              <button
                onClick={() => onAction('delete', folder)}
                className="flex items-center w-full px-4 py-2 text-sm text-red-600 hover:bg-red-50"
              >
                <svg className="w-4 h-4 mr-3 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
                Delete folder
              </button>
            </div>
          </div>
        )}
      </div>
      
      {hasChildren && isExpanded && (
        <div>
          {folder.subfolders.map((subfolder) => (
            <FolderNode
              key={subfolder.folder_id}
              folder={subfolder}
              level={level + 1}
              isExpanded={false} // This will be managed by parent state
              onToggle={onToggle}
              onSelect={onSelect}
              onAction={onAction}
              selectedFolderId={selectedFolderId}
              openDropdown={openDropdown}
              onToggleDropdown={onToggleDropdown}
              dropdownRefs={dropdownRefs}
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
  onFolderMove,
}) => {
  const [folders, setFolders] = useState<Folder[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedFolders, setExpandedFolders] = useState<Set<number>>(new Set());
  const [openDropdown, setOpenDropdown] = useState<number | null>(null);
  const dropdownRefs = useRef<{ [key: number]: HTMLDivElement | null }>({});

  const loadFolders = async () => {
    try {
      setLoading(true);
      const response = await apiService.getFolderTree(appId, repositoryId);
      console.log('FolderTree API response:', response);
      setFolders(response.folders || []);
    } catch (error) {
      console.error('Error loading folders:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadFolders();
  }, [appId, repositoryId]);

  const toggleExpand = (folderId: number) => {
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

  const toggleDropdown = (folderId: number, e: React.MouseEvent) => {
    e.stopPropagation();
    setOpenDropdown(openDropdown === folderId ? null : folderId);
  };

  const closeDropdown = () => {
    setOpenDropdown(null);
  };

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (openDropdown !== null) {
        const dropdownElement = dropdownRefs.current[openDropdown];
        if (dropdownElement && !dropdownElement.contains(event.target as Node)) {
          closeDropdown();
        }
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [openDropdown]);

  const handleSelect = (folderId: number, folderPath: string) => {
    onFolderSelect(folderId, folderPath);
    closeDropdown();
  };

  const handleAction = (action: string, folder: Folder) => {
    console.log('FolderTree: handleAction called', { action, folder });
    closeDropdown();
    switch (action) {
      case 'create':
        // For root folder (folder_id = 0), pass undefined to create at root level
        const parentId = folder.folder_id === 0 ? undefined : folder.folder_id;
        console.log('FolderTree: calling onFolderCreate with parentId:', parentId);
        onFolderCreate?.(parentId);
        break;
      case 'rename':
        console.log('FolderTree: calling onFolderRename');
        onFolderRename?.(folder.folder_id, folder.name);
        break;
      case 'delete':
        console.log('FolderTree: calling onFolderDelete');
        onFolderDelete?.(folder.folder_id, folder.name);
        break;
      case 'move':
        console.log('FolderTree: calling onFolderMove');
        onFolderMove?.(folder.folder_id, folder.parent_folder_id);
        break;
    }
  };

  if (loading) {
    return (
      <div className="p-4 text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
        <p className="mt-2 text-sm text-gray-600">Loading folders...</p>
      </div>
    );
  }

  return (
    <div className="bg-white border border-gray-200 rounded-lg">
      <div className="p-4 border-b border-gray-200">
        <h3 className="text-lg font-semibold text-gray-900">Folders</h3>
      </div>
      
      <div className="p-4">
        {/* Root folder option */}
        <div className="relative">
          <div
            className={`flex items-center p-2 rounded-md cursor-pointer hover:bg-gray-100 transition-colors mb-2 ${
              selectedFolderId === null ? 'bg-blue-100 text-blue-800' : ''
            }`}
            onClick={() => onFolderSelect(null, '')}
          >
            <svg className="w-4 h-4 mr-2 text-gray-500" fill="currentColor" viewBox="0 0 20 20">
              <path d="M10.707 2.293a1 1 0 00-1.414 0l-7 7a1 1 0 001.414 1.414L4 10.414V17a1 1 0 001 1h2a1 1 0 001-1v-2a1 1 0 011-1h2a1 1 0 011 1v2a1 1 0 001 1h2a1 1 0 001-1v-6.586l.293.293a1 1 0 001.414-1.414l-7-7z" />
            </svg>
            <span className="text-sm font-medium">Repository Root</span>

            {/* Dropdown Menu Button for Root */}
            <button
              onClick={(e) => toggleDropdown(0, e)}
              className="ml-2 p-1 text-gray-500 hover:text-gray-700 hover:bg-gray-200 rounded transition-all duration-200"
              title="Root folder actions"
            >
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                <path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z" />
              </svg>
            </button>
          </div>

          {/* Dropdown Menu for Root */}
          {openDropdown === 0 && (
            <div
              ref={(el) => { dropdownRefs.current[0] = el; }}
              className="absolute right-0 mt-1 w-48 bg-white rounded-md shadow-lg z-50 border border-gray-200"
              style={{ top: '100%' }}
            >
              <div className="py-1">
                <button
                  onClick={() => handleAction('create', { folder_id: 0, name: 'Root', parent_folder_id: null } as any)}
                  className="flex items-center w-full px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                >
                  <svg className="w-4 h-4 mr-3 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                  </svg>
                  Create folder
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Folder tree */}
        <div className="space-y-1">
          {folders.map((folder) => (
            <FolderNode
              key={folder.folder_id}
              folder={folder}
              level={0}
              isExpanded={expandedFolders.has(folder.folder_id)}
              onToggle={toggleExpand}
              onSelect={handleSelect}
              onAction={handleAction}
              selectedFolderId={selectedFolderId}
              openDropdown={openDropdown}
              onToggleDropdown={toggleDropdown}
              dropdownRefs={dropdownRefs}
            />
          ))}
        </div>

        {folders.length === 0 && (
          <div className="text-center py-8 text-gray-500">
            <svg className="w-12 h-12 mx-auto mb-4 text-gray-300" fill="currentColor" viewBox="0 0 20 20">
              <path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" />
            </svg>
            <p className="text-sm">No folders yet</p>
            <p className="text-xs text-gray-400 mt-1">Create your first folder to organize files</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default FolderTree;