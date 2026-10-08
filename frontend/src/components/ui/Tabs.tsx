import React, { useRef, useEffect } from 'react';

/**
 * Interface defining the structure of a tab item
 */
export interface TabItem {
  id: string;
  label: string;
  icon?: string;
  /** When true, the tab is shown but cannot be activated (e.g. "save first"). */
  disabled?: boolean;
  /** Tooltip/accessible hint shown when the tab is disabled. */
  disabledReason?: string;
}

/**
 * Interface defining the props for the Tabs component
 */
export interface TabsProps {
  tabs: TabItem[];
  activeTab: string;
  onChange: (tabId: string) => void;
  className?: string;
}

/**
 * Reusable Tabs navigation component
 * 
 * A fully accessible, responsive tab navigation component built with Tailwind CSS.
 * Supports keyboard navigation (arrow keys), ARIA labels, and semantic HTML.
 * 
 * @example
 * const [activeTab, setActiveTab] = useState<string>("basic");
 * 
 * return (
 *   <Tabs 
 *     tabs={[
 *       { id: "basic", label: "Basic" },
 *       { id: "prompts", label: "Prompts" },
 *       { id: "config", label: "Configuration" },
 *     ]}
 *     activeTab={activeTab}
 *     onChange={setActiveTab}
 *   />
 * );
 */
export function Tabs({
  tabs,
  activeTab,
  onChange,
  className = ''
}: Readonly<TabsProps>): React.ReactElement {
  const tabListRef = useRef<HTMLDivElement>(null);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  /**
   * Handle keyboard navigation (arrow keys for tab switching)
   */
  const handleKeyDown = (e: React.KeyboardEvent, currentIndex: number) => {
    let nextIndex: number | null = null;

    if (e.key === 'ArrowRight') {
      nextIndex = (currentIndex + 1) % tabs.length;
      e.preventDefault();
    } else if (e.key === 'ArrowLeft') {
      nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
      e.preventDefault();
    } else if (e.key === 'Home') {
      nextIndex = 0;
      e.preventDefault();
    } else if (e.key === 'End') {
      nextIndex = tabs.length - 1;
      e.preventDefault();
    }

    // Skip disabled tabs so arrow-key navigation never lands on one.
    if (nextIndex !== null) {
      let attempts = 0;
      while (tabs[nextIndex]?.disabled && attempts < tabs.length) {
        nextIndex = e.key === 'ArrowLeft'
          ? (nextIndex - 1 + tabs.length) % tabs.length
          : (nextIndex + 1) % tabs.length;
        attempts += 1;
      }
      if (tabs[nextIndex]?.disabled) return;

      const targetIndex = nextIndex;
      onChange(tabs[targetIndex].id);

      // Focus the newly selected tab for keyboard navigation UX
      setTimeout(() => {
        tabRefs.current[targetIndex]?.focus();
      }, 0);
    }
  };

  /**
   * Ensure active tab button has focus when changed via keyboard
   */
  useEffect(() => {
    const activeTabIndex = tabs.findIndex((tab) => tab.id === activeTab);
    if (activeTabIndex !== -1 && document.activeElement?.getAttribute('role') === 'tab') {
      tabRefs.current[activeTabIndex]?.focus();
    }
  }, [activeTab, tabs]);

  return (
    <div className={`border-b border-gray-200 dark:border-gray-700 ${className}`}>
      <div
        ref={tabListRef}
        role="tablist"
        className="flex flex-wrap sm:flex-nowrap overflow-x-auto scrollbar-hide"
        aria-label="Tab navigation"
      >
        {tabs.map((tab, index) => {
          const isActive = tab.id === activeTab;
          const isDisabled = !!tab.disabled;
          const disabledReasonId = `${tab.id}-disabled-reason`;

          return (
            <React.Fragment key={tab.id}>
              <button
                type="button"
                ref={(el) => {
                  tabRefs.current[index] = el;
                }}
                role="tab"
                aria-selected={isActive}
                aria-controls={`${tab.id}-panel`}
                aria-disabled={isDisabled}
                aria-describedby={isDisabled && tab.disabledReason ? disabledReasonId : undefined}
                title={isDisabled ? tab.disabledReason : undefined}
                tabIndex={isActive ? 0 : -1}
                onClick={() => {
                  if (!isDisabled) onChange(tab.id);
                }}
                onKeyDown={(e) => handleKeyDown(e, index)}
                className={`
                  px-4 py-3 text-sm font-medium whitespace-nowrap
                  transition-colors duration-200
                  focus:outline-none
                  ${
                    isDisabled
                      ? 'cursor-not-allowed text-gray-400 dark:text-gray-600'
                      : isActive
                        ? 'border-b-2 border-blue-600 text-blue-600 dark:border-blue-400 dark:text-blue-400'
                        : 'text-gray-600 hover:text-gray-800 dark:text-gray-300 dark:hover:text-gray-100'
                  }
                `}
              >
                {tab.icon && <span className="mr-2">{tab.icon}</span>}
                {tab.label}
              </button>
              {isDisabled && tab.disabledReason && (
                <span id={disabledReasonId} className="sr-only">
                  {tab.disabledReason}
                </span>
              )}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
}

export default Tabs;
