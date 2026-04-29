import { useCallback } from 'react';
import { toast } from 'sonner';
import { errorMessage } from '../constants/messages';

export interface MutationToastOptions<T = unknown> {
  readonly loading?: string;
  readonly success: string | ((data: T) => string);
  readonly error?: string | ((err: unknown) => string);
}

export type ApiMutation = <T>(
  fn: () => Promise<T>,
  toastOptions: MutationToastOptions<T>,
) => Promise<T | undefined>;

export function useApiMutation(): ApiMutation {
  return useCallback(
    async <T,>(
      fn: () => Promise<T>,
      toastOptions: MutationToastOptions<T>,
    ): Promise<T | undefined> => {
      const promise = fn();

      toast.promise(promise, {
        loading: toastOptions.loading ?? 'Working…',
        success: (data: T) =>
          typeof toastOptions.success === 'function'
            ? toastOptions.success(data)
            : toastOptions.success,
        error: (err: unknown) => {
          if (typeof toastOptions.error === 'function') return toastOptions.error(err);
          if (typeof toastOptions.error === 'string') return toastOptions.error;
          return errorMessage(err, 'Operation failed');
        },
      });

      try {
        return await promise;
      } catch {
        return undefined;
      }
    },
    [],
  );
}
