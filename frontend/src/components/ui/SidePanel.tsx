import React, { useEffect } from 'react';
import { X } from 'lucide-react';

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
  /** Tailwind width classes for the panel. */
  readonly widthClassName?: string;
  readonly closeLabel?: string;
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
  widthClassName = 'w-[310px] max-w-[88%]',
  closeLabel = 'Close panel',
  children,
}: SidePanelProps) {
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  const isLeft = side === 'left';

  return (
    <>
      <div
        aria-hidden="true"
        onClick={onClose}
        className="absolute inset-0 z-[24] bg-ink/15 dark:bg-black/40 animate-fade-in"
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === 'string' ? title : undefined}
        className={`absolute inset-y-0 z-[25] flex flex-col ${widthClassName}
                    bg-canvas-alt dark:bg-canvas-alt-dark border-line dark:border-line-dark
                    ${isLeft
                      ? 'left-0 border-r shadow-[14px_0_40px_rgba(0,0,0,0.12)] animate-slide-in-left'
                      : 'right-0 border-l shadow-[-14px_0_40px_rgba(0,0,0,0.12)] animate-slide-in-right'}`}
      >
        <div className="flex-none px-3.5 pt-3.5 pb-3 border-b border-line dark:border-line-dark">
          <div className={`flex items-center gap-2.5 ${toolbar ? 'mb-[11px]' : ''}`}>
            <h2 className="text-[11px] uppercase tracking-[0.06em] text-fg-tertiary dark:text-fg-tertiary-dark">
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
                         text-fg-tertiary dark:text-fg-tertiary-dark
                         hover:text-fg dark:hover:text-fg-dark transition-colors duration-150"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          {toolbar}
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain px-2.5 pt-2 pb-4">
          {children}
        </div>
      </aside>
    </>
  );
}

export default SidePanel;
