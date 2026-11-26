import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import ConfirmationModal, { type ConfirmVariant } from '../components/ui/ConfirmationModal';

export interface ConfirmOptions {
  readonly title: string;
  readonly message: ReactNode;
  readonly confirmLabel?: string;
  readonly cancelLabel?: string;
  readonly variant?: ConfirmVariant;
  /** Called when the dialog is closed without choosing (Escape, backdrop, X); the promise still resolves false. */
  readonly onDismiss?: () => void;
}

interface ConfirmContextValue {
  readonly confirm: (options: ConfirmOptions) => Promise<boolean>;
}

const ConfirmContext = createContext<ConfirmContextValue | null>(null);

interface PendingConfirm extends ConfirmOptions {
  readonly resolve: (value: boolean) => void;
}

interface ConfirmProviderProps {
  readonly children: ReactNode;
}

export function ConfirmProvider({ children }: ConfirmProviderProps) {
  const [pending, setPending] = useState<PendingConfirm | null>(null);
  const pendingRef = useRef<PendingConfirm | null>(null);
  pendingRef.current = pending;

  const confirm = useCallback(
    (options: ConfirmOptions): Promise<boolean> =>
      new Promise<boolean>((resolve) => {
        const previous = pendingRef.current;
        if (previous) {
          previous.onDismiss?.();
          previous.resolve(false);
        }
        setPending({ ...options, resolve });
      }),
    [],
  );

  const handleConfirm = useCallback(() => {
    setPending((current) => {
      current?.resolve(true);
      return null;
    });
  }, []);

  const handleCancel = useCallback(() => {
    setPending((current) => {
      current?.resolve(false);
      return null;
    });
  }, []);

  const handleDismiss = useCallback(() => {
    const current = pendingRef.current;
    current?.onDismiss?.();
    current?.resolve(false);
    setPending(null);
  }, []);

  const value = useMemo<ConfirmContextValue>(() => ({ confirm }), [confirm]);

  return (
    <ConfirmContext.Provider value={value}>
      {children}
      {pending && (
        <ConfirmationModal
          isOpen
          title={pending.title}
          message={pending.message}
          confirmLabel={pending.confirmLabel}
          cancelLabel={pending.cancelLabel}
          variant={pending.variant}
          onConfirm={handleConfirm}
          onCancel={handleCancel}
          onDismiss={handleDismiss}
        />
      )}
    </ConfirmContext.Provider>
  );
}

export function useConfirm() {
  const ctx = useContext(ConfirmContext);
  if (!ctx) {
    throw new Error('useConfirm must be used within a ConfirmProvider');
  }
  return ctx.confirm;
}
