import React, { useRef, useEffect } from 'react';

/**
 * Interface defining the structure of a tab item
 */
export interface TabItem {
  id: string;
  label: string;
  icon?: string;
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
}: TabsProps): React.ReactElement {
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

    if (nextIndex !== null) {
      const nextTabId = tabs[nextIndex].id;
      onChange(nextTabId);

      // Focus the newly selected tab for keyboard navigation UX
      setTimeout(() => {
        tabRefs.current[nextIndex]?.focus();
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
    <div className={`border-b border-gray-200 ${className}`}>
      <div
        ref={tabListRef}
        role="tablist"
        className="flex flex-wrap sm:flex-nowrap overflow-x-auto scrollbar-hide"
        aria-label="Tab navigation"
      >
        {tabs.map((tab, index) => {
          const isActive = tab.id === activeTab;

          return (
            <button
              key={tab.id}
              ref={(el) => {
                tabRefs.current[index] = el;
              }}
              role="tab"
              aria-selected={isActive}
              aria-controls={`${tab.id}-panel`}
              tabIndex={isActive ? 0 : -1}
              onClick={() => onChange(tab.id)}
              onKeyDown={(e) => handleKeyDown(e, index)}
              className={`
                px-4 py-3 text-sm font-medium whitespace-nowrap
                border-b-2 transition-colors duration-200
                focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-0
                ${
                  isActive
                    ? 'border-blue-600 text-blue-600'
                    : 'border-transparent text-gray-600 hover:text-gray-800 hover:bg-gray-50'
                }
              `}
            >
              {tab.icon && <span className="mr-2">{tab.icon}</span>}
              {tab.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default Tabs;
