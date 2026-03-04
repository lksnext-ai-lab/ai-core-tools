import React, { useState } from 'react';

interface InlineFileDownloadProps {
  fileId: string;
  filename: string;
  resolveUrl: (fileId: string) => Promise<string>;
}

const InlineFileDownload: React.FC<InlineFileDownloadProps> = ({ fileId, filename, resolveUrl }) => {
  const [loading, setLoading] = useState(false);

  const handleClick = async () => {
    setLoading(true);
    try {
      const url = await resolveUrl(fileId);
      window.open(url, '_blank');
    } finally {
      setLoading(false);
    }
  };

  return (
    <button
      onClick={handleClick}
      disabled={loading}
      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md border border-blue-300
                 text-blue-700 bg-blue-50 hover:bg-blue-100 disabled:opacity-50 transition-colors"
    >
      <svg className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
        {loading ? (
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 12a8 8 0 018-8v8z" />
        ) : (
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
        )}
      </svg>
      {filename}
    </button>
  );
};

export default InlineFileDownload;
