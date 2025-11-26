import { AppRole, ROLE_HIERARCHY } from '../types/roles';

type RoleInput = AppRole | string | undefined | null;

export function getRoleLevel(role: RoleInput): number {
  if (!role) return ROLE_HIERARCHY.indexOf(AppRole.GUEST);
  
  // If it's already a valid enum value
  if (Object.values(AppRole).includes(role as AppRole)) {
    return ROLE_HIERARCHY.indexOf(role as AppRole);
  }
  
  return ROLE_HIERARCHY.indexOf(AppRole.GUEST);
}

export function hasMinRole(userRole: RoleInput, requiredRole: AppRole): boolean {
  return getRoleLevel(userRole) >= getRoleLevel(requiredRole);
}

export function hasExactRole(userRole: RoleInput, targetRole: AppRole): boolean {
    return userRole === targetRole;
}
