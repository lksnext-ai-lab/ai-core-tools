import { FileText, Image, FileType, ArrowDown, FolderOpen, Paperclip, Check, X, Loader2 } from 'lucide-react';

export interface PanelFile {
  id: string;
  filename: string;
  file_type?: string;
  processing_status?: string;
  file_size_display?: string;
  has_extractable_content?: boolean;
  content_preview?: string;
}

interface AttachedFilesPanelProps {
  files: PanelFile[];
  isLoading?: boolean;
  onRemoveFile: (id: string) => void;
  onDownloadFile?: (id: string) => void;
  title?: string;
}

function getStatusClassName(status?: string): string {
  if (status === 'ready') return 'bg-green-100 text-green-700';
  if (status === 'error') return 'bg-red-100 text-red-700';
  return 'bg-yellow-100 text-yellow-700';
}

function getExtractableLabel(fileType?: string, hasExtractableContent?: boolean): string {
  if (fileType === 'image') return 'Vision ready';
  if (hasExtractableContent) return 'Text extracted';
  return 'No text';
}

function getFileIcon(fileType?: string) {
  switch (fileType) {
    case 'pdf': return <FileText className="w-4 h-4 text-gray-500" />;
    case 'image': return <Image className="w-4 h-4 text-gray-500" />;
    case 'text': return <FileType className="w-4 h-4 text-gray-500" />;
    case 'document': return <FileText className="w-4 h-4 text-gray-500" />;
    case 'output': return <ArrowDown className="w-4 h-4 text-gray-500" />;
    default: return <FolderOpen className="w-4 h-4 text-gray-500" />;
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
    <div className="w-64 shrink-0 bg-white shadow rounded-lg flex flex-col">
      {/* Header */}
      <div className="p-3 border-b">
        <h3 className="text-sm font-medium text-gray-700 flex items-center gap-2">
          <Paperclip className="w-4 h-4" />
          <span>{title}</span>
          {files.length > 0 && (
            <span className="ml-auto text-xs text-gray-400">
              {files.length} file{files.length === 1 ? '' : 's'}
            </span>
          )}
        </h3>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-2 space-y-2">
        {isLoading && (
          <div className="flex items-center justify-center py-4 gap-2 text-sm text-gray-500">
            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600" />
            Uploading...
          </div>
        )}

        {!isLoading && files.length === 0 && (
          <div className="py-6 text-center text-gray-400">
            <div className="flex justify-center mb-2">
              <Paperclip className="w-6 h-6" />
            </div>
            <p className="text-xs">No files attached yet</p>
            <p className="text-xs mt-1 text-gray-300">Use the attach button to upload</p>
          </div>
        )}

        {files.map((file) => (
          <div
            key={file.id}
            className="flex items-start gap-2 bg-gray-50 rounded border border-gray-200 px-2 py-2 hover:border-gray-300 transition-colors"
          >
            {/* Icon */}
            <span className="shrink-0 mt-0.5">{getFileIcon(file.file_type)}</span>

            {/* Info */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1 flex-wrap">
                <span
                  className="text-xs font-medium text-gray-800 truncate max-w-[120px]"
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
                    {file.processing_status === 'ready' && <><Check className="w-3 h-3 text-green-500" /> Ready</>}
                    {file.processing_status === 'error' && <><X className="w-3 h-3 text-red-500" /> Error</>}
                    {file.processing_status === 'uploaded' && <><Loader2 className="w-3 h-3 animate-spin" /> Uploaded</>}
                    {file.processing_status === 'processing' && <><Loader2 className="w-3 h-3 animate-spin" /> Processing</>}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1 text-xs text-gray-400 mt-0.5">
                {file.file_size_display && <span>{file.file_size_display}</span>}
                {file.has_extractable_content !== undefined && (
                  <>
                    {file.file_size_display && <span>·</span>}
                    <span className={file.has_extractable_content || file.file_type === 'image' ? 'text-green-600' : 'text-gray-400'}>
                      {getExtractableLabel(file.file_type, file.has_extractable_content)}
                    </span>
                  </>
                )}
              </div>
              {file.content_preview && (
                <p
                  className="text-xs text-gray-400 truncate mt-0.5"
                  title={file.content_preview}
                >
                  {file.content_preview}
                </p>
              )}
            </div>

            {/* Action buttons */}
            <div className="shrink-0 flex flex-col gap-0.5">
              {onDownloadFile && (
                <button
                  type="button"
                  onClick={() => onDownloadFile(file.id)}
                  className="text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded p-0.5 transition-colors"
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
                className="text-gray-400 hover:text-red-600 hover:bg-red-50 rounded p-0.5 transition-colors"
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
