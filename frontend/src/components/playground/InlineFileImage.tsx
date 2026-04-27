import React, { useEffect, useState } from 'react';

interface InlineFileImageProps {
  fileId: string;
  filename: string;
  resolveUrl: (fileId: string) => Promise<string>;
}

const InlineFileImage: React.FC<InlineFileImageProps> = ({ fileId, filename, resolveUrl }) => {
  const [src, setSrc] = useState<string | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    resolveUrl(fileId)
      .then((url) => { if (!cancelled) setSrc(url); })
      .catch(() => { if (!cancelled) setError(true); });
    return () => { cancelled = true; };
  }, [fileId]);

  if (error) {
    return <span className="text-red-500 text-sm italic">[Image unavailable: {filename}]</span>;
  }

  if (!src) {
    return (
      <span className="inline-flex items-center gap-1 text-sm text-gray-500 italic">
        <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
        </svg>
        Loading {filename}…
      </span>
    );
  }

  return (
    <span className="inline-block my-2">
      <img
        src={src}
        alt={filename}
        className="max-w-full rounded-lg border border-gray-200 shadow-sm"
        style={{ maxHeight: '400px' }}
      />
      <span className="block mt-1">
        <a
          href={src}
          download={filename}
          className="inline-flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800"
        >
          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          {filename}
        </a>
      </span>
    </span>
  );
};

export default InlineFileImage;
