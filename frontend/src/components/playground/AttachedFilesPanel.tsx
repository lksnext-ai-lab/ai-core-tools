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
  title?: string;
}

function getFileIcon(fileType?: string): string {
  switch (fileType) {
    case 'pdf': return '📄';
    case 'image': return '🖼️';
    case 'text': return '📝';
    case 'document': return '📑';
    default: return '📁';
  }
}

export default function AttachedFilesPanel({
  files,
  isLoading = false,
  onRemoveFile,
  title = 'Attached Files',
}: Readonly<AttachedFilesPanelProps>) {
  return (
    <div className="w-64 shrink-0 bg-white shadow rounded-lg flex flex-col">
      {/* Header */}
      <div className="p-3 border-b">
        <h3 className="text-sm font-medium text-gray-700 flex items-center gap-2">
          <span>📎</span>
          <span>{title}</span>
          {files.length > 0 && (
            <span className="ml-auto text-xs text-gray-400">
              {files.length} file{files.length !== 1 ? 's' : ''}
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
            <div className="text-2xl mb-2">📎</div>
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
            <span className="text-base shrink-0 mt-0.5">{getFileIcon(file.file_type)}</span>

            {/* Info */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1 flex-wrap">
                <span
                  className="text-xs font-medium text-gray-800 truncate max-w-[120px]"
                  title={file.filename}
                >
                  {file.filename}
                </span>
                {file.processing_status && (
                  <span
                    className={`text-xs px-1 py-0.5 rounded-full shrink-0 ${
                      file.processing_status === 'ready'
                        ? 'bg-green-100 text-green-700'
                        : file.processing_status === 'error'
                          ? 'bg-red-100 text-red-700'
                          : 'bg-yellow-100 text-yellow-700'
                    }`}
                  >
                    {file.processing_status === 'ready' && '✓ Ready'}
                    {file.processing_status === 'error' && '✗ Error'}
                    {file.processing_status === 'uploaded' && '⏳ Uploaded'}
                    {file.processing_status === 'processing' && '⏳ Processing'}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1 text-xs text-gray-400 mt-0.5">
                {file.file_size_display && <span>{file.file_size_display}</span>}
                {file.has_extractable_content !== undefined && (
                  <>
                    {file.file_size_display && <span>·</span>}
                    <span className={file.has_extractable_content || file.file_type === 'image' ? 'text-green-600' : 'text-gray-400'}>
                      {file.file_type === 'image' ? 'Vision ready' : file.has_extractable_content ? 'Text extracted' : 'No text'}
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

            {/* Delete button */}
            <button
              type="button"
              onClick={() => onRemoveFile(file.id)}
              className="shrink-0 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded p-0.5 transition-colors"
              title="Remove file"
              aria-label={`Remove ${file.filename}`}
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
