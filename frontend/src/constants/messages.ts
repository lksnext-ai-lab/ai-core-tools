function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export const MESSAGES = {
  CREATED: (entity: string) => `${capitalize(entity)} created`,
  UPDATED: (entity: string) => `${capitalize(entity)} updated`,
  DELETED: (entity: string) => `${capitalize(entity)} deleted`,
  COPIED: (entity: string) => `${capitalize(entity)} copied`,
  IMPORTED: (entity: string) => `${capitalize(entity)} imported`,
  EXPORTED: (entity: string) => `${capitalize(entity)} exported`,

  CREATING: (entity: string) => `Creating ${entity}…`,
  UPDATING: (entity: string) => `Updating ${entity}…`,
  DELETING: (entity: string) => `Deleting ${entity}…`,
  COPYING: (entity: string) => `Copying ${entity}…`,
  IMPORTING: (entity: string) => `Importing ${entity}…`,
  EXPORTING: (entity: string) => `Exporting ${entity}…`,
  LOADING: (entity: string) => `Loading ${entity}…`,
  SAVING: (entity: string) => `Saving ${entity}…`,

  CREATE_FAILED: (entity: string) => `Failed to create ${entity}`,
  UPDATE_FAILED: (entity: string) => `Failed to update ${entity}`,
  DELETE_FAILED: (entity: string) => `Failed to delete ${entity}`,
  COPY_FAILED: (entity: string) => `Failed to copy ${entity}`,
  IMPORT_FAILED: (entity: string) => `Failed to import ${entity}`,
  EXPORT_FAILED: (entity: string) => `Failed to export ${entity}`,
  LOAD_FAILED: (entity: string) => `Failed to load ${entity}`,
  SAVE_FAILED: (entity: string) => `Failed to save ${entity}`,

  CONFIRM_DELETE_TITLE: (entity: string) => `Delete ${entity}?`,
  CONFIRM_DELETE_MESSAGE: (entity: string) =>
    `Are you sure you want to delete this ${entity}? This action cannot be undone.`,

  GENERIC_ERROR: 'Something went wrong. Please try again.',
  REQUIRED_FIELDS: 'Please complete all required fields.',
  NO_PERMISSION: 'You do not have permission to perform this action.',
} as const;

export function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message) return err.message;
  if (typeof err === 'string' && err) return err;
  return fallback;
}
