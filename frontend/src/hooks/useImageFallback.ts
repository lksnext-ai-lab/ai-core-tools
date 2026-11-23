import { useEffect, useState } from 'react';

/** Whether to render `src` as an image: false when absent or after it failed to load (until `src` changes). */
export function useImageFallback(src: string | null | undefined): { showImage: boolean; onError: () => void } {
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  useEffect(() => setFailedSrc(null), [src]);
  return {
    showImage: Boolean(src) && failedSrc !== src,
    onError: () => setFailedSrc(src ?? null),
  };
}
