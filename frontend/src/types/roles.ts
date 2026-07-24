export enum AppRole {
  OWNER = 'owner',
  ADMINISTRATOR = 'administrator',
  EDITOR = 'editor',
  VIEWER = 'viewer',
  USER = 'user',
  GUEST = 'guest'
}

export const ROLE_HIERARCHY = [
  AppRole.GUEST,
  AppRole.USER,
  AppRole.VIEWER,
  AppRole.EDITOR,
  AppRole.ADMINISTRATOR,
  AppRole.OWNER,
];
