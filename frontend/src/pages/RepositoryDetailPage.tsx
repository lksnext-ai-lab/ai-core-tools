import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { apiService } from '../services/api';
import Modal from '../components/ui/Modal';
import FolderTree from '../components/FolderTree';
import StatusBadge from '../components/StatusBadge';
import Alert from '../components/ui/Alert';
import { useAppRole } from '../hooks/useAppRole';
import { AppRole } from '../types/roles';
import ReadOnlyBanner from '../components/ui/ReadOnlyBanner';

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
  ai_services: Array<{
    service_id: number;
    name: string;
  }>;
  media: Media[];
}

  interface Media {
    media_id: number;
    name: string;
    source_type: string;
    source_url: string | null;
    duration: number | null;
    language: string | null;
    status: string;
    error_message: string | null;
    create_date: string;
    folder_id: number | null;
  }

const RepositoryDetailPage: React.FC = () => {
  const { appId, repositoryId } = useParams<{ appId: string; repositoryId: string }>();
  const { hasMinRole, userRole } = useAppRole(appId);
  const canEdit = hasMinRole(AppRole.EDITOR);
  
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

  // Media 
  const [showMediaUploadModal, setShowMediaUploadModal] = useState(false);
  const [mediaFiles, setMediaFiles] = useState<File[]>([]);
  const [youtubeUrl, setYoutubeUrl] = useState('');
  const [uploadType, setUploadType] = useState<'file' | 'youtube'>('file');
  const [pollingIntervals, setPollingIntervals] = useState<Map<number, NodeJS.Timeout>>(new Map());
  const [selectedTranscriptionServiceId, setSelectedTranscriptionServiceId] = useState<number | null>(null);
  const [mediaConfig, setMediaConfig] = useState({
    forced_language: '',
    chunk_min_duration: 30,
    chunk_max_duration: 120,
    chunk_overlap: 5
  });

  // Media delete / move state
  const [showDeleteMediaModal, setShowDeleteMediaModal] = useState(false);
  const [mediaToDelete, setMediaToDelete] = useState<Media | null>(null);

  const [showMoveMediaModal, setShowMoveMediaModal] = useState(false);
  const [mediaToMove, setMediaToMove] = useState<Media | null>(null);
  const [moveMediaToFolderId, setMoveMediaToFolderId] = useState<number | null>(null);

  useEffect(() => {
    if (appId && repositoryId) {
      loadRepository();
    }
  }, [appId, repositoryId]);

  useEffect(() => {
    return () => {
      pollingIntervals.forEach(interval => clearInterval(interval));
    };
  }, [pollingIntervals]);

  const startPolling = (mediaId: number) => {
    if (pollingIntervals.has(mediaId)) return;
    
    const interval = setInterval(async () => {
      try {
        const media = await apiService.getMediaStatus(parseInt(appId!), parseInt(repositoryId!), mediaId);
        
        setRepository(prev => prev ? {
          ...prev,
          media: prev.media.map(m => m.media_id === mediaId ? media : m)
        } : prev);
        
        if (media.status === 'ready' || media.status === 'error') {
          stopPolling(mediaId);
        }
      } catch (err) {
        console.error('Polling error:', err);
        stopPolling(mediaId);
      }
    }, 3000);
    
    setPollingIntervals(prev => new Map(prev).set(mediaId, interval));
  };

  const stopPolling = (mediaId: number) => {
    const interval = pollingIntervals.get(mediaId);
    if (interval) {
      clearInterval(interval);
      setPollingIntervals(prev => {
        const newMap = new Map(prev);
        newMap.delete(mediaId);
        return newMap;
      });
    }
  };

  const loadRepository = async (clearError: boolean = true) => {
    try {
      setLoading(true);
      const data = await apiService.getRepository(parseInt(appId!), parseInt(repositoryId!));
      setRepository(data);
      
      // Start polling for processing media
      data.media?.forEach((m: Media) => {
        if (m.status !== 'ready' && m.status !== 'error') {
          startPolling(m.media_id);
        }
      });
      
      if (clearError) setError(null);
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
      const result = await apiService.uploadResources(parseInt(appId!), parseInt(repositoryId!), Array.from(files), selectedFolderId || undefined);
      
      console.log('Upload result:', result);
      
      // Check if there are any failed files
      if (result.failed_files && result.failed_files.length > 0) {
        console.log('Failed files detected:', result.failed_files);
        const failedMessages = result.failed_files.map((failed: any) => 
          `${failed.filename}: ${failed.error}`
        ).join('\n');
        
        console.log('Failed messages:', failedMessages);
        
        if (result.created_resources && result.created_resources.length > 0) {
          // Some files succeeded, some failed
          setError(`Some files failed to upload:\n${failedMessages}`);
        } else {
          // All files failed
          setError(`Upload failed:\n${failedMessages}`);
        }
      } else {
        console.log('No failed files detected');
      }
      
      // Reload repository to get updated file list (even if some files failed)
      // Don't clear error if we just set one for failed files
      await loadRepository(false);
      
      // Clear file input
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    } catch (err: any) {
      console.error('Error uploading files:', err);
      setError(err.message || 'Failed to upload files');
    } finally {
      setUploading(false);
    }
  };

  const handleMediaUpload = async () => {
    try {
      setUploading(true);
      setError(null);

      if (uploadType === 'file') {
        const result = await apiService.uploadMedia(
          parseInt(appId!),
          parseInt(repositoryId!),
          mediaFiles,
          selectedFolderId || undefined,
          mediaConfig,
          selectedTranscriptionServiceId || undefined
        );
        
        if (result.failed_files?.length > 0) {
          const failedMessages = result.failed_files.map((f: any) => 
            `${f.filename}: ${f.error}`
          ).join('\n');
          setError(`Some files failed:\n${failedMessages}`);
        }
      } else {
        await apiService.addYouTube(
          parseInt(appId!),
          parseInt(repositoryId!),
          youtubeUrl,
          selectedFolderId || undefined,
          mediaConfig,
          selectedTranscriptionServiceId || undefined
        );
      }
      
      setShowMediaUploadModal(false);
      setMediaFiles([]);
      setYoutubeUrl('');
      await loadRepository(false);
    } catch (err: any) {
      setError(err.message || 'Failed to upload media');
    } finally {
      setUploading(false);
    }
  };

  // Folder management functions
  const handleFolderSelect = (folderId: number | null, folderPath: string) => {
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
    setNewParentFolderId(null); // Start with no selection so user can choose
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
    } catch (err: any) {
      console.error('Error creating folder:', err);
      const errorMessage = err?.response?.data?.detail || err?.message || 'Failed to create folder';
      setError(errorMessage);
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
    } catch (err: any) {
      console.error('Error renaming folder:', err);
      const errorMessage = err?.response?.data?.detail || err?.message || 'Failed to rename folder';
      setError(errorMessage);
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
    } catch (err: any) {
      console.error('Error deleting folder:', err);
      const errorMessage = err?.response?.data?.detail || err?.message || 'Failed to delete folder';
      setError(errorMessage);
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
    } catch (err: any) {
      console.error('Error moving folder:', err);
      const errorMessage = err?.response?.data?.detail || err?.message || 'Failed to move folder';
      setError(errorMessage);
    }
  };

  // Get all folder paths for display and filtering
  const getAllFolderPaths = (folders: any[], parentPath: string = ''): Array<{folder_id: number, name: string, full_path: string}> => {
    const result: Array<{folder_id: number, name: string, full_path: string}> = [];
    
    for (const folder of folders) {
      const fullPath = parentPath ? `${parentPath}/${folder.name}` : folder.name;
      result.push({
        folder_id: folder.folder_id,
        name: folder.name,
        full_path: fullPath
      });
      
      if (folder.subfolders && folder.subfolders.length > 0) {
        result.push(...getAllFolderPaths(folder.subfolders, fullPath));
      }
    }
    
    return result;
  };

  // Get valid destination folders (exclude the folder being moved and its descendants)
  const getValidDestinationFolders = () => {
    if (!repository?.folders || !folderActionData.folderId) return [];
    
    // Get all folder paths
    const allFolders = getAllFolderPaths(repository.folders);
    
    // Filter out the folder being moved and its descendants
    const validFolders = allFolders.filter(folder => {
      // Don't allow moving to the same folder
      if (folder.folder_id === folderActionData.folderId) return false;
      
      // Don't allow moving to descendants (this would create circular reference)
      // For now, we'll rely on backend validation, but we could add frontend validation here
      return true;
    });
    
    return validFolders;
  };

  // Filter resources by selected folder
  const filteredResources = repository?.resources.filter(resource => {
    if (selectedFolderId === null) {
      return !resource.folder_id; // Show root-level resources
    }
    return resource.folder_id === selectedFolderId;
  }) || [];

  // Filter media by selected folder
  const filteredMedia = repository?.media.filter(media => {
    if (selectedFolderId === null) {
      return !media.folder_id;
    }
    return media.folder_id === selectedFolderId;
  }) || [];

  const isEmpty =
  filteredResources.length === 0 && filteredMedia.length === 0;

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

  const handleDeleteMedia = (media: Media) => {
    setMediaToDelete(media);
    setShowDeleteMediaModal(true);
  };

  const confirmDeleteMedia = async () => {
    if (!mediaToDelete) return;

    try {
      await apiService.deleteMedia(
        parseInt(appId!),
        parseInt(repositoryId!),
        mediaToDelete.media_id
      );
      await loadRepository();
      setShowDeleteMediaModal(false);
      setMediaToDelete(null);
    } catch (err) {
      console.error(err);
      setError('Failed to delete media');
    }
  };

  const handleMoveMedia = (media: Media) => {
    setMediaToMove(media);
    setMoveMediaToFolderId(null);
    setShowMoveMediaModal(true);
  };

  const confirmMoveMedia = async () => {
    if (!mediaToMove) return;

    try {
      await apiService.moveMedia(
        parseInt(appId!),
        parseInt(repositoryId!),
        mediaToMove.media_id,
        moveMediaToFolderId || undefined
      );
      await loadRepository();
      setShowMoveMediaModal(false);
      setMediaToMove(null);
      setMoveMediaToFolderId(null);
    } catch (err) {
      console.error(err);
      setError('Failed to move media');
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString();
  };

  console.log('Repository:', repository);
  console.log('Media:', repository?.media);
  console.log('Filtered media:', filteredMedia);

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
          {canEdit && (
            <>
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

              <button
                onClick={() => {
                  setSelectedTranscriptionServiceId(null);
                  setShowMediaUploadModal(true);
                }}
                disabled={uploading}
                className="bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-lg flex items-center gap-2 disabled:opacity-50"
              >
                🎥 Upload Media
              </button>
            </>
          )}
        </div>
      </div>

      {!canEdit && <ReadOnlyBanner userRole={userRole} minRole={AppRole.EDITOR} />}

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
      {error && <Alert type="error" message={error} onDismiss={() => setError(null)} className="mb-6" />}

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Folder Tree Sidebar */}
        <div className="lg:col-span-1">
          <FolderTree
            appId={parseInt(appId!)}
            repositoryId={parseInt(repositoryId!)}
            selectedFolderId={selectedFolderId ?? undefined}
            onFolderSelect={handleFolderSelect}
            onFolderCreate={handleCreateFolder}
            onFolderRename={handleRenameFolder}
            onFolderDelete={handleDeleteFolder}
            onFolderMove={handleMoveFolder}
            canEdit={canEdit}
          />
        </div>

        {/* Files + Media Section */}
        <div className="lg:col-span-3">
          <div className="bg-white border border-gray-200 rounded-lg">
            <div className="px-6 py-4 border-b border-gray-200">
              <h2 className="text-lg font-semibold text-gray-900">
                Files ({filteredResources.length + filteredMedia.length})
                {selectedFolderPath && (
                  <span className="text-sm font-normal text-gray-600 ml-2">
                    in {selectedFolderPath}
                  </span>
                )}
              </h2>
            </div>

            {/* ✅ SHARED EMPTY STATE */}
            {isEmpty ? (
              <div className="p-10 text-center">
                <div className="flex justify-center gap-6 mb-4 text-4xl">
                  <span className="text-gray-400">📄</span>
                  <span className="text-gray-400">🎥</span>
                </div>

                <h3 className="text-lg font-medium text-gray-900 mb-2">
                  {selectedFolderId === null
                    ? 'No files or media in repository root'
                    : 'No files or media in this folder'}
                </h3>

                <p className="text-gray-600 mb-6">
                  {selectedFolderId === null
                    ? 'Upload documents or media to get started'
                    : 'Upload files or media to this folder'}
                </p>

                {canEdit && (
                  <div className="flex justify-center gap-3">
                    <button
                      onClick={() => fileInputRef.current?.click()}
                      className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg"
                    >
                      Upload Files
                    </button>

                    <button
                      onClick={() => setShowMediaUploadModal(true)}
                      className="bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-lg"
                    >
                      Upload Media
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <>
                {/* ✅ FILES LIST */}
                {filteredResources.length > 0 && (
                  <div className="divide-y divide-gray-200">
                    {filteredResources.map((resource) => (
                      <div
                        key={resource.resource_id}
                        className="px-6 py-4 flex items-center justify-between"
                      >
                        <div className="flex items-center gap-4">
                          <div className="bg-gray-100 p-2 rounded-lg">📄</div>
                          <div>
                            <h3 className="font-medium text-gray-900">
                              {resource.name}
                            </h3>
                            <p className="text-sm text-gray-500">
                              {(resource.file_type || 'unknown').toUpperCase()} • Uploaded{' '}
                              {formatDate(resource.created_at)}
                            </p>
                          </div>
                        </div>

                        <div className="flex items-center gap-2">
                          {canEdit && (
                            <button
                              onClick={() => handleMoveResource(resource)}
                              className="p-2 text-gray-400 hover:text-purple-600"
                            >
                              ↔️
                            </button>
                          )}
                          <button
                            onClick={() => handleDownloadResource(resource)}
                            className="p-2 text-gray-400 hover:text-blue-600"
                          >
                            ⬇️
                          </button>
                          {canEdit && (
                            <button
                              onClick={() => handleDeleteResource(resource)}
                              className="p-2 text-gray-400 hover:text-red-600"
                            >
                              🗑️
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* ✅ MEDIA LIST */}
                {filteredMedia.length > 0 && (
                  <div className="divide-y divide-gray-200 border-t">
                    {filteredMedia.map((media) => (
                      <div key={media.media_id} className="px-6 py-4">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-4">
                            <div className="bg-purple-100 p-2 rounded-lg">🎥</div>
                            <div>
                              <h4 className="font-medium text-gray-900">
                                {media.name}
                              </h4>
                              <p className="text-sm text-gray-500">
                                {media.source_type.toUpperCase()} •{' '}
                                {media.language || 'detecting...'} •{' '}
                                {media.duration
                                  ? `${media.duration.toFixed(1)}s`
                                  : 'processing...'}
                              </p>
                            </div>
                          </div>

                          <div className="flex items-center gap-2">
                            <StatusBadge status={media.status} />

                            {canEdit && (
                              <>
                                <button
                                  onClick={() => handleMoveMedia(media)}
                                  className="p-2 text-gray-400 hover:text-purple-600"
                                >
                                  ↔️
                                </button>
                                <button
                                  onClick={() => handleDeleteMedia(media)}
                                  className="p-2 text-gray-400 hover:text-red-600"
                                >
                                  🗑️
                                </button>
                              </>
                            )}
                          </div>
                        </div>

                        {media.error_message && (
                          <p className="text-sm text-red-600 mt-2">
                            {media.error_message}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </>
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
            <label htmlFor="create-folder-name" className="block text-sm font-medium text-gray-700 mb-2">
              Folder Name
            </label>
            <input
              id="create-folder-name"
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
            <label htmlFor="rename-folder-name" className="block text-sm font-medium text-gray-700 mb-2">
              Folder Name
            </label>
            <input
              id="rename-folder-name"
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

      {/* Delete Media Modal */}
      <Modal
        isOpen={showDeleteMediaModal}
        onClose={() => {
          setShowDeleteMediaModal(false);
          setMediaToDelete(null);
        }}
        title="Delete Media"
      >
        <div className="p-6">
          <p className="text-gray-700 mb-6">
            Are you sure you want to delete "{mediaToDelete?.name}"?
            This action cannot be undone.
          </p>
          <div className="flex justify-end gap-3">
            <button
              onClick={() => setShowDeleteMediaModal(false)}
              className="px-4 py-2 bg-gray-100 rounded-lg"
            >
              Cancel
            </button>
            <button
              onClick={confirmDeleteMedia}
              className="px-4 py-2 bg-red-600 text-white rounded-lg"
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
              {getValidDestinationFolders().map((folder) => (
                <option key={folder.folder_id} value={folder.folder_id}>
                  {folder.full_path}
                </option>
              ))}
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

      {/* Move Media Modal */}
      <Modal
        isOpen={showMoveMediaModal}
        onClose={() => setShowMoveMediaModal(false)}
        title="Move Media"
      >
        <div className="space-y-4">
          <label className="block text-sm font-medium text-gray-700">
            Move "{mediaToMove?.name}" to:
          </label>

          <select
            value={moveMediaToFolderId || ''}
            onChange={(e) =>
              setMoveMediaToFolderId(
                e.target.value ? parseInt(e.target.value) : null
              )
            }
            className="w-full px-3 py-2 border rounded-md"
          >
            <option value="">Repository Root</option>
            {repository?.folders &&
              getAllFolderPaths(repository.folders).map((folder) => (
                <option key={folder.folder_id} value={folder.folder_id}>
                  {folder.full_path}
                </option>
              ))}
          </select>

          <div className="flex justify-end gap-3">
            <button
              onClick={() => setShowMoveMediaModal(false)}
              className="px-4 py-2 bg-gray-100 rounded-lg"
            >
              Cancel
            </button>
            <button
              onClick={confirmMoveMedia}
              className="px-4 py-2 bg-purple-600 text-white rounded-lg"
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
              {repository?.folders ? getAllFolderPaths(repository.folders).map((folder) => (
                <option key={folder.folder_id} value={folder.folder_id}>
                  {folder.full_path}
                </option>
              )) : null}
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

      {/* Media Upload Modal */}
      <Modal
        isOpen={showMediaUploadModal}
        onClose={() => {
          setShowMediaUploadModal(false);
          setMediaFiles([]);
          setYoutubeUrl('');
          setSelectedTranscriptionServiceId(null);
        }}
        title="Upload Media"
      >
        <div className="space-y-4">
          {/* Upload Type */}
          <div className="flex gap-2">
            <button
              onClick={() => setUploadType('file')}
              className={`flex-1 px-4 py-2 rounded ${uploadType === 'file' ? 'bg-purple-600 text-white' : 'bg-gray-100'}`}
            >
              📁 File Upload
            </button>
            <button
              onClick={() => setUploadType('youtube')}
              className={`flex-1 px-4 py-2 rounded ${uploadType === 'youtube' ? 'bg-purple-600 text-white' : 'bg-gray-100'}`}
            >
              📺 YouTube URL
            </button>
          </div>

          {/* File Upload */}
          {uploadType === 'file' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Select Video/Audio Files
              </label>
              <input
                type="file"
                multiple
                accept="video/*,audio/*"
                onChange={(e) => setMediaFiles(Array.from(e.target.files || []))}
                className="w-full"
              />
              {mediaFiles.length > 0 && (
                <p className="text-sm text-gray-600 mt-2">{mediaFiles.length} file(s) selected</p>
              )}
            </div>
          )}

          {/* YouTube URL */}
          {uploadType === 'youtube' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                YouTube URL
              </label>
              <input
                type="text"
                value={youtubeUrl}
                onChange={(e) => setYoutubeUrl(e.target.value)}
                placeholder="https://youtube.com/watch?v=..."
                className="w-full px-3 py-2 border border-gray-300 rounded-md"
              />
            </div>
          )}

          {/* Configuration */}
          <div className="border-t pt-4">
            <h3 className="font-medium mb-3">Processing Options</h3>
            
            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Transcription Service *</label>
                {!repository?.ai_services || repository.ai_services.length === 0 ? (
                  <div className="text-sm text-red-600 bg-red-50 p-2 rounded">
                    No transcription services available. Please create an AI service.
                  </div>
                ) : (
                  <select
                    value={selectedTranscriptionServiceId || ''}
                    onChange={(e) => setSelectedTranscriptionServiceId(e.target.value ? parseInt(e.target.value) : null)}
                    className="w-full px-3 py-2 border rounded-md text-sm"
                  >
                    <option value="">-- Select a Transcription Service --</option>
                    {repository.ai_services.map(service => (
                      <option key={service.service_id} value={service.service_id}>
                        {service.name}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              <div>
                <label className="block text-sm text-gray-700 mb-1">Language (optional)</label>
                <select
                  value={mediaConfig.forced_language}
                  onChange={(e) => setMediaConfig({...mediaConfig, forced_language: e.target.value})}
                  className="w-full px-3 py-2 border rounded-md text-sm"
                >
                  <option value="">Auto-detect</option>
                  <option value="es">Spanish</option>
                  <option value="en">English</option>
                  <option value="eu">Basque</option>
                  <option value="fr">French</option>
                </select>
              </div>

              <div className="grid grid-cols-3 gap-2">
                <div>
                  <label className="block text-xs text-gray-700 mb-1">Min Chunk (s)</label>
                  <input
                    type="number"
                    value={mediaConfig.chunk_min_duration}
                    onChange={(e) => setMediaConfig({...mediaConfig, chunk_min_duration: parseInt(e.target.value)})}
                    className="w-full px-2 py-1 border rounded text-sm"
                    min="10"
                    max="60"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-700 mb-1">Max Chunk (s)</label>
                  <input
                    type="number"
                    value={mediaConfig.chunk_max_duration}
                    onChange={(e) => setMediaConfig({...mediaConfig, chunk_max_duration: parseInt(e.target.value)})}
                    className="w-full px-2 py-1 border rounded text-sm"
                    min="60"
                    max="300"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-700 mb-1">Overlap (s)</label>
                  <input
                    type="number"
                    value={mediaConfig.chunk_overlap}
                    onChange={(e) => setMediaConfig({...mediaConfig, chunk_overlap: parseInt(e.target.value)})}
                    className="w-full px-2 py-1 border rounded text-sm"
                    min="0"
                    max="20"
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-4 border-t">
            <button
              onClick={() => setShowMediaUploadModal(false)}
              className="px-4 py-2 text-gray-600 hover:text-gray-800"
            >
              Cancel
            </button>
            <button
              onClick={handleMediaUpload}
              disabled={
                selectedTranscriptionServiceId === null ||
                (uploadType === 'file' ? mediaFiles.length === 0 : !youtubeUrl)
              }
              className="px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700 disabled:opacity-50"
            >
              {uploading ? 'Uploading...' : 'Upload'}
            </button>
          </div>
        </div>
      </Modal>

    </div>
  );
};

export default RepositoryDetailPage; 