import { FileText, Image, FileType, ArrowDown, FolderOpen, Paperclip, Check, X, Film } from 'lucide-react';
import { Spinner } from '../ui/Spinner';

export interface PanelFile {
  id: string;
  filename: string;
  file_type?: string;
  processing_status?: string;
  file_size_display?: string;
  has_extractable_content?: boolean;
  content_preview?: string;
  error_message?: string;
}

interface AttachedFilesPanelProps {
  files: PanelFile[];
  isLoading?: boolean;
  onRemoveFile: (id: string) => void;
  onDownloadFile?: (id: string) => void;
  title?: string;
}

// Same palette as the Badge component variants (success / error / warning / info).
function getStatusClassName(status?: string): string {
  if (status === 'ready' || status === 'uploaded') return 'bg-success-bg text-success dark:bg-success-bg-dark dark:text-success-dark';
  if (status === 'error') return 'bg-error-bg text-error dark:bg-error-bg-dark dark:text-error-dark';
  if (status === 'pending') return 'bg-bronze-bg text-bronze dark:bg-bronze-bg-dark dark:text-bronze-dark';
  return 'bg-info-bg text-info dark:bg-info-bg-dark dark:text-info-dark';
}

function getDisplayStatus(status?: string): string | undefined {
  return status === 'uploaded' ? 'ready' : status;
}

function getExtractableLabel(fileType?: string, hasExtractableContent?: boolean): string {
  if (fileType === 'image') return 'Vision ready';
  if (hasExtractableContent) return 'Text extracted';
  return 'No text';
}

function getFileIcon(fileType?: string) {
  switch (fileType) {
    case 'pdf': return <FileText className="w-4 h-4 text-bronze dark:text-bronze-dark" />;
    case 'image': return <Image className="w-4 h-4 text-bronze dark:text-bronze-dark" />;
    case 'text': return <FileType className="w-4 h-4 text-bronze dark:text-bronze-dark" />;
    case 'document': return <FileText className="w-4 h-4 text-bronze dark:text-bronze-dark" />;
    case 'output': return <ArrowDown className="w-4 h-4 text-bronze dark:text-bronze-dark" />;
    case 'media': return <Film className="w-4 h-4 text-bronze dark:text-bronze-dark" />;
    default: return <FolderOpen className="w-4 h-4 text-bronze dark:text-bronze-dark" />;
  }
}

