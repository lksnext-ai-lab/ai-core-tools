import { getProvidersForKind } from '../providers';
import { getProviderBadgeColor } from '../../../ui/providerBadges';
import type { ServiceKind } from '../../../../types/services';

interface ProviderStepProps {
  readonly kind: ServiceKind;
  readonly selected: string;
  readonly onSelect: (providerValue: string) => void;
}

function ProviderStep({
  kind,
  selected,
  onSelect,
}: Readonly<ProviderStepProps>) {
  const providers = getProvidersForKind(kind);
  const subtitle =
    kind === 'ai'
      ? 'Pick the provider that hosts the chat, vision or audio model you want to use.'
      : 'Pick the provider for the embedding model that will index your data.';

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold text-gray-900">Choose a provider</h3>
        <p className="text-sm text-gray-600 mt-1">{subtitle}</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {providers.map((p) => {
          const isSelected = selected === p.value;
          return (
            <button
              key={p.value}
              type="button"
              onClick={() => onSelect(p.value)}
              className={`text-left p-4 rounded-lg border transition-all focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                isSelected
                  ? 'border-blue-600 ring-2 ring-blue-200 bg-blue-50'
                  : 'border-gray-200 bg-white hover:border-gray-300 hover:shadow-sm'
              }`}
            >
              <div className="flex items-start gap-3">
                <div
                  className={`flex-shrink-0 w-9 h-9 rounded-md flex items-center justify-center ${getProviderBadgeColor(
                    p.value,
                  )}`}
                >
                  <p.Icon className="w-5 h-5" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-semibold text-gray-900 truncate">
                      {p.label}
                    </span>
                    {!p.supportsModelListing && (
                      <span className="text-[10px] uppercase tracking-wide font-medium text-amber-700 bg-amber-50 border border-amber-200 px-1.5 py-0.5 rounded">
                        Manual
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-gray-600 mt-1 line-clamp-2">
                    {p.description}
                  </p>
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default ProviderStep;
