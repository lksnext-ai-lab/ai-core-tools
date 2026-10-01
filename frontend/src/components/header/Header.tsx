import React, { useState, useRef, useEffect } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { Moon, Search, Sun } from 'lucide-react';
import { useAuth } from '../../auth/AuthContext';
import { useUser } from '../../contexts/UserContext';
import { useDeploymentMode } from '../../contexts/DeploymentModeContext';
import { useTheme } from '../../themes/ThemeContext';
import PendingInvitationsNotification from '../PendingInvitationsNotification';
import type { NavigationConfig, OrganizationConfig } from '../../core/types';

interface HeaderProps {
  navigationConfig?: NavigationConfig;
  className?: string;
  children?: React.ReactNode;
  title?: string;
  logoUrl?: string;
  organization?: OrganizationConfig;
}

export const Header: React.FC<HeaderProps> = ({
  className = "",
  children,
  title,
  logoUrl,
  organization
}) => {
  const { appId } = useParams();
  const { user } = useUser();
  const { logout } = useAuth();
  const { isSaasMode, authMode, isLoading: modeLoading } = useDeploymentMode();
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const userMenuRef = useRef<HTMLDivElement>(null);
  const { colorMode, toggleColorMode } = useTheme();
  const isDark = colorMode === 'dark';
  const location = useLocation();
  // Header search is visual only for now (design v3 placeholder) — shown on Home, no behaviour.
  const isHome = location.pathname === '/home';

  const getUserInitials = (name?: string, email?: string) => {
    if (name) {
      return name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
    }
    if (email) {
      return email[0].toUpperCase();
    }
    return 'U';
  };

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (userMenuRef.current && !userMenuRef.current.contains(event.target as Node)) {
        setIsUserMenuOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  return (
    <header className={`relative z-20 bg-surface border-b border-line h-14 flex items-center shadow-[0_4px_10px_rgba(32,32,32,0.08)] dark:bg-surface-dark dark:border-line-dark dark:shadow-[0_4px_10px_rgba(0,0,0,0.4)] ${className}`}>

      {/* Design v3: brand block (isotipo + name) — independent of the sidebar width */}
      <div className="flex-shrink-0 flex items-center gap-2 pl-3 pr-4 min-w-0">
        <Link to="/apps" className="flex-shrink-0 flex items-center gap-2 p-1 rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-focus dark:focus-visible:ring-focus-dark">
          <img
            src={logoUrl || "/mattin-small.png"}
            alt={title || "AI Core Tools"}
            className="w-[46px] h-[33px] object-contain"
          />
          <span className="hidden sm:inline font-display text-xl font-medium tracking-[-0.01em] text-fg whitespace-nowrap dark:text-fg-dark">
            {title || "AI Core Tools"}
          </span>
        </Link>
      </div>

      <div className="w-px h-[22px] bg-line flex-shrink-0 dark:bg-line-dark" />

      <div className="flex-1 min-w-0 flex items-center justify-between pl-4 pr-3 gap-4">
        {/* Organization chip = breadcrumb level 1; a "›" separates it from the page crumbs when both exist */}
        <div className="flex-1 min-w-0 flex items-center gap-[9px] [&>a+div]:before:content-['›'] [&>a+div]:before:text-fg-faint2 dark:[&>a+div]:before:text-fg-faint2-dark">
          {organization && (
            <Link
              to="/home"
              title={`${organization.name} · Organization`}
              className="flex-shrink-0 flex items-center gap-[9px] py-1 pl-1 pr-2 rounded-lg hover:bg-surface-hover transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-focus dark:hover:bg-surface-hover-dark dark:focus-visible:ring-focus-dark"
            >
              {organization.logo ? (
                <img src={organization.logo} alt="" className="w-[26px] h-[26px] rounded-full object-contain flex-shrink-0" />
              ) : (
                <span aria-hidden="true" className="w-[26px] h-[26px] flex-shrink-0 rounded-full bg-ink text-ink-on font-display text-[11px] font-medium flex items-center justify-center dark:bg-ink-dark dark:text-ink-on-dark">
                  {organization.name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)}
                </span>
              )}
              <span className="hidden md:flex flex-col items-start leading-[1.12]">
                <span className="text-[13px] font-medium text-fg whitespace-nowrap dark:text-fg-dark">{organization.name}</span>
                <span className="text-[9px] uppercase tracking-[0.06em] text-fg-tertiary dark:text-fg-tertiary-dark">Organization</span>
              </span>
            </Link>
          )}
          {children}
        </div>

        {isHome && (
          <div role="search" className="hidden md:block flex-1 max-w-[460px] mx-6">
            <label htmlFor="header-search" className="sr-only">Search agents, apps or chats</label>
            <div className="flex items-center gap-[9px] px-[13px] py-2 bg-surface-hover border border-line rounded-lg focus-within:border-ink dark:bg-surface-hover-dark dark:border-line-dark dark:focus-within:border-ink-dark">
              <Search className="w-[15px] h-[15px] flex-shrink-0 text-fg-tertiary dark:text-fg-tertiary-dark" aria-hidden="true" />
              <input
                id="header-search"
                name="search"
                type="search"
                placeholder="Search agents, apps or chats…"
                className="w-full p-0 border-none bg-transparent text-[13.5px] text-fg placeholder:text-fg-tertiary outline-none focus:ring-0 dark:text-fg-dark dark:placeholder:text-fg-tertiary-dark"
              />
            </div>
          </div>
        )}

        <div className="flex-shrink-0 flex items-center gap-1.5">
          <button
            type="button"
            onClick={toggleColorMode}
            aria-pressed={isDark}
            aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
            title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
            className="w-[34px] h-[34px] flex items-center justify-center rounded-lg text-fg-secondary hover:bg-surface-hover transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-focus dark:text-fg-secondary-dark dark:hover:bg-surface-hover-dark dark:focus-visible:ring-focus-dark"
          >
            {isDark
              ? <Sun className="w-[18px] h-[18px]" strokeWidth={1.5} aria-hidden="true" />
              : <Moon className="w-[18px] h-[18px]" strokeWidth={1.5} aria-hidden="true" />}
          </button>

          <PendingInvitationsNotification />

          <div className="w-px h-[22px] bg-line mx-1 flex-shrink-0 dark:bg-line-dark" />

          <div className="relative" ref={userMenuRef}>
            <button
              onClick={() => setIsUserMenuOpen(!isUserMenuOpen)}
              className="flex items-center gap-[9px] py-1 pl-1 pr-2 rounded-lg hover:bg-surface-hover transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-focus dark:hover:bg-surface-hover-dark dark:focus-visible:ring-focus-dark"
              aria-expanded={isUserMenuOpen}
              aria-haspopup="true"
            >
              <div className="w-8 h-8 bg-ink rounded-full flex items-center justify-center flex-shrink-0 dark:bg-ink-dark">
                <span className="font-display text-ink-on text-xs font-medium dark:text-ink-on-dark">
                  {getUserInitials(user?.name, user?.email)}
                </span>
              </div>
              <div className="hidden lg:block text-left">
                <p className="text-[13px] font-medium text-fg leading-tight whitespace-nowrap dark:text-fg-dark">
                  {user?.name || 'User'}
                </p>
                <p className="text-[11px] text-fg-tertiary leading-tight whitespace-nowrap dark:text-fg-tertiary-dark">
                  {user?.email}
                </p>
              </div>
              <svg
                className={`w-3 h-3 text-fg-faint flex-shrink-0 transition-transform dark:text-fg-faint-dark ${isUserMenuOpen ? 'rotate-180' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {isUserMenuOpen && (
              <div className="absolute right-0 mt-2 w-[280px] bg-surface border border-line rounded-lg shadow-[0_14px_40px_rgba(32,28,20,0.14)] overflow-hidden z-50 dark:bg-surface-dark dark:border-line-dark dark:shadow-[0_14px_40px_rgba(0,0,0,0.55)]">
                <div className="p-1.5" role="menu" aria-orientation="vertical">
                  <div className="-m-1.5 mb-1.5 p-4 border-b border-line dark:border-line-dark">
                    <p className="text-sm font-medium text-fg dark:text-fg-dark">
                      {user?.name || 'User'}
                    </p>
                    <p className="text-xs text-fg-tertiary truncate dark:text-fg-tertiary-dark">
                      {user?.email}
                    </p>
                  </div>

                  <Link
                    to="/profile"
                    className="flex items-center px-2.5 py-[9px] text-[13.5px] text-fg rounded-md hover:bg-surface-hover transition-colors dark:text-fg-dark dark:hover:bg-surface-hover-dark"
                    role="menuitem"
                    onClick={() => setIsUserMenuOpen(false)}
                  >
                    <svg className="w-4 h-4 mr-3 text-fg-tertiary dark:text-fg-tertiary-dark" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                    </svg>
                    Profile
                  </Link>

                  {appId && (
                    <Link
                      to={`/apps/${appId}/settings`}
                      className="flex items-center px-2.5 py-[9px] text-[13.5px] text-fg rounded-md hover:bg-surface-hover transition-colors dark:text-fg-dark dark:hover:bg-surface-hover-dark"
                      role="menuitem"
                      onClick={() => setIsUserMenuOpen(false)}
                    >
                      <svg className="w-4 h-4 mr-3 text-fg-tertiary dark:text-fg-tertiary-dark" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      </svg>
                      Settings
                    </Link>
                  )}

                  {isSaasMode && (
                    <Link
                      to="/subscription"
                      className="flex items-center px-2.5 py-[9px] text-[13.5px] text-fg rounded-md hover:bg-surface-hover transition-colors dark:text-fg-dark dark:hover:bg-surface-hover-dark"
                      role="menuitem"
                      onClick={() => setIsUserMenuOpen(false)}
                    >
                      <svg className="w-4 h-4 mr-3 text-fg-tertiary dark:text-fg-tertiary-dark" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
                      </svg>
                      Subscription
                    </Link>
                  )}

                  {!modeLoading && authMode === 'local' && (
                    <Link
                      to="/change-password"
                      className="flex items-center px-2.5 py-[9px] text-[13.5px] text-fg rounded-md hover:bg-surface-hover transition-colors dark:text-fg-dark dark:hover:bg-surface-hover-dark"
                      role="menuitem"
                      onClick={() => setIsUserMenuOpen(false)}
                    >
                      <svg className="w-4 h-4 mr-3 text-fg-tertiary dark:text-fg-tertiary-dark" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
                      </svg>
                      Change password
                    </Link>
                  )}

                  <div className="mt-1 pt-1 border-t border-line dark:border-line-dark">
                    <button
                      onClick={() => {
                        logout();
                        setIsUserMenuOpen(false);
                      }}
                      className="flex items-center w-full px-2.5 py-[9px] text-[13.5px] text-fg rounded-md hover:bg-surface-hover transition-colors dark:text-fg-dark dark:hover:bg-surface-hover-dark"
                      role="menuitem"
                    >
                      <svg className="w-4 h-4 mr-3 text-fg-tertiary dark:text-fg-tertiary-dark" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                      </svg>
                      Sign out
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

      </div>
    </header>
  );
};
