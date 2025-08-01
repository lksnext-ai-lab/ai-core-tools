import React, { useState, useEffect } from 'react';
import { apiService } from '../../services/api';

interface VersionFooterProps {
  className?: string;
}

interface VersionInfo {
  name: string;
  version: string;
}

const VersionFooter: React.FC<VersionFooterProps> = ({ className = '' }) => {
  const [versionInfo, setVersionInfo] = useState<VersionInfo>({ name: 'ia-core-tools', version: '0.1.0' });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchVersion() {
      try {
        const version = await apiService.getVersion();
        setVersionInfo(version);
      } catch (error) {
        console.error('Failed to fetch version:', error);
        // Keep default values if fetch fails
      } finally {
        setLoading(false);
      }
    }

    fetchVersion();
  }, []);

  if (loading) {
    return (
      <div className={`version-info text-end text-gray-500 text-xs py-2 px-4 ${className}`}>
        Loading version...
      </div>
    );
  }

  return (
    <div className={`version-info text-end text-gray-500 text-xs py-2 px-4 ${className}`}>
      {versionInfo.name} v{versionInfo.version}
    </div>
  );
};

export default VersionFooter; 