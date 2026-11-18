// URL policy for markdown rendered from chat messages (model output included).
import { configService } from '../core/ConfigService';

/**
 * react-markdown `urlTransform`: the library's safe default (http, https, mailto,
 * relative…) plus `file://` (internal file references resolved by the app) and
 * `data:image/*` for images. Anything else (e.g. `javascript:`) becomes empty.
 */
export function markdownUrlTransform(
  url: string,
  key: string,
  defaultTransform: (value: string) => string,
): string {
  if (url.startsWith('file://')) return url;
  if (key === 'src' && /^data:image\//i.test(url)) return url;
  return defaultTransform(url);
}

function backendOrigin(): string | null {
  try {
    const base = configService.getApiBaseUrl();
    return base ? new URL(base, globalThis.location.href).origin : null;
  } catch {
    return null;
  }
}

/** Whether an image may load automatically: same origin, the backend, or inline data. */
export function isAutoLoadableImageUrl(src: string): boolean {
  if (/^data:image\//i.test(src)) return true;
  try {
    const { origin } = new URL(src, globalThis.location.href);
    return origin === globalThis.location.origin || origin === backendOrigin();
  } catch {
    return false;
  }
}

/** Host of a URL for display, or an empty string when it cannot be parsed. */
export function urlHost(url: string): string {
  try {
    return new URL(url, globalThis.location.href).host;
  } catch {
    return '';
  }
}
