import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Clapperboard, Mic, FolderOpen, Folder, Home, ChevronRight, Video, FileText, ArrowDownToLine, ArrowLeftRight, Trash2, Tv, Search, RefreshCw } from 'lucide-react';
import { apiService } from '../services/api';
import Modal from '../components/ui/Modal';
import FolderTree from '../components/FolderTree';
import { StatusBadge, type StatusType } from '../components/ui/Badge';
import Alert from '../components/ui/Alert';
import { useAppRole } from '../hooks/useAppRole';
import { AppRole } from '../types/roles';
import ReadOnlyBanner from '../components/ui/ReadOnlyBanner';
import { Title } from '../components/ui/Title';
import { ButtonApp } from '../components/ui/ButtonApp';
import BackgroundImage from '../components/ui/BackgroundImage';
import { FormField, FormSelect } from '../components/ui/FormField';
import { LoadingState } from '../components/ui/LoadingState';
import { Spinner } from '../components/ui/Spinner';
import type { ServiceLifecycleWarning } from '../types/services';
import ServiceLifecycleAlert from '../components/services/ServiceLifecycleAlert';

interface Resource {
  resource_id: number;
  name: string;
  uri: string;
  file_type: string;
  created_at: string;
  folder_id?: number;
  folder_path?: string;
  status?: string | null;
  error_message?: string | null;
}

interface RepositoryDetail {
  repository_id: number;
  silo_id?: number;
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
    supports_video?: boolean;
  }>;
  media: Media[];
  transcription_service_id?: number | null;
  video_ai_service_id?: number | null;
  service_warnings?: string[];
  lifecycle_warnings?: ServiceLifecycleWarning[];
}

  interface Media {
    media_id: number;
    name: string;
    source_type: string;
    source_url: string | null;
    duration: number | null;
    language: string | null;
    status: string;
    processing_mode: string | null;
    error_message: string | null;
    create_date: string;
    folder_id: number | null;
  }

function isTerminalMediaStatus(status: string): boolean {
  return status === 'ready' || status === 'error';
}

const IN_PROGRESS_MEDIA_STATUSES = new Set(['downloading', 'processing', 'transcribing', 'analyzing_video', 'indexing']);

function getMediaStatusBadgeType(status: string): StatusType {
  if (status === 'ready') return 'success';
  if (status === 'error') return 'error';
  if (status === 'pending') return 'pending';
  if (IN_PROGRESS_MEDIA_STATUSES.has(status)) return 'processing';
  return 'inactive';
}

function filterByFolder<T extends { folder_id?: number | null }>(
  items: T[] | undefined,
  selectedFolderId: number | null
): T[] {
  if (!items) return [];
  return items.filter(item =>
    selectedFolderId === null ? !item.folder_id : item.folder_id === selectedFolderId
  );
}

function updateMediaInRepo(prev: RepositoryDetail | null, mediaId: number, media: Media): RepositoryDetail | null {
  if (!prev) return null;
  return {
    ...prev,
    media: prev.media.map(m => (m.media_id === mediaId ? media : m)),
  };
}

// Ancestors of the selected folder (root excluded), each with its full path, for the breadcrumb
function getFolderTrail(
  folders: RepositoryDetail['folders'] | undefined,
  folderId: number | null
): Array<{ folder_id: number; name: string; path: string }> {
  if (!folders || folderId === null) return [];
  const byId = new Map(folders.map(f => [f.folder_id, f]));
  const chain: RepositoryDetail['folders'] = [];
  let current = byId.get(folderId);
  while (current && chain.length < folders.length) {
    chain.unshift(current);
    current = current.parent_folder_id ? byId.get(current.parent_folder_id) : undefined;
  }
  let path = '';
  return chain.map(f => {
    path = path ? `${path}/${f.name}` : f.name;
    return { folder_id: f.folder_id, name: f.name, path };
  });
}

