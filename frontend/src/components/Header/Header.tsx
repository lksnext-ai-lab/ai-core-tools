import React, { useState, useRef, useEffect } from 'react';
import { Link, useParams, useLocation } from 'react-router-dom';
import { useUser } from '../../contexts/UserContext';
import PendingInvitationsNotification from '../PendingInvitationsNotification';
import { apiService } from '../../services/api';
import type { NavigationConfig } from '../../core/types';

interface App {
  app_id: number;
  name: string;
  description?: string;
  created_at: string;
  updated_at: string;
  owner_id: number;
  is_public: boolean;
  agent_count: number;
  repository_count: number;
  silo_count: number;
  domain_count: number;
  collaborator_count: number;
  langsmith_configured: boolean;
  agent_rate_limit: number;
}

interface HeaderProps {
  navigationConfig?: NavigationConfig;
  className?: string;
  children?: React.ReactNode;
  title?: string;
  logoUrl?: string;
}

export const Header: React.FC<HeaderProps> = ({ 
  navigationConfig, 
  className = "",
  children,
  title,
  logoUrl
}) => {
  const { appId } = useParams();
  const location = useLocation();
  const { user, logout } = useUser();
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const [currentApp, setCurrentApp] = useState<App | null>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);

  // Fetch app data when appId changes
  useEffect(() => {
    if (appId) {
      loadAppData();
    } else {
      setCurrentApp(null);
    }
  }, [appId]);

  async function loadAppData() {
    if (!appId) return;
    
    try {
      const apps = await apiService.getApps();
      const app = apps.find((a: App) => a.app_id === parseInt(appId));
      setCurrentApp(app || null);
    } catch (error) {
      console.error('Failed to load app data:', error);
      setCurrentApp(null);
    }
  }

  const isActive = (path: string) => {
    return location.pathname.startsWith(path) ? 'text-blue-600 bg-blue-50' : 'text-gray-700 hover:text-blue-600 hover:bg-gray-50';
  };

  // Get user initials for avatar
  const getUserInitials = (name?: string, email?: string) => {
    if (name) {
      return name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
    }
    if (email) {
      return email[0].toUpperCase();
    }
    return 'U';
  };

  // Close dropdown when clicking outside
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
    <header className={`bg-white shadow-sm border-b border-gray-200 px-6 py-4 ${className}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-6">

          {/* App Context and Change App */}
          {appId && (
            <div className="flex items-center space-x-4">
              <div className="flex items-center space-x-3">
                <div>
                  <h3 className="text-sm font-medium text-gray-900">
                    {currentApp ? currentApp.name : 'Loading...'}
                  </h3>
                  <Link 
                  to="/apps" 
                  className="text-xs text-blue-600 hover:text-blue-800 px-2 py-1 rounded hover:bg-blue-50"
                >
                  Change App
                </Link>
                </div>
                
              </div>
            </div>
          )}

          {/* App-specific horizontal navigation */}
          {appId && navigationConfig?.appNavigation && (
            <nav className="flex space-x-6 border-l border-gray-200 pl-6">
              {navigationConfig.appNavigation.map((item, index) => {
                // Skip admin items if user is not admin
                if (item.adminOnly && !user?.is_admin) {
                  return null;
                }

                // Replace :appId placeholder with actual appId
                const path = item.path.replace(':appId', appId);
                const active = isActive(path);
                
                return (
                  <Link
                    key={`app-nav-${item.path}`}
                    to={path}
                    className={`relative px-1 py-2 text-sm font-medium transition-all duration-200 ${
                      active
                        ? 'text-blue-600' 
                        : 'text-gray-600 hover:text-gray-900'
                    }`}
                  >
                    <span className="flex items-center">
                      {item.icon && <span className="mr-2 text-base">{item.icon}</span>}
                      {item.name}
                    </span>
                    {/* Active indicator - bottom border */}
                    {active && (
                      <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-blue-600 rounded-full"></span>
                    )}
                  </Link>
                );
              }).filter(Boolean)}
            </nav>
          )}

          {/* Custom children */}
          {children}
        </div>
        
        {/* Top Right Actions */}
        <div className="flex items-center space-x-4">
          {/* Pending Invitations */}
          <PendingInvitationsNotification />
          
          {/* User Menu Dropdown */}
          <div className="relative" ref={userMenuRef}>
            <button
              onClick={() => setIsUserMenuOpen(!isUserMenuOpen)}
              className="flex items-center space-x-3 p-2 rounded-md hover:bg-gray-100 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
              aria-expanded={isUserMenuOpen}
              aria-haspopup="true"
            >
              <div className="w-8 h-8 bg-blue-500 rounded-full flex items-center justify-center">
                <span className="text-white text-sm font-medium">
                  {getUserInitials(user?.name, user?.email)}
                </span>
              </div>
              <div className="hidden md:block text-left">
                <p className="text-sm font-medium text-gray-900">
                  {user?.name || 'User'}
                </p>
                <p className="text-xs text-gray-600">
                  {user?.email}
                </p>
              </div>
              <svg
                className={`w-4 h-4 text-gray-400 transition-transform ${isUserMenuOpen ? 'rotate-180' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {/* Dropdown Menu */}
            {isUserMenuOpen && (
              <div className="absolute right-0 mt-2 w-56 bg-white rounded-md shadow-lg ring-1 ring-black ring-opacity-5 z-50">
                <div className="py-1" role="menu" aria-orientation="vertical">
                  {/* User Info Header */}
                  <div className="px-4 py-3 border-b border-gray-100">
                    <p className="text-sm font-medium text-gray-900">
                      {user?.name || 'User'}
                    </p>
                    <p className="text-sm text-gray-600 truncate">
                      {user?.email}
                    </p>
                  </div>

                  {/* Menu Items */}
                  <Link
                    to="/profile"
                    className="flex items-center px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 transition-colors"
                    role="menuitem"
                    onClick={() => setIsUserMenuOpen(false)}
                  >
                    <svg className="w-4 h-4 mr-3 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                    </svg>
                    Profile
                  </Link>

                  <Link
                    to="/settings"
                    className="flex items-center px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 transition-colors"
                    role="menuitem"
                    onClick={() => setIsUserMenuOpen(false)}
                  >
                    <svg className="w-4 h-4 mr-3 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                    Settings
                  </Link>

                  <div className="border-t border-gray-100">
                    <button
                      onClick={() => {
                        logout();
                        setIsUserMenuOpen(false);
                      }}
                      className="flex items-center w-full px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 transition-colors"
                      role="menuitem"
                    >
                      <svg className="w-4 h-4 mr-3 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
