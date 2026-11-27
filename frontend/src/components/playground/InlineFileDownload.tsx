import React, { useState } from 'react';
import { ButtonApp } from '../ui/ButtonApp';

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
    <ButtonApp
      label={filename}
      onClick={handleClick}
      loading={loading}
      variant="secondary"
      size="small"
      icon={
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
        </svg>
      }
    />
  );
};

export default InlineFileDownload;
