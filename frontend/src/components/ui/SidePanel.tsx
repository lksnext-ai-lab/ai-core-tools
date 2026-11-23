import React, { useEffect, useId, useRef } from 'react';
import { X } from 'lucide-react';
import { hasOpenModal } from './Modal';

const FOCUSABLE_SELECTORS = [
  'a[href]',
  'button:not([disabled])',
  'textarea:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ');

export interface SidePanelProps {
  /** Whether the panel is visible. */
  readonly open: boolean;
  /** Called on backdrop click, close button and Escape key. */
  readonly onClose: () => void;
  /** Small uppercase heading shown at the top of the panel. */
  readonly title: React.ReactNode;
  /** Edge the panel slides in from. Defaults to `left`. */
  readonly side?: 'left' | 'right';
  /** Extra controls rendered in the header, before the close button. */
  readonly headerActions?: React.ReactNode;
  /** Content rendered under the title row inside the header (e.g. a search input). */
  readonly toolbar?: React.ReactNode;
  /** Content pinned to the bottom of the panel, outside the scroll area. */
  readonly footer?: React.ReactNode;
  /** Tailwind width classes for the panel. */
  readonly widthClassName?: string;
  readonly closeLabel?: string;
  /** DOM id of the dialog, so the control that opens it can point to it with `aria-controls`. */
  readonly id?: string;
  readonly children: React.ReactNode;
}

/**
 * Overlay side panel (drawer) with a dimmed backdrop. It is absolutely
 * positioned, so it covers its nearest `relative` ancestor — place it inside
 * the area it should overlay.
 */
export function SidePanel({
  open,
  onClose,
  title,
  side = 'left',
  headerActions,
  toolbar,
  footer,
  widthClassName = 'w-[310px] max-w-[88%]',
  closeLabel = 'Close panel',
  id,
  children,
}: SidePanelProps) {
  const generatedId = useId();
  const panelId = id ?? generatedId;
  const panelRef = useRef<HTMLDivElement>(null);
  const backdropRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  // Dialog behaviour (same contract as Modal): focus moves in, Tab wraps, the rest of the page is inert
  // while it is open, Esc closes it, and focus goes back to where it was.
  useEffect(() => {
    if (!open) return;
    const panel = panelRef.current;
    const returnTarget = document.activeElement;

    // Make the siblings of the panel (the page it overlays) unreachable.
    const inerted: Element[] = [];
    for (const sibling of Array.from(panel?.parentElement?.children ?? [])) {
      if (sibling === panel || sibling === backdropRef.current || sibling.hasAttribute('inert')) continue;
      sibling.setAttribute('inert', '');
      inerted.push(sibling);
    }

    // Do not take focus from a control inside the panel that already asked for it (autoFocus).
    if (panel && !panel.contains(document.activeElement)) panel.focus();

    const handleKeyDown = (e: KeyboardEvent) => {
      // A modal opened from the panel (e.g. a delete confirmation) owns Esc and Tab.
      if (hasOpenModal() || e.defaultPrevented) return;
      if (e.key === 'Escape') {
        e.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (e.key !== 'Tab' || !panel) return;
      const focusables = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTORS))
        .filter((el) => !el.closest('[hidden]'));
      if (focusables.length === 0) {
        e.preventDefault();
        panel.focus();
        return;
      }
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && (active === first || active === panel)) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      } else if (!panel.contains(active)) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      inerted.forEach((el) => el.removeAttribute('inert'));
      // The element that opened the panel may be gone (or never had focus): then leave focus where it is.
      if (returnTarget instanceof HTMLElement && returnTarget.isConnected && returnTarget !== document.body) {
        returnTarget.focus();
      }
    };
  }, [open]);

  if (!open) return null;

  const isLeft = side === 'left';

  return (
    <>
      <div
        ref={backdropRef}
        aria-hidden="true"
        onClick={onClose}
        className="absolute inset-0 z-[24] bg-ink/15 dark:bg-black/40 animate-fade-in"
      />
      <div
        ref={panelRef}
        id={panelId}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === 'string' ? title : undefined}
        className={`absolute inset-y-0 z-[25] flex flex-col outline-none ${widthClassName}
                    bg-surface dark:bg-surface-dark border-line dark:border-line-dark
                    ${isLeft
                      ? 'left-0 border-r shadow-[14px_0_40px_rgba(0,0,0,0.12)] animate-slide-in-left'
                      : 'right-0 border-l shadow-[-14px_0_40px_rgba(0,0,0,0.12)] animate-slide-in-right'}`}
      >
        <div className="flex-none px-3.5 pt-3.5 pb-3 border-b border-line dark:border-line-dark">
          <div className={`flex items-center gap-2.5 ${toolbar ? 'mb-[11px]' : ''}`}>
            <h2 className="text-[11px] uppercase tracking-[0.06em] text-fg-secondary dark:text-fg-secondary-dark">
              {title}
            </h2>
            <span className="flex-1" />
            {headerActions}
            <button
              type="button"
              onClick={onClose}
              aria-label={closeLabel}
              title={closeLabel}
              className="flex-none flex items-center p-1 -mr-1 rounded
                         text-fg-secondary dark:text-fg-secondary-dark
                         hover:text-fg dark:hover:text-fg-dark transition-colors duration-150
                         focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus dark:focus-visible:ring-focus-dark"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          {toolbar}
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain px-2.5 pt-2 pb-4">
          {children}
        </div>
        {footer && (
          <div className="flex-none px-4 py-3 border-t border-line dark:border-line-dark">
            {footer}
          </div>
        )}
      </div>
    </>
  );
}

export default SidePanel;
