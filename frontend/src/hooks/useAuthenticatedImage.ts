import { useEffect, useRef, useState } from 'react';

/**
 * Object URL of a picture served behind authentication (user avatar, App image), which an `<img src>` cannot
 * fetch on its own. Loaded again only when `key` or `version` changes; no `version` means no picture.
 * The previous URL is revoked once its replacement is set, so no broken image shows in between; a failed
 * load yields null (callers fall back to initials).
 */
export function useAuthenticatedImage(
  key: string | number | null,
  version: string | null | undefined,
  load: (version: string) => Promise<Blob | null>,
): string | null {
  const [url, setUrl] = useState<string | null>(null);
  const urlRef = useRef<string | null>(null);
  // The loader is usually an inline closure: keep the latest one without reloading on every render.
  // Declared before the loading effect, so it runs first.
  const loadRef = useRef(load);
  useEffect(() => {
    loadRef.current = load;
  });

  useEffect(() => {
    const replace = (next: string | null) => {
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
      urlRef.current = next;
      setUrl(next);
    };
    if (key === null || !version) {
      replace(null);
      return;
    }
    let cancelled = false;
    loadRef.current(version)
      .then((blob) => {
        if (!cancelled) replace(blob ? URL.createObjectURL(blob) : null);
      })
      .catch((err: unknown) => {
        console.error('Failed to load the picture', err);
        if (!cancelled) replace(null);
      });
    return () => {
      cancelled = true;
    };
  }, [key, version]);

  useEffect(() => () => {
    if (urlRef.current) URL.revokeObjectURL(urlRef.current);
  }, []);

  return url;
}
