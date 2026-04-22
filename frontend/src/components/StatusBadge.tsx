import React from 'react';

interface StatusBadgeProps {
  status: string;
  processingMode?: string | null;
}

const StatusBadge: React.FC<StatusBadgeProps> = ({ status, processingMode }) => {
  const colors: Record<string, string> = {
    pending: 'bg-yellow-100 text-yellow-800',
    downloading: 'bg-blue-100 text-blue-800',
    processing: 'bg-blue-100 text-blue-800',
    transcribing: 'bg-purple-100 text-purple-800',
    analyzing_video: 'bg-violet-100 text-violet-800',
    indexing: 'bg-indigo-100 text-indigo-800',
    ready: 'bg-green-100 text-green-800',
    error: 'bg-red-100 text-red-800'
  };

  const labels: Record<string, string> = {
    analyzing_video: 'analyzing video',
  };

  const label = labels[status] || status;

  // Show multimodal indicator when ready
  if (status === 'ready' && processingMode === 'multimodal') {
    return (
      <span className="px-3 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">
        ready
      </span>
    );
  }
  
  return (
    <span className={`px-3 py-1 rounded-full text-xs font-medium ${colors[status] || 'bg-gray-100 text-gray-800'}`}>
      {label}
    </span>
  );
};

export default StatusBadge;