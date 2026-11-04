/** Marks a platform-wide service (app_id NULL) listed among an app's services. */
function SystemServiceBadge() {
  return (
    <span
      className="ml-1 text-xs font-medium text-blue-700 bg-blue-100 dark:text-blue-200 dark:bg-blue-900/40 px-1.5 py-0.5 rounded"
      title="Platform service managed by the system administrators"
    >
      System
    </span>
  );
}

export default SystemServiceBadge;
