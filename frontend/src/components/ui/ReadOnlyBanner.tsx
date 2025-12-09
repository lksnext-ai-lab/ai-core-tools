interface ReadOnlyBannerProps {
  userRole: string;
  minRole?: string;
}

function ReadOnlyBanner({ userRole, minRole = 'app owners' }: Readonly<ReadOnlyBannerProps>) {
  // Helper to pluralize role names if needed
  const getRoleDisplay = (role: string) => {
    if (role === 'app owners') return role;
    // If it's already plural or looks like a sentence, return as is
    if (role.endsWith('s')) return role;
    return `${role}s`;
  };

  const roleDisplay = getRoleDisplay(minRole);

  return (
    <div className="mb-4 bg-amber-50 border border-amber-200 rounded-lg p-3">
      <div className="flex items-center">
        <span className="text-amber-500 text-lg mr-2">🔒</span>
        <p className="text-sm text-amber-700">
          <strong>Read-only mode:</strong> Only {roleDisplay} can modify these settings. You have {userRole} access.
        </p>
      </div>
    </div>
  );
}

export default ReadOnlyBanner;



