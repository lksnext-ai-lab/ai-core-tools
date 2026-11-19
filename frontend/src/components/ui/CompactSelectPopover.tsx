import {
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';
import { Check, ChevronDown } from 'lucide-react';

import {
  TYPE_AHEAD_RESET_MS,
  activateResult,
  buildGroups,
  chipValueText,
  clampIndex,
  filterOptions,
  flattenGroups,
  nextActiveIndex,
  selectedLabels,
  typeAheadIndex,
  type NavigationKey,
} from './compactSelectLogic';

export interface CompactSelectOption {
  readonly value: string;
  readonly label: string;
  /** Secondary text under the label. */
  readonly description?: string;
  /** Group header. Options sharing the same text are listed together, in order of first appearance. */
  readonly group?: string;
  readonly disabled?: boolean;
  /** Shown inside a disabled option so users learn why it cannot be chosen. */
  readonly disabledReason?: string;
  /** Optional adornment rendered after the label (e.g. a status badge). */
  readonly trailing?: ReactNode;
}

interface CompactSelectPopoverBaseProps {
  /** Accessible name of the listbox, and of the trigger when there is no visible `label`. */
  readonly ariaLabel: string;
  /** Visible chip label (e.g. "Model"). It is part of the trigger's accessible name. */
  readonly label?: string;
  readonly icon?: ReactNode;
  readonly options: readonly CompactSelectOption[];
  /**
   * Label for a selected value that is not in `options` (e.g. a deleted or retired item).
   * Without it such values are not shown; callers should then include the current value in
   * `options` as a disabled option with a reason.
   */
  readonly fallbackLabel?: (value: string) => string;
  /** Text shown in the chip when nothing is selected. */
  readonly placeholder?: string;
  readonly disabled?: boolean;
  readonly searchable?: boolean;
  readonly searchPlaceholder?: string;
  readonly searchAriaLabel?: string;
  /** Text of the empty list / no search match message (also announced). */
  readonly emptyLabel?: string;
  /** Announced while searching, e.g. "3 results". */
  readonly resultsLabel?: (count: number) => string;
  /** Announced after toggling an option in multiple mode, e.g. "Translate selected". */
  readonly selectionChangeLabel?: (label: string, selected: boolean) => string;
  readonly className?: string;
  readonly id?: string;
}

export interface CompactSelectPopoverSingleProps extends CompactSelectPopoverBaseProps {
  readonly multiple?: false;
  readonly value: string | null;
  readonly onChange: (value: string) => void;
}

export interface CompactSelectPopoverMultipleProps extends CompactSelectPopoverBaseProps {
  readonly multiple: true;
  readonly value: readonly string[];
  readonly onChange: (values: string[]) => void;
  /** Builds the chip value when more than two options are selected (e.g. "3 selected"). */
  readonly summarizeSelection?: (selectedLabels: readonly string[]) => string;
}

export type CompactSelectPopoverProps =
  | CompactSelectPopoverSingleProps
  | CompactSelectPopoverMultipleProps;

const POPOVER_PREFERRED_HEIGHT_PX = 320;
const POPOVER_MIN_HEIGHT_PX = 120;
const POPOVER_GAP_PX = 4;
const VIEWPORT_MARGIN_PX = 8;
const POPOVER_MIN_WIDTH_PX = 240;

interface PopoverPosition {
  readonly left: number;
  readonly width: number;
  readonly top?: number;
  readonly bottom?: number;
  readonly maxHeight: number;
}

function viewportSize(): { width: number; height: number } {
  const vv = window.visualViewport;
  return { width: vv?.width ?? window.innerWidth, height: vv?.height ?? window.innerHeight };
}

function computePosition(trigger: DOMRect): PopoverPosition {
  const vp = viewportSize();
  const spaceBelow = vp.height - trigger.bottom - POPOVER_GAP_PX - VIEWPORT_MARGIN_PX;
  const spaceAbove = trigger.top - POPOVER_GAP_PX - VIEWPORT_MARGIN_PX;
  const openUp = spaceBelow < POPOVER_PREFERRED_HEIGHT_PX && spaceAbove > spaceBelow;
  const hardCap = Math.max(vp.height - 2 * VIEWPORT_MARGIN_PX, 0);
  const maxHeight = Math.min(
    POPOVER_PREFERRED_HEIGHT_PX,
    hardCap,
    Math.max(openUp ? spaceAbove : spaceBelow, Math.min(POPOVER_MIN_HEIGHT_PX, hardCap)),
  );
  const width = Math.min(Math.max(trigger.width, POPOVER_MIN_WIDTH_PX), vp.width - 2 * VIEWPORT_MARGIN_PX);
  const left = Math.max(VIEWPORT_MARGIN_PX, Math.min(trigger.left, vp.width - width - VIEWPORT_MARGIN_PX));
  const base = { left, width, maxHeight };
  return openUp
    ? { ...base, bottom: vp.height - trigger.top + POPOVER_GAP_PX }
    : { ...base, top: trigger.bottom + POPOVER_GAP_PX };
}

function samePosition(a: PopoverPosition | null, b: PopoverPosition): boolean {
  return (
    a !== null &&
    a.left === b.left &&
    a.width === b.width &&
    a.top === b.top &&
    a.bottom === b.bottom &&
    a.maxHeight === b.maxHeight
  );
}

const NAVIGATION_KEYS: readonly string[] = ['ArrowDown', 'ArrowUp', 'Home', 'End', 'PageDown', 'PageUp'];

/**
 * Compact chip-like trigger (icon, label, current value) that opens a popover listbox.
 * Supports single and multiple selection, grouped options, disabled options with a visible
 * reason and an optional search box. The popover is portaled to <body> with fixed
 * positioning, flips upward when there is more room above, fits the (visual) viewport and
 * closes on Escape (returning focus to the trigger), Tab, an outside click or when the
 * trigger scrolls out of view.
 *
 * Keyboard: Enter / Space / ArrowDown / ArrowUp open the popover; ArrowUp/Down, Home, End,
 * PageUp and PageDown move the active option (disabled options stay reachable so their reason
 * can be read); Enter (and Space when there is no search box) selects it; without a search box,
 * typing characters jumps to the next option starting with them.
 */
export function CompactSelectPopover(props: Readonly<CompactSelectPopoverProps>) {
  const {
    ariaLabel,
    label,
    icon,
    options,
    fallbackLabel,
    placeholder = '',
    disabled = false,
    searchable = false,
    searchPlaceholder,
    searchAriaLabel,
    emptyLabel,
    resultsLabel,
    selectionChangeLabel,
    className = '',
    id,
  } = props;
  const multiple = props.multiple === true;

  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const [position, setPosition] = useState<PopoverPosition | null>(null);
  const [selectionAnnouncement, setSelectionAnnouncement] = useState('');
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const typeAheadRef = useRef<{ buffer: string; timer: ReturnType<typeof setTimeout> | null }>({
    buffer: '',
    timer: null,
  });
  const baseId = useId();
  const listboxId = `${baseId}-listbox`;
  const labelId = `${baseId}-label`;
  const valueId = `${baseId}-value`;
  const optionId = (index: number) => `${baseId}-opt-${index}`;

  const selectedValues = useMemo<readonly string[]>(() => {
    if (props.multiple === true) return props.value;
    return props.value === null ? [] : [props.value];
  }, [props.multiple, props.value]);

  const visibleOptions = useMemo(() => filterOptions(options, query), [options, query]);
  const groups = useMemo(() => buildGroups(visibleOptions), [visibleOptions]);
  const flat = useMemo(() => flattenGroups(groups), [groups]);
  const safeActive = clampIndex(activeIndex, flat.length);

  const labels = useMemo(
    () => selectedLabels(options, selectedValues, fallbackLabel),
    [options, selectedValues, fallbackLabel],
  );
  const valueText = chipValueText(
    labels,
    placeholder,
    props.multiple === true ? props.summarizeSelection : undefined,
  );

  const reposition = () => {
    const rect = triggerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const next = computePosition(rect);
    setPosition((prev) => (samePosition(prev, next) ? prev : next));
  };

  const open = () => {
    const visual = flattenGroups(buildGroups(options));
    const firstSelected = visual.findIndex((o) => selectedValues.includes(o.value));
    setQuery('');
    setSelectionAnnouncement('');
    setActiveIndex(Math.max(0, firstSelected));
    reposition();
    setIsOpen(true);
  };

  const close = (returnFocus: boolean) => {
    setIsOpen(false);
    if (returnFocus) triggerRef.current?.focus();
  };

  useEffect(() => {
    if (!isOpen) return;
    (searchable ? searchRef.current : listRef.current)?.focus();

    const handleOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      if (!triggerRef.current?.contains(target) && !popoverRef.current?.contains(target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleOutside);
    return () => document.removeEventListener('mousedown', handleOutside);
  }, [isOpen, searchable]);

  useLayoutEffect(() => {
    if (!isOpen) return;
    const update = (event?: Event) => {
      // The popover's own list scrolling must not trigger work.
      if (event?.type === 'scroll' && popoverRef.current?.contains(event.target as Node)) return;
      const rect = triggerRef.current?.getBoundingClientRect();
      if (!rect) return;
      const vp = viewportSize();
      if (event?.type === 'scroll' && (rect.bottom < 0 || rect.top > vp.height)) {
        // Return focus to the trigger if it was inside the (unmounting) popover.
        const focusInside = popoverRef.current?.contains(document.activeElement) ?? false;
        setIsOpen(false);
        if (focusInside) triggerRef.current?.focus({ preventScroll: true });
        return;
      }
      const next = computePosition(rect);
      setPosition((prev) => (samePosition(prev, next) ? prev : next));
    };
    update();
    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    window.visualViewport?.addEventListener('resize', update);
    return () => {
      window.removeEventListener('resize', update);
      window.removeEventListener('scroll', update, true);
      window.visualViewport?.removeEventListener('resize', update);
    };
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    document.getElementById(optionId(safeActive))?.scrollIntoView?.({ block: 'nearest' });
    // optionId only depends on the stable baseId.
  }, [isOpen, safeActive]);

  useEffect(() => {
    if (disabled) setIsOpen(false);
  }, [disabled]);

  useEffect(() => {
    const state = typeAheadRef.current;
    return () => {
      if (state.timer) clearTimeout(state.timer);
    };
  }, []);

  const activate = () => {
    const result = activateResult(flat, safeActive, multiple, selectedValues);
    if (result.kind === 'none') return;
    if (result.kind === 'single' && props.multiple !== true) {
      props.onChange(result.value);
      close(true);
    } else if (result.kind === 'multiple' && props.multiple === true) {
      props.onChange(result.values);
      const option = flat[safeActive];
      setSelectionAnnouncement(selectionChangeLabel?.(option.label, result.selected) ?? '');
    }
  };

  const handleTypeAhead = (char: string) => {
    const state = typeAheadRef.current;
    if (state.timer) clearTimeout(state.timer);
    state.buffer += char;
    state.timer = setTimeout(() => {
      state.buffer = '';
    }, TYPE_AHEAD_RESET_MS);
    const found = typeAheadIndex(flat, safeActive, state.buffer);
    if (found >= 0) setActiveIndex(found);
  };

  const handleTriggerKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (isOpen) return;
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      open();
    }
  };

  const handlePopoverKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    const { key } = event;
    if (NAVIGATION_KEYS.includes(key)) {
      // In the search box Home/End keep moving the text caret.
      if (searchable && (key === 'Home' || key === 'End')) return;
      event.preventDefault();
      setActiveIndex(nextActiveIndex(safeActive, key as NavigationKey, flat.length));
      return;
    }
    if (key === 'Enter') {
      event.preventDefault();
      activate();
    } else if (key === ' ' && !searchable && typeAheadRef.current.buffer === '') {
      event.preventDefault();
      activate();
    } else if (key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      close(true);
    } else if (key === 'Tab') {
      // The popover lives at the end of <body>: hand focus back so Tab continues from the trigger.
      close(true);
    } else if (!searchable && key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
      event.preventDefault();
      handleTypeAhead(key);
    }
  };

  const activeDescendant = flat.length > 0 ? optionId(safeActive) : undefined;
  const trimmedQuery = query.trim();
  // The last toggle wins: it is cleared on every query change.
  let liveText = selectionAnnouncement;
  if (!liveText) {
    if (flat.length === 0 && emptyLabel) liveText = emptyLabel;
    else if (trimmedQuery && resultsLabel) liveText = resultsLabel(flat.length);
  }

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        id={id}
        disabled={disabled}
        title={valueText || undefined}
        aria-labelledby={`${labelId} ${valueId}`}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-controls={isOpen ? listboxId : undefined}
        onClick={() => (isOpen ? close(false) : open())}
        onKeyDown={handleTriggerKeyDown}
        className={`inline-flex min-h-11 max-w-full items-center gap-1.5 rounded-full border border-line bg-surface px-3 py-1 text-xs text-fg transition-colors hover:bg-surface-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-focus disabled:cursor-not-allowed disabled:opacity-60 motion-reduce:transition-none sm:min-h-8 dark:border-line-dark dark:bg-surface-dark dark:text-fg-dark dark:hover:bg-surface-hover-dark dark:focus-visible:ring-focus-dark ${className}`}
      >
        {icon && (
          <span aria-hidden="true" className="inline-flex shrink-0 text-fg-tertiary dark:text-fg-tertiary-dark">
            {icon}
          </span>
        )}
        <span
          id={labelId}
          className={label ? 'shrink-0 text-fg-secondary dark:text-fg-secondary-dark' : 'sr-only'}
        >
          {label ?? ariaLabel}
        </span>
        <span id={valueId} className="min-w-0 truncate font-medium">{valueText}</span>
        <ChevronDown
          aria-hidden="true"
          className={`h-3.5 w-3.5 shrink-0 text-fg-tertiary transition-transform motion-reduce:transition-none dark:text-fg-tertiary-dark ${
            isOpen ? 'rotate-180' : ''
          }`}
        />
      </button>

      {isOpen &&
        position &&
        createPortal(
          <div
            ref={popoverRef}
            // Fixed coordinates are computed from the trigger rect at runtime; Tailwind cannot express them.
            style={{
              left: position.left,
              width: position.width,
              top: position.top,
              bottom: position.bottom,
              maxHeight: position.maxHeight,
            }}
            className="fixed z-50 flex flex-col overflow-hidden rounded-md border border-line bg-surface shadow-[0_14px_40px_rgba(32,28,20,0.14)] dark:border-line-dark dark:bg-surface-dark dark:shadow-[0_14px_40px_rgba(0,0,0,0.55)]"
          >
            {searchable && (
              <input
                ref={searchRef}
                type="text"
                role="combobox"
                aria-expanded="true"
                aria-haspopup="listbox"
                aria-autocomplete="list"
                aria-controls={listboxId}
                aria-activedescendant={activeDescendant}
                aria-label={searchAriaLabel ?? ariaLabel}
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setActiveIndex(0);
                  setSelectionAnnouncement('');
                }}
                onKeyDown={handlePopoverKeyDown}
                placeholder={searchPlaceholder}
                autoComplete="off"
                className="w-full shrink-0 border-b border-line bg-transparent px-3 py-2 text-sm text-fg placeholder:text-fg-secondary focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus dark:border-line-dark dark:text-fg-dark dark:placeholder:text-fg-secondary-dark dark:focus-visible:ring-focus-dark"
              />
            )}
            <div
              ref={listRef}
              id={listboxId}
              role="listbox"
              aria-label={ariaLabel}
              aria-multiselectable={multiple || undefined}
              aria-activedescendant={searchable ? undefined : activeDescendant}
              tabIndex={searchable ? undefined : 0}
              onKeyDown={searchable ? undefined : handlePopoverKeyDown}
              className="min-h-0 flex-1 overflow-y-auto py-1 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus dark:focus-visible:ring-focus-dark"
            >
              {groups.map((group) => {
                const headerId = `${baseId}-grp-${group.index}`;
                return (
                  <div
                    key={group.index}
                    role={group.header ? 'group' : 'presentation'}
                    aria-labelledby={group.header ? headerId : undefined}
                  >
                    {group.header && (
                      <div
                        id={headerId}
                        className="px-3 pb-1 pt-2 text-[11px] font-medium uppercase tracking-wide text-fg-secondary dark:text-fg-secondary-dark"
                      >
                        {group.header}
                      </div>
                    )}
                    {group.items.map(({ option, index }) => {
                      const selected = selectedValues.includes(option.value);
                      const active = index === safeActive;
                      const activate = () => {
                        setActiveIndex(index);
                        const result = activateResult(flat, index, multiple, selectedValues);
                        if (result.kind === 'single' && props.multiple !== true) {
                          props.onChange(result.value);
                          close(true);
                        } else if (result.kind === 'multiple' && props.multiple === true) {
                          props.onChange(result.values);
                          setSelectionAnnouncement(
                            selectionChangeLabel?.(option.label, result.selected) ?? '',
                          );
                        }
                      };
                      return (
                        <div
                          key={option.value}
                          id={optionId(index)}
                          role="option"
                          aria-selected={selected}
                          aria-disabled={option.disabled || undefined}
                          onMouseDown={(e) => e.preventDefault()}
                          onClick={activate}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              e.preventDefault();
                              activate();
                            }
                          }}
                          onMouseEnter={() => setActiveIndex(index)}
                          className={`flex items-start gap-2 px-3 py-1.5 text-sm ${
                            option.disabled
                              ? 'cursor-not-allowed text-fg-secondary dark:text-fg-secondary-dark'
                              : 'cursor-pointer text-fg dark:text-fg-dark'
                          } ${active ? 'bg-surface-hover ring-2 ring-inset ring-focus dark:bg-surface-hover-dark dark:ring-focus-dark' : ''}`}
                        >
                          <span aria-hidden="true" className="mt-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center">
                            {selected && <Check className="h-4 w-4 text-accent dark:text-accent-dark" />}
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className={`block truncate ${selected ? 'font-medium' : ''}`}>
                              {option.label}
                            </span>
                            {option.description && (
                              <span className="block truncate text-xs text-fg-secondary dark:text-fg-secondary-dark">
                                {option.description}
                              </span>
                            )}
                            {option.disabled && option.disabledReason && (
                              <span className="block text-xs italic text-fg-secondary dark:text-fg-secondary-dark">
                                {option.disabledReason}
                              </span>
                            )}
                          </span>
                          {option.trailing && <span className="shrink-0">{option.trailing}</span>}
                        </div>
                      );
                    })}
                  </div>
                );
              })}
            </div>
            {flat.length === 0 && emptyLabel && (
              <p className="shrink-0 px-3 py-2 text-sm text-fg-secondary dark:text-fg-secondary-dark">
                {emptyLabel}
              </p>
            )}
            <div role="status" aria-live="polite" className="sr-only">
              {liveText}
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}

export default CompactSelectPopover;
