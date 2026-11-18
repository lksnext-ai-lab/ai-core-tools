import { createContext } from 'react';
import type { AppRole } from '../types/roles';

export interface AppRoleContextValue {
  readonly appId: string;
  readonly userRole: AppRole;
  readonly loading: boolean;
}

export const AppRoleContext = createContext<AppRoleContextValue | null>(null);
