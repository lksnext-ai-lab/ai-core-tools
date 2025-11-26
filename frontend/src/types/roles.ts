export enum AppRole {
  OMNIADMIN = 'omniadmin',
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
  AppRole.OMNIADMIN
];
