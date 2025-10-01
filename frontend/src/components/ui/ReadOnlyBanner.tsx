interface ReadOnlyBannerProps {
  userRole: string;
}

function ReadOnlyBanner({ userRole }: ReadOnlyBannerProps) {
  return (
    <div className="mb-4 bg-amber-50 border border-amber-200 rounded-lg p-3">
      <div className="flex items-center">
        <span className="text-amber-500 text-lg mr-2">🔒</span>
        <p className="text-sm text-amber-700">
          <strong>Read-only mode:</strong> Only app owners can modify these settings. You have {userRole} access.
        </p>
      </div>
    </div>
  );
}

export default ReadOnlyBanner;