function getAllFolderPaths(
  folders: Array<{ folder_id: number; name: string; subfolders?: Array<{ folder_id: number; name: string; subfolders?: unknown[] }> }>,
  parentPath: string = ''
): Array<{ folder_id: number; name: string; full_path: string }> {
  const result: Array<{ folder_id: number; name: string; full_path: string }> = [];
  for (const folder of folders) {
    const fullPath = parentPath ? `${parentPath}/${folder.name}` : folder.name;
    result.push({ folder_id: folder.folder_id, name: folder.name, full_path: fullPath });
    if (folder.subfolders && folder.subfolders.length > 0) {
      result.push(...getAllFolderPaths(folder.subfolders as Parameters<typeof getAllFolderPaths>[0], fullPath));
    }
  }
  return result;
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
  const [reindexingId, setReindexingId] = useState<number | null>(null);
  const [reindexNotice, setReindexNotice] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  
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
  const pollingIntervalsRef = useRef<Map<number, NodeJS.Timeout>>(new Map());
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
      void loadRepository();
    }
  }, [appId, repositoryId]);

  useEffect(() => {
    return () => {
      pollingIntervalsRef.current.forEach(interval => clearInterval(interval));
    };
  }, []);

  const startPolling = (mediaId: number) => {
    if (pollingIntervalsRef.current.has(mediaId)) return;
    
    const interval = setInterval(async () => {
      try {
        const media = await apiService.getMediaStatus(Number.parseInt(appId!), Number.parseInt(repositoryId!), mediaId);
        setRepository(prev => updateMediaInRepo(prev, mediaId, media));
        if (isTerminalMediaStatus(media.status)) {
          stopPolling(mediaId);
        }
      } catch (err) {
        console.error('Polling error:', err);
        stopPolling(mediaId);
      }
    }, 3000);
    
    pollingIntervalsRef.current.set(mediaId, interval);
  };

  const stopPolling = (mediaId: number) => {
    const interval = pollingIntervalsRef.current.get(mediaId);
    if (interval) {
      clearInterval(interval);
      pollingIntervalsRef.current.delete(mediaId);
    }
  };

  const loadRepository = async (clearError: boolean = true) => {
    try {
      setLoading(true);
      const data = await apiService.getRepository(Number.parseInt(appId!), Number.parseInt(repositoryId!));
      setRepository(data);
      
      // Start polling for processing media
      data.media?.forEach((m: Media) => {
        if (m.status !== 'ready' && m.status !== 'error' && !pollingIntervalsRef.current.has(m.media_id)) {
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
      const result = await apiService.uploadResources(Number.parseInt(appId!), Number.parseInt(repositoryId!), Array.from(files), selectedFolderId || undefined);
      
      console.log('Upload result:', result);
      
      const problems: string[] = [];
      // Files rejected before upload
      if (result.failed_files && result.failed_files.length > 0) {
        const failedMessages = result.failed_files.map((failed) => `${failed.filename}: ${failed.error}`).join('\n');
        const allFailed = !result.created_resources || result.created_resources.length === 0;
        problems.push(`${allFailed ? 'Upload failed' : 'Some files failed to upload'}:\n${failedMessages}`);
      }
      // Uploaded but not indexed (e.g. the embedding service rejected its API key)
      if (result.indexing_failures && result.indexing_failures.length > 0) {
        const indexingMessages = result.indexing_failures.map((failed) => `${failed.filename}: ${failed.error}`).join('\n');
        problems.push(`Uploaded, but indexing failed (not searchable until reindexed):\n${indexingMessages}`);
      }
      if (problems.length > 0) {
        setError(problems.join('\n\n'));
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
          Number.parseInt(appId!),
          Number.parseInt(repositoryId!),
          mediaFiles,
          selectedFolderId || undefined,
          mediaConfig,
        );
        
        if (result.failed_files && result.failed_files.length > 0) {
          const failedMessages = result.failed_files.map((f: any) => 
            `${f.filename}: ${f.error}`
          ).join('\n');
          setError(`Some files failed:\n${failedMessages}`);
        }
      } else {
        await apiService.addYouTube(
          Number.parseInt(appId!),
          Number.parseInt(repositoryId!),
          youtubeUrl,
          selectedFolderId || undefined,
          mediaConfig,
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
        Number.parseInt(appId!),
        Number.parseInt(repositoryId!),
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
        Number.parseInt(appId!),
        Number.parseInt(repositoryId!),
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
        Number.parseInt(appId!),
        Number.parseInt(repositoryId!),
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
        Number.parseInt(appId!),
        Number.parseInt(repositoryId!),
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

  // Get valid destination folders (exclude the folder being moved and its descendants)
  const getValidDestinationFolders = () => {
    if (!repository?.folders || !folderActionData.folderId) return [];
    const allFolders = getAllFolderPaths(repository.folders);
    // Backend validates circular references; frontend just excludes the moved folder itself
    return allFolders.filter(folder => folder.folder_id !== folderActionData.folderId);
  };

  // Filter resources by selected folder
  const filteredResources = filterByFolder(repository?.resources, selectedFolderId);

  // Filter media by selected folder
  const filteredMedia = filterByFolder(repository?.media, selectedFolderId);

  // Direct subfolders of the selected folder, listed as rows in the files table
  const subfolders = (repository?.folders ?? []).filter(
    f => (f.parent_folder_id ?? null) === selectedFolderId
  );
  const folderTrail = getFolderTrail(repository?.folders, selectedFolderId);
  const countFolderItems = (folderId: number) =>
    (repository?.resources ?? []).filter(r => r.folder_id === folderId).length +
    (repository?.media ?? []).filter(m => m.folder_id === folderId).length;

  const isEmpty =
  subfolders.length === 0 && filteredResources.length === 0 && filteredMedia.length === 0;

  const handleDownloadResource = async (resource: Resource) => {
    try {
      const response = await apiService.downloadResource(Number.parseInt(appId!), Number.parseInt(repositoryId!), resource.resource_id);
      
      // Create a blob from the response and download it
      const blob = new Blob([response], { type: 'application/octet-stream' });
      const url = globalThis.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = resource.uri; // Use uri which contains the filename with extension
      document.body.appendChild(a);
      a.click();
      globalThis.URL.revokeObjectURL(url);
      a.remove();
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

  const handleReindexResource = async (resource: Resource) => {
    if (reindexingId !== null) return;
    const siloId = repository?.silo_id;
    if (!siloId) {
      setReindexNotice({ type: 'error', text: 'This repository is not linked to a silo.' });
      return;
    }
    setReindexingId(resource.resource_id);
    setReindexNotice(null);
    try {
      await apiService.reindexSiloResource(Number.parseInt(appId!), siloId, resource.resource_id);
      setReindexNotice({ type: 'success', text: `"${resource.name}" reindexed successfully.` });
    } catch (err) {
      setReindexNotice({ type: 'error', text: err instanceof Error ? err.message : 'Reindex failed' });
    } finally {
      await loadRepository(false);
      setReindexingId(null);
      setTimeout(() => setReindexNotice(null), 4000);
    }
  };

  const confirmDeleteResource = async () => {
    if (!resourceToDelete) return;

    try {
      await apiService.deleteResource(Number.parseInt(appId!), Number.parseInt(repositoryId!), resourceToDelete.resource_id);
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
        Number.parseInt(appId!),
        Number.parseInt(repositoryId!),
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
      stopPolling(mediaToDelete.media_id);  // Add this - stop polling before delete
      
      await apiService.deleteMedia(
        Number.parseInt(appId!),
        Number.parseInt(repositoryId!),
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
        Number.parseInt(appId!),
        Number.parseInt(repositoryId!),
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

  if (loading) {
    return (
      <LoadingState variant="page" />
    );
  }

  if (!repository) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-fg dark:text-fg-dark mb-4">Repository not found</h1>
          <ButtonApp
            label="Back to Repositories"
            variant="secondary"
            size="medium"
            onClick={() => navigate(`/apps/${appId}/repositories`)}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <Title
          titulo={repository.name}
          subtitulo={`Created ${formatDate(repository.created_at)} • ${repository.resources.length} files`}
          subtitleMarginBottom={0}
        />
        {(repository.transcription_service_id || repository.video_ai_service_id) && (
          <p className="text-sm text-fg-tertiary dark:text-fg-tertiary-dark mt-1">
            {repository.transcription_service_id && (
              <span className="inline-flex items-center gap-1 mr-3">
                <Mic className="w-4 h-4" aria-hidden="true" /> <span>Transcription: {repository.ai_services.find(s => s.service_id === repository.transcription_service_id)?.name ?? `Service #${repository.transcription_service_id}`}</span>
              </span>
            )}
            {repository.video_ai_service_id && (
              <span className="inline-flex items-center gap-1">
                <Clapperboard className="w-4 h-4" aria-hidden="true" /> <span>Video AI: {repository.ai_services.find(s => s.service_id === repository.video_ai_service_id)?.name ?? `Service #${repository.video_ai_service_id}`}</span>
              </span>
            )}
          </p>
        )}
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
      {reindexNotice && <Alert type={reindexNotice.type} message={reindexNotice.text} onDismiss={() => setReindexNotice(null)} className="mb-6" />}
      <ServiceLifecycleAlert warnings={repository?.lifecycle_warnings} variant="full" className="mb-6" />
      {repository?.service_warnings?.map((warning) => (
        <Alert
          key={warning}
          type="warning"
          title="A service used by this repository is failing"
          message={`${warning} Check the service settings (or ask your platform administrator for system services), then reindex the affected files.`}
          className="mb-6"
        />
      ))}

      {/* Explorer: folder tree + files */}
      <div className="grid grid-cols-1 lg:grid-cols-[240px_minmax(0,1fr)] bg-surface border border-line rounded-lg dark:bg-surface-dark dark:border-line-dark">
        {/* Folder Tree Sidebar */}
        <div className="bg-surface-tint border-b border-line rounded-t-lg lg:border-b-0 lg:border-r lg:rounded-tr-none lg:rounded-l-lg dark:bg-surface-tint-dark dark:border-line-dark">
          <FolderTree
            appId={Number.parseInt(appId!)}
            repositoryId={Number.parseInt(repositoryId!)}
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
        <div className="min-w-0">
          {/* Toolbar: breadcrumb + actions */}
          <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-3 border-b border-line dark:border-line-dark">
            <nav aria-label="Folder path" className="flex flex-wrap items-center gap-1 min-w-0 text-sm">
              <button
                onClick={() => handleFolderSelect(null, '')}
                aria-current={selectedFolderId === null ? 'page' : undefined}
                className={`inline-flex items-center gap-1.5 transition-colors ${
                  selectedFolderId === null
                    ? 'font-medium text-fg dark:text-fg-dark'
                    : 'text-fg-tertiary hover:text-accent dark:text-fg-tertiary-dark dark:hover:text-accent-dark'
                }`}
              >
                <Home className="w-4 h-4" /> Repository Root
              </button>
              {folderTrail.map((crumb, index) => {
                const isCurrent = index === folderTrail.length - 1;
                return (
                  <React.Fragment key={crumb.folder_id}>
                    <ChevronRight className="w-3.5 h-3.5 text-fg-faint2 dark:text-fg-faint2-dark flex-shrink-0" />
                    <button
                      onClick={() => handleFolderSelect(crumb.folder_id, crumb.path)}
                      aria-current={isCurrent ? 'page' : undefined}
                      className={`truncate transition-colors ${
                        isCurrent
                          ? 'font-medium text-fg dark:text-fg-dark'
                          : 'text-fg-tertiary hover:text-accent dark:text-fg-tertiary-dark dark:hover:text-accent-dark'
                      }`}
                    >
                      {crumb.name}
                    </button>
                  </React.Fragment>
                );
              })}
              <span className="ml-1 text-fg-faint dark:text-fg-faint-dark">
                · {filteredResources.length + filteredMedia.length} files
              </span>
            </nav>

            <div className="flex flex-wrap items-center gap-2">
              <ButtonApp
                label="Search"
                variant="muted"
                size="control"
                icon={<Search className="w-4 h-4" />}
                onClick={() => navigate(`/apps/${appId}/repositories/${repositoryId}/playground`)}
              />
              {canEdit && (
                <>
                  <ButtonApp
                    label="Upload Media"
                    variant="secondary"
                    size="control"
                    icon={<Video className="w-4 h-4" />}
                    onClick={() => {
                      setShowMediaUploadModal(true);
                    }}
                    disabled={uploading}
                  />
                  <ButtonApp
                    label="Upload Files"
                    variant="primary"
                    size="control"
                    icon={<FolderOpen className="w-4 h-4" />}
                    onClick={() => fileInputRef.current?.click()}
                    loading={uploading}
                  />
                </>
              )}
            </div>
          </div>

          {/* SHARED EMPTY STATE */}
          {isEmpty ? (
            <div className="p-10 text-center">
              <div className="flex justify-center gap-6 mb-4">
                <FileText className="w-10 h-10 text-fg-faint2 dark:text-fg-faint2-dark" />
                <Video className="w-10 h-10 text-fg-faint2 dark:text-fg-faint2-dark" />
              </div>
              <h3 className="font-display text-lg font-normal tracking-[-0.02em] text-fg dark:text-fg-dark mb-1">
                {selectedFolderId === null
                  ? 'No files or media in repository root'
                  : 'No files or media in this folder'}
              </h3>

              <p className="text-sm text-fg-tertiary dark:text-fg-tertiary-dark">
                {selectedFolderId === null
                  ? 'Upload documents or media to get started'
                  : 'Upload files or media to this folder'}
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-line dark:divide-line-dark">
                <thead className="bg-tableCab dark:bg-tableCab-dark">
                  <tr>
                    <th className="px-5 py-3 text-left text-[11px] font-medium uppercase tracking-[0.05em] text-fg-tertiary dark:text-fg-tertiary-dark">Name</th>
                    <th className="px-5 py-3 text-left text-[11px] font-medium uppercase tracking-[0.05em] text-fg-tertiary dark:text-fg-tertiary-dark">Type</th>
                    <th className="px-5 py-3 text-left text-[11px] font-medium uppercase tracking-[0.05em] text-fg-tertiary dark:text-fg-tertiary-dark">Uploaded</th>
                    <th className="px-5 py-3 text-right text-[11px] font-medium uppercase tracking-[0.05em] text-fg-tertiary dark:text-fg-tertiary-dark">
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line text-sm text-fg dark:divide-line-dark dark:text-fg-dark">
                  {/* SUBFOLDERS (double-click to open) */}
                  {subfolders.map((folder) => {
                    const folderPath = selectedFolderPath ? `${selectedFolderPath}/${folder.name}` : folder.name;
                    const itemCount = countFolderItems(folder.folder_id);
                    return (
                      <tr
                        key={`folder-${folder.folder_id}`}
                        onDoubleClick={() => handleFolderSelect(folder.folder_id, folderPath)}
                        className="cursor-pointer select-none hover:bg-surface-tint dark:hover:bg-surface-tint-dark"
                      >
                        <td className="px-5 py-3">
                          <button
                            type="button"
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') handleFolderSelect(folder.folder_id, folderPath);
                            }}
                            title="Double-click to open"
                            className="flex items-center gap-3 text-left"
                          >
                            <BackgroundImage icon={Folder} size={32} iconSize={16} variant="marron" />
                            <span className="font-medium">{folder.name}</span>
                            {itemCount > 0 && (
                              <span className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark">({itemCount})</span>
                            )}
                          </button>
                        </td>
                        <td className="px-5 py-3 whitespace-nowrap text-fg-tertiary dark:text-fg-tertiary-dark">Folder</td>
                        <td className="px-5 py-3 whitespace-nowrap text-fg-tertiary dark:text-fg-tertiary-dark">—</td>
                        <td className="px-5 py-3" />
                      </tr>
                    );
                  })}

                  {/* FILES LIST */}
                  {filteredResources.map((resource) => (
                    <tr key={resource.resource_id} className="hover:bg-surface-tint dark:hover:bg-surface-tint-dark">
                      <td className="px-5 py-3">
                        <div className="flex items-center gap-3">
                          <BackgroundImage icon={FileText} size={32} iconSize={16} variant="marron" />
                          <span className="font-medium">{resource.name}</span>
                        </div>
                      </td>
                      <td className="px-5 py-3 whitespace-nowrap text-fg-tertiary dark:text-fg-tertiary-dark">
                        {(resource.file_type || 'unknown').toUpperCase()}
                      </td>
                      <td className="px-5 py-3 whitespace-nowrap text-fg-tertiary dark:text-fg-tertiary-dark">
                        {formatDate(resource.created_at)}
                      </td>
                      <td className="px-5 py-3">
                        <div className="flex items-center justify-end gap-1">
                          {canEdit && (
                            <button
                              onClick={() => handleMoveResource(resource)}
                              className="p-2 rounded text-fg-tertiary hover:text-fg hover:bg-surface-hover dark:text-fg-tertiary-dark dark:hover:text-fg-dark dark:hover:bg-surface-hover-dark"
                            >
                              <ArrowLeftRight className="w-4 h-4" />
                            </button>
                          )}
                          <button
                            onClick={() => handleDownloadResource(resource)}
                            className="p-2 rounded text-fg-tertiary hover:text-fg hover:bg-surface-hover dark:text-fg-tertiary-dark dark:hover:text-fg-dark dark:hover:bg-surface-hover-dark"
                          >
                            <ArrowDownToLine className="w-4 h-4" />
                          </button>
                          {canEdit && (
                            <button
                              onClick={() => handleReindexResource(resource)}
                              disabled={reindexingId !== null}
                              title="Re-extract and reindex this file"
                              aria-label={`Reindex ${resource.name}`}
                              className="p-2 rounded text-fg-tertiary hover:text-fg hover:bg-surface-hover disabled:opacity-50 disabled:cursor-not-allowed dark:text-fg-tertiary-dark dark:hover:text-fg-dark dark:hover:bg-surface-hover-dark"
                            >
                              {reindexingId === resource.resource_id
                                ? <Spinner size="sm" tone="current" />
                                : <RefreshCw className="w-4 h-4" />}
                            </button>
                          )}
                          {canEdit && (
                            <button
                              onClick={() => handleDeleteResource(resource)}
                              className="p-2 rounded text-fg-tertiary hover:text-error hover:bg-error-bg dark:text-fg-tertiary-dark dark:hover:text-error-dark dark:hover:bg-error-bg-dark"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}

                  {/* MEDIA LIST */}
                  {filteredMedia.map((media) => (
                    <tr key={media.media_id} className="hover:bg-surface-tint dark:hover:bg-surface-tint-dark">
                      <td className="px-5 py-3">
                        <div className="flex items-center gap-3">
                          <span className="bg-surface-ash p-2 rounded-lg dark:bg-surface-hover-dark"><Video className="w-4 h-4" /></span>
                          <div className="min-w-0">
                            <h4 className="font-medium">{media.name}</h4>
                            <p className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark">
                              {media.language || 'detecting...'} •{' '}
                              {media.duration
                                ? `${media.duration.toFixed(1)}s`
                                : 'processing...'}
                              {media.processing_mode === 'multimodal' && (
                                <span className="ml-2 inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-bronze-bg text-bronze dark:bg-bronze-bg-dark dark:text-bronze-dark" title="Indexed with multimodal video analysis">
                                  Multimodal
                                </span>
                              )}
                            </p>
                            {media.error_message && (
                              <p className="text-xs text-error dark:text-error-dark mt-1">
                                {media.error_message}
                              </p>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-5 py-3 whitespace-nowrap text-fg-tertiary dark:text-fg-tertiary-dark">
                        {media.source_type.toUpperCase()}
                      </td>
                      <td className="px-5 py-3 whitespace-nowrap text-fg-tertiary dark:text-fg-tertiary-dark">
                        {formatDate(media.create_date)}
                      </td>
                      <td className="px-5 py-3">
                        <div className="flex items-center justify-end gap-1">
                          <StatusBadge
                            status={getMediaStatusBadgeType(media.status)}
                            customLabel={media.status.replace('_', ' ')}
                          />

                          {canEdit && (
                            <>
                              <button
                                onClick={() => handleMoveMedia(media)}
                                className="p-2 rounded text-fg-tertiary hover:text-fg hover:bg-surface-hover dark:text-fg-tertiary-dark dark:hover:text-fg-dark dark:hover:bg-surface-hover-dark"
                              >
                                <ArrowLeftRight className="w-4 h-4" />
                              </button>
                              <button
                                onClick={() => handleDeleteMedia(media)}
                                className="p-2 rounded text-fg-tertiary hover:text-error hover:bg-error-bg dark:text-fg-tertiary-dark dark:hover:text-error-dark dark:hover:bg-error-bg-dark"
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
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
          <FormField
            label="Folder Name"
            id="create-folder-name"
            type="text"
            value={newFolderName}
            onChange={(e) => setNewFolderName(e.target.value)}
            placeholder="Enter folder name"
          />
          <div className="flex justify-end space-x-3">
            <ButtonApp
              label="Cancel"
              variant="secondary"
              size="medium"
              onClick={() => setShowCreateFolderModal(false)}
            />
            <ButtonApp
              label="Create"
              variant="primary"
              size="medium"
              onClick={createFolder}
              disabled={!newFolderName.trim()}
            />
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
          <FormField
            label="Folder Name"
            id="rename-folder-name"
            type="text"
            value={newFolderName}
            onChange={(e) => setNewFolderName(e.target.value)}
            placeholder="Enter folder name"
          />
          <div className="flex justify-end space-x-3">
            <ButtonApp
              label="Cancel"
              variant="secondary"
              size="medium"
              onClick={() => setShowRenameFolderModal(false)}
            />
            <ButtonApp
              label="Rename"
              variant="primary"
              size="medium"
              onClick={renameFolder}
              disabled={!newFolderName.trim()}
            />
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
              onChange={(e) => setNewParentFolderId(e.target.value ? Number.parseInt(e.target.value) : null)}
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
                e.target.value ? Number.parseInt(e.target.value) : null
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
              onChange={(e) => setMoveToFolderId(e.target.value ? Number.parseInt(e.target.value) : null)}
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
        }}
        title="Upload Media"
      >
        <div className="space-y-5">
          {/* Upload Type */}
          <div className="grid grid-cols-2 gap-3">
            <button
              onClick={() => setUploadType('file')}
              aria-pressed={uploadType === 'file'}
              className={`flex items-center gap-3 p-3 rounded-lg border text-left text-sm transition-colors ${
                uploadType === 'file'
                  ? 'border-ink bg-surface text-fg dark:border-ink-dark dark:bg-surface-dark dark:text-fg-dark'
                  : 'border-line bg-surface text-fg-secondary hover:bg-surface-hover dark:border-line-dark dark:bg-surface-dark dark:text-fg-secondary-dark dark:hover:bg-surface-hover-dark'
              }`}
            >
              <BackgroundImage icon={FolderOpen} variant={uploadType === 'file' ? 'marron' : 'gris'} />
              <span className="font-display tracking-[-0.02em]">File Upload</span>
            </button>
            <button
              onClick={() => setUploadType('youtube')}
              aria-pressed={uploadType === 'youtube'}
              className={`flex items-center gap-3 p-3 rounded-lg border text-left text-sm transition-colors ${
                uploadType === 'youtube'
                  ? 'border-ink bg-surface text-fg dark:border-ink-dark dark:bg-surface-dark dark:text-fg-dark'
                  : 'border-line bg-surface text-fg-secondary hover:bg-surface-hover dark:border-line-dark dark:bg-surface-dark dark:text-fg-secondary-dark dark:hover:bg-surface-hover-dark'
              }`}
            >
              <BackgroundImage icon={Tv} variant={uploadType === 'youtube' ? 'marron' : 'gris'} />
              <span className="font-display tracking-[-0.02em]">YouTube URL</span>
            </button>
          </div>

          {/* File Upload */}
          {uploadType === 'file' && (
            <div>
              <label htmlFor="media-files-input" className="block text-sm font-medium text-fg dark:text-fg-dark mb-1">
                Select Video/Audio Files
              </label>
              <input
                id="media-files-input"
                type="file"
                multiple
                accept="video/*,audio/*"
                onChange={(e) => setMediaFiles(Array.from(e.target.files || []))}
                className="w-full p-3 text-sm text-fg-secondary border border-dashed border-line-strong rounded-lg bg-surface-tint cursor-pointer dark:text-fg-secondary-dark dark:border-line-strong-dark dark:bg-surface-tint-dark file:mr-3 file:px-3 file:py-1.5 file:rounded-md file:border file:border-ink file:bg-surface file:text-fg file:font-display file:text-sm file:cursor-pointer hover:file:bg-surface-hover dark:file:border-ink-dark dark:file:bg-surface-dark dark:file:text-fg-dark"
              />
              {mediaFiles.length > 0 && (
                <p className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark mt-1">{mediaFiles.length} file(s) selected</p>
              )}
            </div>
          )}

          {/* YouTube URL */}
          {uploadType === 'youtube' && (
            <FormField
              label="YouTube URL"
              id="youtube-url-input"
              value={youtubeUrl}
              onChange={(e) => setYoutubeUrl(e.target.value)}
              placeholder="https://youtube.com/watch?v=..."
            />
          )}

          {/* Configuration */}
          <div className="border-t border-line pt-5 dark:border-line-dark">
            <h3 className="font-display text-base font-normal tracking-[-0.02em] text-fg dark:text-fg-dark mb-3">Processing Options</h3>

            {/* Repository AI Services (read-only info) */}
            <div className="mb-4 space-y-2">
              {repository?.transcription_service_id ? (
                <Alert
                  type="success"
                  title="Transcription"
                  message={<strong>{repository.ai_services?.find(s => s.service_id === repository.transcription_service_id)?.name ?? `Service #${repository.transcription_service_id}`}</strong>}
                />
              ) : (
                <Alert
                  type="error"
                  title="Transcription service missing"
                  message="No transcription service configured. Please set one in the repository settings before uploading media."
                />
              )}
              {repository?.video_ai_service_id && (
                <Alert
                  type="info"
                  title="Video Analysis"
                  message={<><strong>{repository.ai_services?.find(s => s.service_id === repository.video_ai_service_id)?.name ?? `Service #${repository.video_ai_service_id}`}</strong> (multimodal enabled)</>}
                />
              )}
            </div>

            <div className="space-y-3">
              <FormSelect
                label="Language (optional)"
                id="media-language-select"
                value={mediaConfig.forced_language}
                onChange={(e) => setMediaConfig({...mediaConfig, forced_language: e.target.value})}
                options={[
                  { value: '', label: 'Auto-detect' },
                  { value: 'es', label: 'Spanish' },
                  { value: 'en', label: 'English' },
                  { value: 'eu', label: 'Basque' },
                  { value: 'fr', label: 'French' },
                ]}
              />

              <div className="grid grid-cols-3 gap-3">
                <FormField
                  label="Min Chunk (s)"
                  id="chunk-min-duration"
                  type="number"
                  value={mediaConfig.chunk_min_duration}
                  onChange={(e) => setMediaConfig({...mediaConfig, chunk_min_duration: Number.parseInt(e.target.value)})}
                  min={10}
                  max={60}
                  labelClassName="block text-xs font-medium text-fg-secondary dark:text-fg-secondary-dark mb-1"
                />
                <FormField
                  label="Max Chunk (s)"
                  id="chunk-max-duration"
                  type="number"
                  value={mediaConfig.chunk_max_duration}
                  onChange={(e) => setMediaConfig({...mediaConfig, chunk_max_duration: Number.parseInt(e.target.value)})}
                  min={60}
                  max={300}
                  labelClassName="block text-xs font-medium text-fg-secondary dark:text-fg-secondary-dark mb-1"
                />
                <FormField
                  label="Overlap (s)"
                  id="chunk-overlap"
                  type="number"
                  value={mediaConfig.chunk_overlap}
                  onChange={(e) => setMediaConfig({...mediaConfig, chunk_overlap: Number.parseInt(e.target.value)})}
                  min={0}
                  max={20}
                  labelClassName="block text-xs font-medium text-fg-secondary dark:text-fg-secondary-dark mb-1"
                />
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-5 border-t border-line dark:border-line-dark">
            <ButtonApp
              label="Cancel"
              variant="secondary"
              onClick={() => setShowMediaUploadModal(false)}
            />
            <ButtonApp
              label={uploading ? 'Uploading...' : 'Upload'}
              variant="primary"
              onClick={handleMediaUpload}
              disabled={
                !repository?.transcription_service_id ||
                (uploadType === 'file' ? mediaFiles.length === 0 : !youtubeUrl)
              }
            />
          </div>
        </div>
      </Modal>

    </div>
  );
};

export default RepositoryDetailPage;
