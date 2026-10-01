import { type ReactNode, useEffect, useRef, useId } from 'react';
import { X } from 'lucide-react';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  size?: 'small' | 'medium' | 'large' | 'xlarge';
}

const FOCUSABLE_SELECTORS = [
  'a[href]',
  'button:not([disabled])',
  'textarea:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ');

function Modal({ isOpen, onClose, title, children, size = 'large' }: Readonly<ModalProps>) {
  const titleId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const returnFocusRef = useRef<Element | null>(null);
  // Stable ref so the effect depends on `isOpen` only — avoids re-running (and re-stealing focus)
  // when the parent passes a new onClose reference on each render (e.g. while user types).
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  const sizeClasses = {
    small: 'max-w-md max-h-96',
    medium: 'max-w-2xl max-h-[70vh]',
    large: 'max-w-4xl max-h-[80vh]',
    xlarge: 'max-w-6xl max-h-[90vh]',
  };

  useEffect(() => {
    if (!isOpen) return;

    returnFocusRef.current = document.activeElement;

    const panel = panelRef.current;
    if (panel) {
      const first = panel.querySelector<HTMLElement>(FOCUSABLE_SELECTORS);
      (first ?? panel).focus();
    }

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onCloseRef.current();
        return;
      }

      if (e.key !== 'Tab') return;

      const currentPanel = panelRef.current;
      if (!currentPanel) return;

      const focusables = Array.from(
        currentPanel.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTORS),
      ).filter((el) => !el.closest('[hidden]'));

      if (focusables.length === 0) {
        e.preventDefault();
        return;
      }

      const first = focusables[0];
      const last = focusables[focusables.length - 1];

      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      if (returnFocusRef.current instanceof HTMLElement) {
        returnFocusRef.current.focus();
      }
    };
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div
        className="fixed inset-0 bg-ink/40 dark:bg-black/60 transition-opacity"
        aria-hidden="true"
        onClick={onClose}
      />

      <div className="flex min-h-full items-center justify-center p-4">
        <div
          ref={panelRef}
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          tabIndex={-1}
          className={`relative bg-surface dark:bg-surface-dark border border-line dark:border-line-dark rounded-lg shadow-[0_14px_40px_rgba(32,28,20,0.14)] dark:shadow-[0_14px_40px_rgba(0,0,0,0.55)] w-full overflow-hidden focus:outline-none ${sizeClasses[size]}`}
        >
          <div className="flex items-center justify-between px-6 py-5 border-b border-line dark:border-line-dark bg-surface dark:bg-surface-dark sticky top-0 z-10">
            <h3 id={titleId} className="font-display text-lg font-normal tracking-[-0.02em] text-fg dark:text-fg-dark">
              {title}
            </h3>
            <button
              onClick={onClose}
              aria-label="Close"
              className="p-1 text-fg-tertiary hover:text-fg hover:bg-surface-hover dark:text-fg-tertiary-dark dark:hover:text-fg-dark dark:hover:bg-surface-hover-dark transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-focus dark:focus-visible:ring-focus-dark rounded-lg"
            >
              <X className="w-5 h-5" aria-hidden="true" />
            </button>
          </div>

          <div className="p-6 overflow-y-auto" style={{ maxHeight: 'calc(80vh - 88px)' }}>
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}

export default Modal;
