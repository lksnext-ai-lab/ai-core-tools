import React, { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowUpDown, ChevronDown, ChevronRight, Folder, Home, MoreVertical, Pencil, Plus, Trash2 } from 'lucide-react';
import { apiService } from '../services/api';
import { LoadingState } from './ui/LoadingState';

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
  canEdit?: boolean;
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
  dropdownRefs: React.RefObject<{ [key: number]: HTMLDivElement | null }>;
  canEdit?: boolean;
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
  dropdownRefs,
  canEdit = true
}) => {
  const { t } = useTranslation('common');
  const hasChildren = folder.subfolders && folder.subfolders.length > 0;
  const isSelected = selectedFolderId === folder.folder_id;
  const folderPath = folder.folder_path || folder.name;

  let expandIcon: React.ReactNode = <span className="w-3 h-3" />;
  if (hasChildren) {
    if (isExpanded) {
      expandIcon = (
        <ChevronDown className="w-3 h-3" aria-hidden="true" />
      );
    } else {
      expandIcon = (
        <ChevronRight className="w-3 h-3" aria-hidden="true" />
      );
    }
  }

  return (
    <div className="select-none">
      <div className="relative">
        <div
          className={`flex items-center p-2 rounded-md transition-colors hover:bg-surface-hover dark:hover:bg-surface-hover-dark ${
            isSelected ? 'bg-surface-hover text-accent dark:bg-surface-hover-dark dark:text-accent-dark' : 'text-fg dark:text-fg-dark'
          }`}
          style={{ paddingLeft: `${level * 16 + 8}px` }}
        >
          <button
            type="button"
            aria-label={t(isExpanded ? 'folderTree.collapseFolder' : 'folderTree.expandFolder', { name: folder.name })}
            onClick={(e) => {
              e.stopPropagation();
              onToggle(folder.folder_id);
            }}
            className="mr-2 text-fg-tertiary hover:text-fg dark:text-fg-tertiary-dark dark:hover:text-fg-dark w-4 h-4 flex items-center justify-center flex-shrink-0"
          >
            {expandIcon}
          </button>

          <button
            type="button"
            className="flex items-center flex-1 min-w-0 text-left bg-transparent border-0 p-0 cursor-pointer"
            onClick={() => onSelect(folder.folder_id, folderPath)}
          >
            <Folder className={`w-4 h-4 mr-2 flex-shrink-0 ${isSelected ? 'text-accent dark:text-accent-dark' : 'text-fg-tertiary dark:text-fg-tertiary-dark'}`} aria-hidden="true" />

            <span className="flex-1 text-sm truncate">{folder.name}</span>

            {folder.resource_count > 0 && (
              <span className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark ml-2">
                ({folder.resource_count})
              </span>
            )}
          </button>

          {/* Dropdown Menu Button */}
          {canEdit && (
            <button
              type="button"
              onClick={(e) => onToggleDropdown(folder.folder_id, e)}
              className="ml-2 p-1 text-fg-tertiary hover:text-fg hover:bg-surface-ash rounded transition-all duration-200 dark:text-fg-tertiary-dark dark:hover:text-fg-dark dark:hover:bg-surface-tint-dark"
              title={t('folderTree.actions')}
            >
              <MoreVertical className="w-4 h-4" aria-hidden="true" />
            </button>
          )}
        </div>

        {/* Dropdown Menu */}
        {canEdit && openDropdown === folder.folder_id && (
          <div
            ref={(el) => { dropdownRefs.current[folder.folder_id] = el; }}
            className="absolute right-0 mt-1 w-48 bg-surface rounded-md shadow-lg z-50 border border-line dark:bg-surface-dark dark:border-line-dark"
            style={{ top: '100%' }}
          >
            <div className="py-1">
              <button
                onClick={() => onAction('create', folder)}
                className="flex items-center w-full px-4 py-2 text-sm text-fg-secondary hover:bg-surface-hover dark:text-fg-secondary-dark dark:hover:bg-surface-hover-dark"
              >
                <Plus className="w-4 h-4 mr-3 text-fg-tertiary dark:text-fg-tertiary-dark" aria-hidden="true" />
                {t('folderTree.createSubfolder')}
              </button>
              
              <button
                onClick={() => onAction('rename', folder)}
                className="flex items-center w-full px-4 py-2 text-sm text-fg-secondary hover:bg-surface-hover dark:text-fg-secondary-dark dark:hover:bg-surface-hover-dark"
              >
                <Pencil className="w-4 h-4 mr-3 text-fg-tertiary dark:text-fg-tertiary-dark" aria-hidden="true" />
                {t('folderTree.renameFolder')}
              </button>
              
              <button
                onClick={() => onAction('move', folder)}
                className="flex items-center w-full px-4 py-2 text-sm text-fg-secondary hover:bg-surface-hover dark:text-fg-secondary-dark dark:hover:bg-surface-hover-dark"
              >
                <ArrowUpDown className="w-4 h-4 mr-3 text-fg-tertiary dark:text-fg-tertiary-dark" aria-hidden="true" />
                {t('folderTree.moveFolder')}
              </button>
              
              <div className="border-t border-line dark:border-line-dark"></div>
              
              <button
                onClick={() => onAction('delete', folder)}
                className="flex items-center w-full px-4 py-2 text-sm text-error hover:bg-error-bg dark:text-error-dark dark:hover:bg-error-bg-dark"
              >
                <Trash2 className="w-4 h-4 mr-3 text-error dark:text-error-dark" aria-hidden="true" />
                {t('folderTree.deleteFolder')}
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
  canEdit = true
}) => {
  const { t } = useTranslation('common');
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
    void loadFolders();
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
      case 'create': {
        // For root folder (folder_id = 0), pass undefined to create at root level
        const parentId = folder.folder_id === 0 ? undefined : folder.folder_id;
        console.log('FolderTree: calling onFolderCreate with parentId:', parentId);
        onFolderCreate?.(parentId);
        break;
      }
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
      <LoadingState variant="section" message={t('folderTree.loading')} />
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between px-4 pt-4 pb-2">
        <h3 className="text-[11px] font-medium uppercase tracking-[0.05em] text-fg-tertiary dark:text-fg-tertiary-dark">{t('folderTree.heading')}</h3>
        {canEdit && onFolderCreate && (
          <button
            type="button"
            onClick={() => onFolderCreate()}
            className="p-1 rounded text-fg-tertiary hover:text-fg hover:bg-surface-ash transition-colors dark:text-fg-tertiary-dark dark:hover:text-fg-dark dark:hover:bg-surface-hover-dark"
            title={t('folderTree.createFolder')}
            aria-label={t('folderTree.createFolder')}
          >
            <Plus className="w-4 h-4" />
          </button>
        )}
      </div>

      <div className="px-2 pb-4">
        {/* Root folder option */}
        <div className="relative">
          <div
            className={`flex items-center p-2 rounded-md transition-colors mb-1 hover:bg-surface-hover dark:hover:bg-surface-hover-dark ${
              selectedFolderId === null ? 'bg-surface-hover text-accent dark:bg-surface-hover-dark dark:text-accent-dark' : 'text-fg dark:text-fg-dark'
            }`}
          >
            <button
              type="button"
              className="flex items-center flex-1 min-w-0 text-left bg-transparent border-0 p-0 cursor-pointer"
              onClick={() => onFolderSelect(null, '')}
            >
              <Home className={`w-4 h-4 mr-2 ${selectedFolderId === null ? 'text-accent dark:text-accent-dark' : 'text-fg-tertiary dark:text-fg-tertiary-dark'}`} aria-hidden="true" />
              <span className="text-sm font-medium">{t('folderTree.root')}</span>
            </button>

            {/* Dropdown Menu Button for Root */}
            {canEdit && (
              <button
                type="button"
                onClick={(e) => toggleDropdown(0, e)}
                className="ml-2 p-1 text-fg-tertiary hover:text-fg hover:bg-surface-ash rounded transition-all duration-200 dark:text-fg-tertiary-dark dark:hover:text-fg-dark dark:hover:bg-surface-tint-dark"
                title={t('folderTree.rootActions')}
              >
                <MoreVertical className="w-4 h-4" aria-hidden="true" />
              </button>
            )}
          </div>

          {/* Dropdown Menu for Root */}
          {canEdit && openDropdown === 0 && (
            <div
              ref={(el) => { dropdownRefs.current[0] = el; }}
              className="absolute right-0 mt-1 w-48 bg-surface rounded-md shadow-lg z-50 border border-line dark:bg-surface-dark dark:border-line-dark"
              style={{ top: '100%' }}
            >
              <div className="py-1">
                <button
                  onClick={() => handleAction('create', { folder_id: 0, name: 'Root', parent_folder_id: null } as any)}
                  className="flex items-center w-full px-4 py-2 text-sm text-fg-secondary hover:bg-surface-hover dark:text-fg-secondary-dark dark:hover:bg-surface-hover-dark"
                >
                  <Plus className="w-4 h-4 mr-3 text-fg-tertiary dark:text-fg-tertiary-dark" aria-hidden="true" />
                  {t('folderTree.createFolder')}
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
              canEdit={canEdit}
            />
          ))}
        </div>

        {folders.length === 0 && (
          <div className="text-center py-6 px-2 text-fg-tertiary dark:text-fg-tertiary-dark">
            <Folder className="w-10 h-10 mx-auto mb-3 text-fg-faint2 dark:text-fg-faint2-dark" aria-hidden="true" />
            <p className="text-sm">{t('folderTree.noFolders')}</p>
            <p className="text-xs text-fg-faint dark:text-fg-faint-dark mt-1">{t('folderTree.createFirstFolder')}</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default FolderTree;