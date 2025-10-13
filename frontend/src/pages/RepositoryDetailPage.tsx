import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { apiService } from '../services/api';
import Modal from '../components/ui/Modal';
import FolderTree from '../components/FolderTree';

interface Resource {
  resource_id: number;
  name: string;
  uri: string;
  file_type: string;
  created_at: string;
  folder_id?: number;
  folder_path?: string;
}

interface RepositoryDetail {
  repository_id: number;
  name: string;
  created_at: string;
  resources: Resource[];
  folders: Array<{
    folder_id: number;
    name: string;
    parent_folder_id?: number;
  }>;
  embedding_services: Array<{
    service_id: number;
    name: string;
  }>;
}

const RepositoryDetailPage: React.FC = () => {
  const { appId, repositoryId } = useParams<{ appId: string; repositoryId: string }>();
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);
  
  const [repository, setRepository] = useState<RepositoryDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [resourceToDelete, setResourceToDelete] = useState<Resource | null>(null);
  const [showMoveModal, setShowMoveModal] = useState(false);
  const [resourceToMove, setResourceToMove] = useState<Resource | null>(null);
  const [moveToFolderId, setMoveToFolderId] = useState<number | null>(null);
  
  // Folder-related state
  const [selectedFolderId, setSelectedFolderId] = useState<number | null>(null);
  const [selectedFolderPath, setSelectedFolderPath] = useState<string>('');
  const [showCreateFolderModal, setShowCreateFolderModal] = useState(false);
  const [showRenameFolderModal, setShowRenameFolderModal] = useState(false);
  const [showDeleteFolderModal, setShowDeleteFolderModal] = useState(false);
  const [showMoveFolderModal, setShowMoveFolderModal] = useState(false);
  const [folderActionData, setFolderActionData] = useState<{
    folderId?: number;
    folderName?: string;
    parentFolderId?: number;
  }>({});
  const [newFolderName, setNewFolderName] = useState('');
  const [newParentFolderId, setNewParentFolderId] = useState<number | null>(null);

  useEffect(() => {
    if (appId && repositoryId) {
      loadRepository();
    }
  }, [appId, repositoryId]);

  const loadRepository = async () => {
    try {
      setLoading(true);
      const data = await apiService.getRepository(parseInt(appId!), parseInt(repositoryId!));
      setRepository(data);
      setError(null);
    } catch (err) {
      console.error('Error loading repository:', err);
      setError('Failed to load repository');
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    try {
      setUploading(true);
      setError(null);

      const formData = new FormData();
      Array.from(files).forEach(file => {
        formData.append('files', file);
      });

      console.log('Uploading files with folder_id:', selectedFolderId);
      await apiService.uploadResources(parseInt(appId!), parseInt(repositoryId!), Array.from(files), selectedFolderId || undefined);
      
      // Reload repository to get updated file list
      await loadRepository();
      
      // Clear file input
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    } catch (err) {
      console.error('Error uploading files:', err);
      setError('Failed to upload files');
    } finally {
      setUploading(false);
    }
  };

  // Folder management functions
  const handleFolderSelect = (folderId: number | null, folderPath: string) => {
    console.log('Folder selected:', { folderId, folderPath });
    setSelectedFolderId(folderId);
    setSelectedFolderPath(folderPath);
  };

  const handleCreateFolder = (parentFolderId?: number) => {
    setFolderActionData({ parentFolderId });
    setNewFolderName('');
    setShowCreateFolderModal(true);
  };

  const handleRenameFolder = (folderId: number, currentName: string) => {
    setFolderActionData({ folderId, folderName: currentName });
    setNewFolderName(currentName);
    setShowRenameFolderModal(true);
  };

  const handleDeleteFolder = (folderId: number, folderName: string) => {
    setFolderActionData({ folderId, folderName });
    setShowDeleteFolderModal(true);
  };

  const handleMoveFolder = (folderId: number, currentParentId?: number) => {
    setFolderActionData({ folderId, parentFolderId: currentParentId });
    setNewParentFolderId(currentParentId || null);
    setShowMoveFolderModal(true);
  };

  const createFolder = async () => {
    if (!newFolderName.trim()) return;
    
    try {
      await apiService.createFolder(
        parseInt(appId!),
        parseInt(repositoryId!),
        newFolderName.trim(),
        folderActionData.parentFolderId
      );
      setShowCreateFolderModal(false);
      setNewFolderName('');
      await loadRepository();
    } catch (err) {
      console.error('Error creating folder:', err);
      setError('Failed to create folder');
    }
  };

  const renameFolder = async () => {
    if (!newFolderName.trim() || !folderActionData.folderId) return;
    
    try {
      await apiService.updateFolder(
        parseInt(appId!),
        parseInt(repositoryId!),
        folderActionData.folderId,
        newFolderName.trim()
      );
      setShowRenameFolderModal(false);
      setNewFolderName('');
      await loadRepository();
    } catch (err) {
      console.error('Error renaming folder:', err);
      setError('Failed to rename folder');
    }
  };

  const deleteFolder = async () => {
    if (!folderActionData.folderId) return;
    
    try {
      await apiService.deleteFolder(
        parseInt(appId!),
        parseInt(repositoryId!),
        folderActionData.folderId
      );
      setShowDeleteFolderModal(false);
      // Reset selection if deleted folder was selected
      if (selectedFolderId === folderActionData.folderId) {
        setSelectedFolderId(null);
        setSelectedFolderPath('');
      }
      await loadRepository();
    } catch (err) {
      console.error('Error deleting folder:', err);
      setError('Failed to delete folder');
    }
  };

  const moveFolder = async () => {
    if (!folderActionData.folderId) return;
    
    try {
      await apiService.moveFolder(
        parseInt(appId!),
        parseInt(repositoryId!),
        folderActionData.folderId,
        newParentFolderId || undefined
      );
      setShowMoveFolderModal(false);
      setNewParentFolderId(null);
      await loadRepository();
    } catch (err) {
      console.error('Error moving folder:', err);
      setError('Failed to move folder');
    }
  };

  // Filter resources by selected folder
  const filteredResources = repository?.resources.filter(resource => {
    if (selectedFolderId === null) {
      return !resource.folder_id; // Show root-level resources
    }
    return resource.folder_id === selectedFolderId;
  }) || [];

  const handleDownloadResource = async (resource: Resource) => {
    try {
      const response = await apiService.downloadResource(parseInt(appId!), parseInt(repositoryId!), resource.resource_id);
      
      // Create a blob from the response and download it
      const blob = new Blob([response], { type: 'application/octet-stream' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = resource.uri; // Use uri which contains the filename with extension
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error('Error downloading resource:', err);
      setError('Failed to download file');
    }
  };

  const handleDeleteResource = (resource: Resource) => {
    setResourceToDelete(resource);
    setShowDeleteModal(true);
  };

  const handleMoveResource = (resource: Resource) => {
    setResourceToMove(resource);
    setMoveToFolderId(null);
    setShowMoveModal(true);
  };

  const confirmDeleteResource = async () => {
    if (!resourceToDelete) return;

    try {
      await apiService.deleteResource(parseInt(appId!), parseInt(repositoryId!), resourceToDelete.resource_id);
      await loadRepository(); // Reload to update the list
      setShowDeleteModal(false);
      setResourceToDelete(null);
    } catch (err) {
      console.error('Error deleting resource:', err);
      setError('Failed to delete file');
    }
  };

  const confirmMoveResource = async () => {
    if (!resourceToMove) return;

    try {
      await apiService.moveResource(
        parseInt(appId!),
        parseInt(repositoryId!),
        resourceToMove.resource_id,
        moveToFolderId || undefined
      );
      
      // Reload repository to get updated file list
      await loadRepository();
      
      setShowMoveModal(false);
      setResourceToMove(null);
      setMoveToFolderId(null);
    } catch (err) {
      console.error('Error moving resource:', err);
      setError('Failed to move file');
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString();
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (!repository) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-900 mb-4">Repository not found</h1>
          <button
            onClick={() => navigate(`/apps/${appId}/repositories`)}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg"
          >
            Back to Repositories
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="flex justify-between items-start mb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <button
              onClick={() => navigate(`/apps/${appId}/repositories`)}
              className="text-gray-500 hover:text-gray-700 transition-colors"
            >
              ← Back
            </button>
            <h1 className="text-3xl font-bold text-gray-900">{repository.name}</h1>
          </div>
          <p className="text-gray-600">
            Created {formatDate(repository.created_at)} • {repository.resources.length} files
          </p>
          
          {/* Breadcrumb Navigation */}
          <div className="mt-2 flex items-center text-sm text-gray-600">
            <button
              onClick={() => handleFolderSelect(null, '')}
              className={`hover:text-blue-600 ${selectedFolderId === null ? 'text-blue-600 font-medium' : ''}`}
            >
              Repository Root
            </button>
            {selectedFolderPath && (
              <>
                <span className="mx-2">/</span>
                <span className="text-blue-600 font-medium">{selectedFolderPath}</span>
              </>
            )}
          </div>
        </div>
        
        <div className="flex gap-3">
          <button
            onClick={() => navigate(`/apps/${appId}/repositories/${repositoryId}/playground`)}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg flex items-center gap-2"
          >
            🔍 Search
          </button>
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg flex items-center gap-2 disabled:opacity-50"
          >
            {uploading ? (
              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
            ) : (
              <span>📁</span>
            )}
            Upload Files
          </button>
        </div>
      </div>

      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        onChange={handleFileUpload}
        className="hidden"
        accept=".pdf,.docx,.txt"
      />

      {/* Error Message */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-6">
          {error}
        </div>
      )}

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Folder Tree Sidebar */}
        <div className="lg:col-span-1">
          <FolderTree
            appId={parseInt(appId!)}
            repositoryId={parseInt(repositoryId!)}
            selectedFolderId={selectedFolderId}
            onFolderSelect={handleFolderSelect}
            onFolderCreate={handleCreateFolder}
            onFolderRename={handleRenameFolder}
            onFolderDelete={handleDeleteFolder}
            onFolderMove={handleMoveFolder}
          />
        </div>

        {/* Files Section */}
        <div className="lg:col-span-3">
          <div className="bg-white border border-gray-200 rounded-lg">
            <div className="px-6 py-4 border-b border-gray-200">
              <h2 className="text-lg font-semibold text-gray-900">
                Files ({filteredResources.length})
                {selectedFolderPath && (
                  <span className="text-sm font-normal text-gray-600 ml-2">
                    in {selectedFolderPath}
                  </span>
                )}
              </h2>
            </div>

            {filteredResources.length === 0 ? (
              <div className="p-8 text-center">
                <div className="text-4xl text-gray-400 mb-4">📄</div>
                <h3 className="text-lg font-medium text-gray-900 mb-2">
                  {selectedFolderId === null ? 'No files in repository root' : 'No files in this folder'}
                </h3>
                <p className="text-gray-600 mb-4">
                  {selectedFolderId === null ? 'Upload your first document to get started' : 'Upload files to this folder'}
                </p>
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg"
                >
                  Upload Files
                </button>
              </div>
            ) : (
              <div className="divide-y divide-gray-200">
                {filteredResources.map((resource) => (
              <div key={resource.resource_id} className="px-6 py-4 flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div className="bg-gray-100 p-2 rounded-lg">
                    <span className="text-gray-600">📄</span>
                  </div>
                  <div>
                    <h3 className="font-medium text-gray-900">{resource.name}</h3>
                    <p className="text-sm text-gray-500">
                      {(resource.file_type || 'unknown').toUpperCase()} • Uploaded {formatDate(resource.created_at)}
                    </p>
                  </div>
                </div>
                
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleMoveResource(resource)}
                    className="p-2 text-gray-400 hover:text-purple-600 transition-colors"
                    title="Move file"
                  >
                    ↔️
                  </button>
                  <button
                    onClick={() => handleDownloadResource(resource)}
                    className="p-2 text-gray-400 hover:text-blue-600 transition-colors"
                    title="Download file"
                  >
                    ⬇️
                  </button>
                  <button
                    onClick={() => handleDeleteResource(resource)}
                    className="p-2 text-gray-400 hover:text-red-600 transition-colors"
                    title="Delete file"
                  >
                    🗑️
                  </button>
                </div>
              </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={showDeleteModal}
        onClose={() => {
          setShowDeleteModal(false);
          setResourceToDelete(null);
        }}
        title="Delete File"
      >
        <div className="p-6">
          <p className="text-gray-700 mb-6">
            Are you sure you want to delete "{resourceToDelete?.name}"? This action cannot be undone.
          </p>
          <div className="flex justify-end gap-3">
            <button
              onClick={() => {
                setShowDeleteModal(false);
                setResourceToDelete(null);
              }}
              className="px-4 py-2 text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={confirmDeleteResource}
              className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors"
            >
              Delete
            </button>
          </div>
        </div>
      </Modal>

      {/* Create Folder Modal */}
      <Modal
        isOpen={showCreateFolderModal}
        onClose={() => setShowCreateFolderModal(false)}
        title="Create Folder"
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Folder Name
            </label>
            <input
              type="text"
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="Enter folder name"
              autoFocus
            />
          </div>
          <div className="flex justify-end space-x-3">
            <button
              onClick={() => setShowCreateFolderModal(false)}
              className="px-4 py-2 text-gray-600 hover:text-gray-800"
            >
              Cancel
            </button>
            <button
              onClick={createFolder}
              disabled={!newFolderName.trim()}
              className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
            >
              Create
            </button>
          </div>
        </div>
      </Modal>

      {/* Rename Folder Modal */}
      <Modal
        isOpen={showRenameFolderModal}
        onClose={() => setShowRenameFolderModal(false)}
        title="Rename Folder"
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Folder Name
            </label>
            <input
              type="text"
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="Enter folder name"
              autoFocus
            />
          </div>
          <div className="flex justify-end space-x-3">
            <button
              onClick={() => setShowRenameFolderModal(false)}
              className="px-4 py-2 text-gray-600 hover:text-gray-800"
            >
              Cancel
            </button>
            <button
              onClick={renameFolder}
              disabled={!newFolderName.trim()}
              className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
            >
              Rename
            </button>
          </div>
        </div>
      </Modal>

      {/* Delete Folder Modal */}
      <Modal
        isOpen={showDeleteFolderModal}
        onClose={() => setShowDeleteFolderModal(false)}
        title="Delete Folder"
      >
        <div className="space-y-4">
          <p className="text-gray-700">
            Are you sure you want to delete the folder "{folderActionData.folderName}"?
            This will also delete all files and subfolders inside it.
          </p>
          <div className="flex justify-end space-x-3">
            <button
              onClick={() => setShowDeleteFolderModal(false)}
              className="px-4 py-2 text-gray-600 hover:text-gray-800"
            >
              Cancel
            </button>
            <button
              onClick={deleteFolder}
              className="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700"
            >
              Delete
            </button>
          </div>
        </div>
      </Modal>

      {/* Move Folder Modal */}
      <Modal
        isOpen={showMoveFolderModal}
        onClose={() => setShowMoveFolderModal(false)}
        title="Move Folder"
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Move "{folderActionData.folderName}" to:
            </label>
            <select
              value={newParentFolderId || ''}
              onChange={(e) => setNewParentFolderId(e.target.value ? parseInt(e.target.value) : null)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">Repository Root</option>
              {/* TODO: Add folder options here */}
            </select>
          </div>
          <div className="flex justify-end space-x-3">
            <button
              onClick={() => setShowMoveFolderModal(false)}
              className="px-4 py-2 text-gray-600 hover:text-gray-800"
            >
              Cancel
            </button>
            <button
              onClick={moveFolder}
              className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
            >
              Move
            </button>
          </div>
        </div>
      </Modal>

      {/* Move File Modal */}
      <Modal
        isOpen={showMoveModal}
        onClose={() => setShowMoveModal(false)}
        title="Move File"
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Move "{resourceToMove?.name}" to:
            </label>
            <select
              value={moveToFolderId || ''}
              onChange={(e) => setMoveToFolderId(e.target.value ? parseInt(e.target.value) : null)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">Repository Root</option>
              {repository?.folders?.map((folder) => (
                <option key={folder.folder_id} value={folder.folder_id}>
                  {folder.name}
                </option>
              ))}
            </select>
          </div>
          <div className="flex justify-end space-x-3">
            <button
              onClick={() => setShowMoveModal(false)}
              className="px-4 py-2 text-gray-600 hover:text-gray-800"
            >
              Cancel
            </button>
            <button
              onClick={confirmMoveResource}
              className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
            >
              Move
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default RepositoryDetailPage; 