export default function AttachedFilesPanel({
  files,
  isLoading = false,
  onRemoveFile,
  onDownloadFile,
  title = 'Attached Files',
}: Readonly<AttachedFilesPanelProps>) {
  return (
    <div className="w-64 shrink-0 bg-canvas-alt dark:bg-canvas-alt-dark border-[0.5px] border-line dark:border-line-dark flex flex-col h-full max-h-full min-h-0">
      {/* Header */}
      <div className="p-3 border-b border-line dark:border-line-dark shrink-0">
        <h3 className="text-sm font-medium text-fg dark:text-fg-dark flex items-center gap-2">
          <Paperclip className="w-4 h-4" />
          <span>{title}</span>
          {files.length > 0 && (
            <span className="ml-auto text-xs text-fg dark:text-fg-dark">
              {files.length} file{files.length === 1 ? '' : 's'}
            </span>
          )}
        </h3>
      </div>

      {/* Content */}
      <div className="flex-1 min-h-0 overflow-y-auto p-2 space-y-2 overscroll-contain">
        {isLoading && (
          <div className="flex items-center justify-center py-4 gap-2 text-sm text-fg-tertiary dark:text-fg-tertiary-dark">
            <Spinner size="sm" tone="muted" />
            Uploading...
          </div>
        )}

        {!isLoading && files.length === 0 && (
          <div className="py-6 text-center text-fg-secondary dark:text-fg-secondary-dark">
            <div className="flex justify-center mb-2">
              <Paperclip className="w-6 h-6" />
            </div>
            <p className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark">No files attached yet</p>
            <p className="text-xs mt-1 text-fg-tertiary dark:text-fg-tertiary-dark">Use the attach button to upload</p>
          </div>
        )}

        {files.map((file) => (
          <div
            key={file.id}
            className="flex items-start gap-2 bg-surface dark:bg-surface-dark rounded border border-line dark:border-line-dark px-2 py-2 hover:border-ink dark:hover:border-ink-dark transition-colors"
          >
            {/* Icon */}
            <span className="shrink-0 mt-0.5">{getFileIcon(file.file_type)}</span>

            {/* Info */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1 flex-wrap">
                <span
                  className="text-xs font-medium text-fg dark:text-fg-dark truncate max-w-[120px]"
                  title={file.filename}
                >
                  {file.filename}
                </span>
                {file.file_type === 'output' && (
                  <span className="text-xs px-1 py-0.5 rounded-full shrink-0 bg-blue-100 text-blue-700">
                    Generated
                  </span>
                )}
                {file.processing_status && file.file_type !== 'output' && (
                  <span
                    className={`inline-flex items-center gap-0.5 text-xs px-1 py-0.5 rounded-full shrink-0 ${
                      getStatusClassName(file.processing_status)
                    }`}
                  >
                    {getDisplayStatus(file.processing_status) === 'ready' && <><Check className="w-3 h-3 text-bronze dark:text-bronze-dark" /> Ready</>}
                    {getDisplayStatus(file.processing_status) === 'error' && <><X className="w-3 h-3 text-bronze dark:text-bronze-dark" /> Error</>}
                    {getDisplayStatus(file.processing_status) === 'pending' && <><Spinner size="xs" tone="current" className="text-bronze dark:text-bronze-dark" /> Pending</>}
                    {getDisplayStatus(file.processing_status) === 'processing' && <><Spinner size="xs" tone="current" className="text-bronze dark:text-bronze-dark" /> Processing</>}
                    {getDisplayStatus(file.processing_status) === 'transcribing' && <><Spinner size="xs" tone="current" className="text-bronze dark:text-bronze-dark" /> Transcribing</>}
                    {getDisplayStatus(file.processing_status) === 'analyzing_video' && <><Spinner size="xs" tone="current" className="text-bronze dark:text-bronze-dark" /> Analyzing video</>}
                    {getDisplayStatus(file.processing_status) === 'downloading' && <><Spinner size="xs" tone="current" className="text-bronze dark:text-bronze-dark" /> Downloading</>}
                    {getDisplayStatus(file.processing_status) === 'indexing' && <><Spinner size="xs" tone="current" className="text-bronze dark:text-bronze-dark" /> Indexing</>}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1 text-xs text-fg-tertiary dark:text-fg-tertiary-dark mt-0.5">
                {file.file_size_display && <span>{file.file_size_display}</span>}
                {file.has_extractable_content !== undefined && (
                  <>
                    {file.file_size_display && <span>·</span>}
                    <span className='text-fg-secondary dark:text-fg-secondary-dark'>
                      {getExtractableLabel(file.file_type, file.has_extractable_content)}
                    </span>
                  </>
                )}
              </div>
              {file.content_preview && (
                <p
                  className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark truncate mt-0.5"
                  title={file.content_preview}
                >
                  {file.content_preview}
                </p>
              )}
              {getDisplayStatus(file.processing_status) === 'error' && file.error_message && (
                <p
                  className="text-xs text-error dark:text-error-dark mt-0.5 line-clamp-2"
                  title={file.error_message}
                >
                  {file.error_message}
                </p>
              )}
            </div>

            {/* Action buttons */}
            <div className="shrink-0 flex flex-col gap-0.5">
              {onDownloadFile && (
                <button
                  type="button"
                  onClick={() => onDownloadFile(file.id)}
                  className="text-bronze dark:text-bronze-dark hover:text-fg dark:hover:text-fg-dark  rounded p-0.5 transition-colors"
                  title="Download file"
                  aria-label={`Download ${file.filename}`}
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                </button>
              )}
              <button
                type="button"
                onClick={() => onRemoveFile(file.id)}
                className="text-bronze dark:text-bronze-dark hover:text-error hover:bg-bg-error rounded p-0.5 transition-colors"
                title="Remove file"
                aria-label={`Remove ${file.filename}`}
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
